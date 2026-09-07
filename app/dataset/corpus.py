"""
The Phase 6 controlled source corpus (#118).

Assembles :class:`SourceRecord` objects from:

* the repository's own MIT-licensed test fixtures (``repository_fixture``);
* synthetic programs written for Phase 6 (``synthetic``);
* the ``tests/golden/*.java`` pairs as reviewed / executable-verified
  ``cobol_to_java`` labels.

Provenance and licensing for every entry are documented in
``data/sources/phase6/SOURCES.md`` and ``data/sources/phase6-v2/SOURCES.md``.
No external / unverified material is included.

**Training vs evaluation corpus.** ``load_phase6_corpus`` is the full
corpus that produced both ``phase6-v1`` *and* ``benchmark-v1`` — they
overlap, which is why #121's leakage guard rejects ``phase6-v1``.
``load_training_corpus`` returns a corpus that is **source-disjoint from
the benchmark**: the three original programs the benchmark never used,
plus dedicated synthetic training-only programs. ``load_evaluation_corpus``
returns exactly the held-out programs the benchmark is built from. The
partition is::

    load_phase6_corpus()  ==  load_training_corpus()  ⊍  load_evaluation_corpus()  \\
                              (minus the v2-only synthetic additions)

and by construction::

    {r.source_id for r in load_training_corpus()} ∩ BENCHMARK_SOURCE_IDS == ∅
"""

from __future__ import annotations

from pathlib import Path

from app.dataset.builder import SourceRecord
from app.dataset.schema import Difficulty, Provenance

__all__ = [
    "REPO_ROOT",
    "BENCHMARK_SOURCE_IDS",
    "load_phase6_corpus",
    "load_training_corpus",
    "load_evaluation_corpus",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
_SYN_DIR = REPO_ROOT / "data" / "sources" / "phase6"
_V2_SYN_DIR = REPO_ROOT / "data" / "sources" / "phase6-v2"

_MIT = "MIT"

#: The source programs the frozen ``benchmark-v1`` (#119) is built from —
#: see ``app/benchmark/curated.py::_SPEC``. These are **held out
#: permanently**: no training dataset may contain them.
#: ``tests/dataset/test_benchmark_separation.py`` asserts this set equals
#: the source ids actually present in ``data/benchmark/benchmark-v1/``.
BENCHMARK_SOURCE_IDS: frozenset[str] = frozenset(
    {
        "fx_hello_world",
        "fx_move_display",
        "fx_arithmetic",
        "fx_if_else",
        "fx_call",
        "fx_eligibility",
        "fx_complex_proc",
        "fx_highly_coupled",
        "fx_acctbatch",
        "fx_unsupported",
        "fx_file_processing",
        "fx_incomplete",
        "syn_status_machine",
        "syn_limit_check",
        "syn_misleading_names",
        "syn_misleading_comments",
        "syn_ambiguous_question",
    }
)

# (source_id, repo-relative path, difficulty, golden-java repo-relative path or None)
_FIXTURES: tuple[tuple[str, str, Difficulty, str | None], ...] = (
    ("fx_hello_world", "tests/fixtures/hello_world.cbl", Difficulty.EASY, None),
    (
        "fx_move_display",
        "tests/golden/move_display.cbl",
        Difficulty.EASY,
        "tests/golden/move_display.java",
    ),
    (
        "fx_arithmetic",
        "tests/golden/arithmetic.cbl",
        Difficulty.EASY,
        "tests/golden/arithmetic.java",
    ),
    (
        "fx_if_else",
        "tests/golden/if_else.cbl",
        Difficulty.MEDIUM,
        "tests/golden/if_else.java",
    ),
    (
        "fx_call",
        "tests/golden/call.cbl",
        Difficulty.MEDIUM,
        "tests/golden/call.java",
    ),
    (
        "fx_perform_until",
        "tests/golden/perform_until.cbl",
        Difficulty.MEDIUM,
        "tests/golden/perform_until.java",
    ),
    (
        "fx_combined",
        "tests/golden/combined_program.cbl",
        Difficulty.DIFFICULT,
        "tests/golden/combined_program.java",
    ),
    (
        "fx_eligibility",
        "tests/fixtures/phase4/eligibility_rules.cbl",
        Difficulty.MEDIUM,
        None,
    ),
    (
        "fx_simple_proc",
        "tests/fixtures/phase5/simple_procedural.cbl",
        Difficulty.MEDIUM,
        None,
    ),
    (
        "fx_complex_proc",
        "tests/fixtures/phase5/complex_procedural.cbl",
        Difficulty.DIFFICULT,
        None,
    ),
    (
        "fx_highly_coupled",
        "tests/fixtures/phase5/highly_coupled.cbl",
        Difficulty.DIFFICULT,
        None,
    ),
    (
        "fx_file_processing",
        "tests/fixtures/phase5/file_processing.cbl",
        Difficulty.ADVERSARIAL,
        None,
    ),
    (
        "fx_unsupported",
        "tests/fixtures/phase5/unsupported_syntax.cbl",
        Difficulty.ADVERSARIAL,
        None,
    ),
    (
        "fx_incomplete",
        "tests/fixtures/phase5/incomplete_parsing.cbl",
        Difficulty.ADVERSARIAL,
        None,
    ),
    (
        "fx_acctbatch",
        "workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl",
        Difficulty.DIFFICULT,
        None,
    ),
)

# (source_id, filename under data/sources/phase6/, difficulty, note)
_SYNTHETIC: tuple[tuple[str, str, Difficulty, str], ...] = (
    (
        "syn_status_machine",
        "status_machine.cbl",
        Difficulty.MEDIUM,
        "status-transition rules",
    ),
    (
        "syn_misleading_names",
        "misleading_names.cbl",
        Difficulty.ADVERSARIAL,
        "identifier WS-FRAUD-SCORE is only a loop counter",
    ),
    (
        "syn_misleading_comments",
        "misleading_comments.cbl",
        Difficulty.ADVERSARIAL,
        "a comment claims a discount rule the code never applies",
    ),
    (
        "syn_ambiguous_question",
        "ambiguous_question.cbl",
        Difficulty.ADVERSARIAL,
        "used with a question that is not answerable from the source",
    ),
    (
        "syn_limit_check",
        "limit_check.cbl",
        Difficulty.MEDIUM,
        "numeric limit-check rule",
    ),
)

#: Training-only synthetic programs for ``phase6-v2`` (#118 rebuild).
#: Hand-written for this repository, MIT-licensed, documented in
#: ``data/sources/phase6-v2/SOURCES.md``. Each is a distinct small
#: business program (payroll, inventory, lending, grading, shipping,
#: fees, …) within the analyzer's supported COBOL subset. They exist so a
#: benchmark-disjoint training split has real source diversity — never to
#: pad a source count. source_id is ``t_<filename stem>``.
# (filename under data/sources/phase6-v2/, difficulty, note)
_TRAINING_SYNTHETIC: tuple[tuple[str, Difficulty, str], ...] = (
    (
        "payroll_net_pay.cbl",
        Difficulty.MEDIUM,
        "gross-to-net payroll with a tax bracket",
    ),
    ("reorder_point.cbl", Difficulty.MEDIUM, "inventory reorder-point decision"),
    (
        "loan_balance.cbl",
        Difficulty.DIFFICULT,
        "loan amortisation loop (PERFORM UNTIL)",
    ),
    ("grade_letter.cbl", Difficulty.MEDIUM, "score-to-letter-grade nested IF"),
    ("shipping_zone.cbl", Difficulty.MEDIUM, "weight/zone shipping cost"),
    (
        "account_validate.cbl",
        Difficulty.DIFFICULT,
        "two external CALLs then a nested accept/hold/reject decision",
    ),
    ("discount_tier.cbl", Difficulty.MEDIUM, "customer-tier discount schedule"),
    (
        "overdraft_fee.cbl",
        Difficulty.MEDIUM,
        "overdraft fee with an extra-days surcharge",
    ),
    ("temp_convert.cbl", Difficulty.EASY, "Celsius-to-Fahrenheit arithmetic"),
    ("late_fee.cbl", Difficulty.MEDIUM, "days-overdue late-fee schedule"),
    ("interest_accrue.cbl", Difficulty.DIFFICULT, "daily interest accrual loop"),
    ("bonus_calc.cbl", Difficulty.MEDIUM, "sales-tier bonus with a rating flag"),
    ("credit_limit.cbl", Difficulty.MEDIUM, "income/score credit-limit decision"),
    ("vacation_accrual.cbl", Difficulty.MEDIUM, "years-of-service vacation accrual"),
    ("stock_alert.cbl", Difficulty.MEDIUM, "price-change alert flag"),
)

#: Golden Java files verified to compile with javac (tests/golden/ + the
#: Phase 3 review report).
_JAVA_COMPILES = frozenset(
    {
        "tests/golden/move_display.java",
        "tests/golden/arithmetic.java",
        "tests/golden/if_else.java",
        "tests/golden/call.java",
        "tests/golden/perform_until.java",
        "tests/golden/combined_program.java",
    }
)


def load_phase6_corpus() -> list[SourceRecord]:
    """Return every :class:`SourceRecord` in the Phase 6 corpus."""
    records: list[SourceRecord] = []

    for source_id, rel, difficulty, java_rel in _FIXTURES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        reviewed_java = None
        java_compiles = None
        if java_rel:
            jpath = REPO_ROOT / java_rel
            if jpath.exists():
                reviewed_java = jpath.read_text(encoding="utf-8")
                java_compiles = java_rel in _JAVA_COMPILES
        records.append(
            SourceRecord(
                source_id=source_id,
                source=path.read_text(encoding="utf-8"),
                provenance=Provenance.REPOSITORY_FIXTURE,
                license=_MIT,
                difficulty=difficulty,
                reviewed_java=reviewed_java,
                java_compiles=java_compiles,
                notes=f"repository fixture: {rel}",
            )
        )

    for source_id, fname, difficulty, note in _SYNTHETIC:
        path = _SYN_DIR / fname
        if not path.exists():
            continue
        records.append(
            SourceRecord(
                source_id=source_id,
                source=path.read_text(encoding="utf-8"),
                provenance=Provenance.SYNTHETIC,
                license=_MIT,
                difficulty=difficulty,
                notes=f"synthetic (Phase 6): {note}",
            )
        )

    return sorted(records, key=lambda r: r.source_id)


def _training_synthetic_records() -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for fname, difficulty, note in _TRAINING_SYNTHETIC:
        path = _V2_SYN_DIR / fname
        if not path.exists():
            continue
        records.append(
            SourceRecord(
                source_id=f"t_{Path(fname).stem}",
                source=path.read_text(encoding="utf-8"),
                provenance=Provenance.SYNTHETIC,
                license=_MIT,
                difficulty=difficulty,
                notes=f"synthetic training-only (phase6-v2): {note}",
            )
        )
    return records


def load_training_corpus() -> list[SourceRecord]:
    """The benchmark-disjoint training corpus for ``phase6-v2``.

    = the original programs the benchmark never used
      (``BENCHMARK_SOURCE_IDS`` removed from :func:`load_phase6_corpus`)
      + the dedicated synthetic training-only programs.

    Guarantees ``{r.source_id} ∩ BENCHMARK_SOURCE_IDS == ∅``.
    """
    kept = [r for r in load_phase6_corpus() if r.source_id not in BENCHMARK_SOURCE_IDS]
    records = kept + _training_synthetic_records()
    overlap = {r.source_id for r in records} & BENCHMARK_SOURCE_IDS
    if overlap:  # pragma: no cover - defensive; construction prevents this
        raise AssertionError(f"training corpus overlaps benchmark: {sorted(overlap)}")
    return sorted(records, key=lambda r: r.source_id)


def load_evaluation_corpus() -> list[SourceRecord]:
    """The held-out programs ``benchmark-v1`` is built from (read-only)."""
    return sorted(
        (r for r in load_phase6_corpus() if r.source_id in BENCHMARK_SOURCE_IDS),
        key=lambda r: r.source_id,
    )
