"""#118 §8-§10 — validation, splitting, leakage tests."""

from __future__ import annotations

import json

from app.dataset.io import canonical_json_line, write_jsonl
from app.dataset.leakage import detect_leakage
from app.dataset.schema import Provenance, TaskType
from app.dataset.splitting import SplitRatios, split_dataset
from app.dataset.validation import validate_dataset
from app.dataset.version import DATASET_VERSION
from tests.dataset.conftest import make_example

# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_validate_clean_dataset(tmp_path) -> None:
    exs = [
        make_example(source_id=f"s{i}", variant=str(i), task=TaskType.MODERNIZATION_QA)
        for i in range(4)
    ]
    p = tmp_path / "d.jsonl"
    write_jsonl(p, exs)
    rep = validate_dataset(p, expected_version=DATASET_VERSION)
    assert rep.ok
    assert rep.valid == 4
    assert rep.error_count == 0


def test_validate_rejects_malformed_json(tmp_path) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text('{"not": "valid"\n', encoding="utf-8")
    rep = validate_dataset(p)
    assert not rep.ok
    assert any(i.code in ("invalid_jsonl", "schema") for i in rep.issues)


def test_validate_detects_duplicate_example_id(tmp_path) -> None:
    ex = make_example(source_id="s1", variant="a")
    p = tmp_path / "dup.jsonl"
    p.write_text(
        canonical_json_line(ex.model_dump(mode="json"))
        + "\n"
        + canonical_json_line(ex.model_dump(mode="json"))
        + "\n",
        encoding="utf-8",
    )
    rep = validate_dataset(p)
    assert any(i.code == "exact_duplicate" for i in rep.issues)
    assert any(i.code == "duplicate_example_id" for i in rep.issues)


def test_validate_detects_content_duplicate_different_id(tmp_path) -> None:
    a = make_example(source_id="s1", variant="a")
    b = make_example(source_id="s1", variant="b")  # different id, same content
    p = tmp_path / "cd.jsonl"
    write_jsonl(p, [a, b])
    rep = validate_dataset(p)
    assert any(i.code == "content_duplicate" for i in rep.issues)


def test_validate_flags_secret_in_source(tmp_path) -> None:
    src = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. LEAK.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN.\n"
        "           MOVE 'AKIA1234567890ABCDEF' TO WS-KEY.\n"
        "           STOP RUN.\n"
    )
    ex = make_example(source=src, source_id="leak")
    p = tmp_path / "s.jsonl"
    write_jsonl(p, [ex])
    rep = validate_dataset(p)
    assert not rep.ok
    assert rep.secret_findings
    assert any(i.code == "secret" for i in rep.issues)


def test_validate_detects_mixed_versions(tmp_path) -> None:
    a = make_example(source_id="s1", variant="a").model_dump(mode="json")
    b = make_example(source_id="s2", variant="b").model_dump(mode="json")
    b["dataset_version"] = "phase6-v99"
    p = tmp_path / "mv.jsonl"
    p.write_text(
        canonical_json_line(a) + "\n" + canonical_json_line(b) + "\n", encoding="utf-8"
    )
    rep = validate_dataset(p)
    assert any(i.code == "mixed_versions" for i in rep.issues)


# ---------------------------------------------------------------------------
# splitting
# ---------------------------------------------------------------------------


def _mksrc(n: int) -> str:
    return (
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. P{n:03d}.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        f"       01 WS-V{n:03d} PIC 9(3) VALUE {n % 10}.\n"
        "       PROCEDURE DIVISION.\n"
        f"       MAIN-{n:03d}.\n"
        f"           MOVE {n % 100} TO WS-V{n:03d}.\n"
        "           STOP RUN.\n"
    )


def _corpus(n_sources: int, per_source: int = 3):
    out = []
    for s in range(n_sources):
        src = _mksrc(s)
        for k in range(per_source):
            out.append(
                make_example(
                    source=src,
                    source_id=f"src{s:02d}",
                    variant=f"{s}-{k}",
                    task=list(TaskType)[k % len(TaskType)],
                    expected={"answer": {"n": s, "k": k}},
                )
            )
    return out


def test_split_is_deterministic_from_version_and_seed() -> None:
    exs = _corpus(30)
    a = split_dataset(exs, seed=7)
    b = split_dataset(exs, seed=7)
    assert [e.example_id for e in a.train] == [e.example_id for e in b.train]
    assert a.assignment == b.assignment
    c = split_dataset(exs, seed=8)
    assert c.assignment != a.assignment  # different seed -> different split


def test_split_never_puts_a_source_in_two_splits() -> None:
    exs = _corpus(40)
    r = split_dataset(exs, seed=3)
    train_src = {e.input.source_id for e in r.train}
    val_src = {e.input.source_id for e in r.validation}
    test_src = {e.input.source_id for e in r.test}
    assert not (train_src & val_src)
    assert not (train_src & test_src)
    assert not (val_src & test_src)
    # every example landed with its group
    for split_name, group in (
        ("train", r.train),
        ("validation", r.validation),
        ("test", r.test),
    ):
        for e in group:
            assert r.assignment[e.input.source_id] == split_name


def test_split_ratios_are_respected_within_group_granularity() -> None:
    exs = _corpus(100)
    r = split_dataset(exs, seed=1, ratios=SplitRatios(0.6, 0.2, 0.2))
    total = len(exs)
    assert 0.45 * total <= len(r.train) <= 0.75 * total
    assert len(r.validation) > 0 and len(r.test) > 0


def test_split_manifest_is_json_safe() -> None:
    r = split_dataset(_corpus(10), seed=1)
    json.dumps(r.manifest())


# ---------------------------------------------------------------------------
# leakage
# ---------------------------------------------------------------------------


def test_leakage_hard_fails_on_shared_source_id() -> None:
    a = make_example(source_id="shared", variant="a", task=TaskType.MODERNIZATION_QA)
    b = make_example(source_id="shared", variant="b", task=TaskType.RISK_IDENTIFICATION)
    rep = detect_leakage(train=[a], validation=[], test=[b])
    assert not rep.ok
    assert any(h.kind == "shared_source_id" and h.severity == "error" for h in rep.hits)


def test_leakage_hard_fails_on_identical_source_text() -> None:
    src = make_example().input.source
    a = make_example(source=src, source_id="p1", variant="a")
    b = make_example(source=src, source_id="p2", variant="b")
    rep = detect_leakage(train=[a], validation=[b], test=[])
    assert any(h.kind == "identical_source" and h.severity == "error" for h in rep.hits)


def test_leakage_clean_when_sources_disjoint() -> None:
    exs = _corpus(30)
    r = split_dataset(exs, seed=5)
    rep = detect_leakage(r.train, r.validation, r.test)
    assert rep.ok  # no error-severity hits


def test_leakage_ignores_trivial_negative_answers() -> None:
    a = make_example(
        source_id="a",
        variant="a",
        task=TaskType.BUSINESS_RULE_EXTRACTION,
        expected={"business_rules": [], "rule_count": 0},
    )
    b = make_example(
        source_id="b",
        variant="b",
        task=TaskType.BUSINESS_RULE_EXTRACTION,
        source="       IDENTIFICATION DIVISION.\n       PROGRAM-ID. B.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n           STOP RUN.\n",
        expected={"business_rules": [], "rule_count": 0},
    )
    rep = detect_leakage(train=[a], validation=[], test=[b])
    assert not any(h.kind == "identical_expected_output" for h in rep.hits)


# ---------------------------------------------------------------------------
# full corpus build (integration)
# ---------------------------------------------------------------------------


def test_built_corpus_validates_splits_and_has_no_leakage(
    built_dataset, tmp_path
) -> None:
    p = tmp_path / "all.jsonl"
    write_jsonl(p, built_dataset.examples)
    rep = validate_dataset(p, expected_version=DATASET_VERSION)
    assert rep.ok, [i.to_dict() for i in rep.issues if i.severity.value == "error"][:5]

    split = split_dataset(built_dataset.examples, seed=20260906)
    assert len(split.train) + len(split.validation) + len(split.test) == len(
        built_dataset.examples
    )
    leak = detect_leakage(split.train, split.validation, split.test)
    assert leak.ok, [h.to_dict() for h in leak.hits if h.severity == "error"][:5]


def test_built_corpus_provenance_is_explicit(built_dataset) -> None:
    for ex in built_dataset.examples:
        assert ex.metadata.source_provenance in Provenance
        assert ex.metadata.provenance in Provenance
        assert ex.metadata.license
        assert ex.metadata.generator_version
        assert ex.metadata.analysis_version
        assert len(ex.metadata.source_sha256) == 64


def test_built_corpus_java_answers_never_claim_unverified_ground_truth(
    built_dataset,
) -> None:
    from app.dataset.schema import GroundTruthStatus

    for ex in built_dataset.examples:
        if ex.task_type is not TaskType.COBOL_TO_JAVA:
            continue
        # backend output that was not human-reviewed must be REFERENCE only
        if ex.metadata.ground_truth_status is GroundTruthStatus.REFERENCE:
            assert "not a human-reviewed" in (ex.metadata.notes or "").lower()
        else:
            assert ex.metadata.ground_truth_status in (
                GroundTruthStatus.REVIEWED,
                GroundTruthStatus.EXECUTABLE_VERIFIED,
            )


def test_build_is_byte_reproducible(tmp_path) -> None:
    from app.dataset.builder import DatasetBuilder
    from app.dataset.corpus import load_phase6_corpus

    b1 = DatasetBuilder(
        work_dir=tmp_path / "w1", created_at="2026-01-01T00:00:00Z"
    ).build(load_phase6_corpus())
    b2 = DatasetBuilder(
        work_dir=tmp_path / "w2", created_at="2026-01-01T00:00:00Z"
    ).build(load_phase6_corpus())
    lines1 = [canonical_json_line(e.model_dump(mode="json")) for e in b1.examples]
    lines2 = [canonical_json_line(e.model_dump(mode="json")) for e in b2.examples]
    assert lines1 == lines2
    assert b1.manifest == b2.manifest
