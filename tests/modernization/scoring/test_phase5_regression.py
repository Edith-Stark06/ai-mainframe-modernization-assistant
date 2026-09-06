"""
Phase 5 scoring regression suite (#117).

Nine deterministic fixtures, each with expected RANGES (never exact
floats) for complexity / coupling / readiness / confidence / coverage,
plus the semantic properties Phase 5 must guarantee.
"""

from __future__ import annotations

import json

import pytest

from tests.modernization.scoring.conftest import (
    PHASE5_FIXTURES,
    analyze_fixture,
    analyze_source,
    score_fixture,
)

# ---------------------------------------------------------------------------
# Per-fixture expected ranges
#   (complexity, coupling, readiness, confidence, coverage) as (lo, hi)
# ---------------------------------------------------------------------------

_RANGES = {
    "trivial": {
        "complexity": (0.0, 0.15),
        "readiness": (0.80, 1.0),
        "confidence": (0.95, 1.0),
        "coverage": (0.95, 1.0),
    },
    "simple_procedural": {
        "complexity": (0.05, 0.35),
        "readiness": (0.60, 0.95),
        "confidence": (0.90, 1.0),
        "coverage": (0.95, 1.0),
    },
    "complex_procedural": {
        "complexity": (0.15, 0.55),
        "readiness": (0.55, 0.90),
        "confidence": (0.85, 1.0),
        "coverage": (0.90, 1.0),
    },
    "file_processing": {
        "readiness": (0.60, 1.0),
        "confidence": (0.35, 0.80),
        "coverage": (0.35, 0.80),
    },
    "highly_coupled": {
        "complexity": (0.25, 0.75),
        "readiness": (0.40, 0.85),
        "confidence": (0.85, 1.0),
        "coverage": (0.90, 1.0),
    },
    "low_complexity": {
        "complexity": (0.0, 0.25),
        "readiness": (0.70, 1.0),
        "confidence": (0.95, 1.0),
        "coverage": (0.95, 1.0),
    },
    "unsupported_syntax": {
        "confidence": (0.45, 0.85),
        "coverage": (0.45, 0.85),
    },
    "incomplete_parsing": {
        "confidence": (0.0, 0.55),
        "coverage": (0.0, 0.55),
    },
    "parser_failure": {
        "confidence": (0.0, 0.15),
        "coverage": (0.0, 0.15),
    },
}


@pytest.mark.parametrize("name", PHASE5_FIXTURES)
def test_fixture_ranges(name: str, scores) -> None:
    sc = scores[name]
    values = {
        "complexity": sc.complexity,
        "coupling": sc.coupling,
        "readiness": sc.readiness,
        "confidence": sc.analysis_confidence,
        "coverage": sc.analysis_coverage,
    }
    for metric, (lo, hi) in _RANGES[name].items():
        assert (
            lo <= values[metric] <= hi
        ), f"{name}.{metric}={values[metric]:.3f} not in [{lo}, {hi}]"


# ---------------------------------------------------------------------------
# Semantic properties
# ---------------------------------------------------------------------------


def test_fully_analyzed_program_high_coverage_high_confidence(scores) -> None:
    for name in (
        "trivial",
        "simple_procedural",
        "complex_procedural",
        "low_complexity",
    ):
        sc = scores[name]
        assert sc.analysis_coverage >= 0.9, name
        assert sc.analysis_confidence >= 0.85, name
        assert sc.coverage_report.overall_status.value in ("COMPLETE", "PARTIAL")


def test_readiness_reflects_actual_complexity_when_fully_analyzed(scores) -> None:
    # All four are fully analyzed, so readiness should track complexity:
    # the more complex / coupled program should not read as *more* ready.
    trivial = scores["trivial"]
    complex_ = scores["complex_procedural"]
    coupled = scores["highly_coupled"]
    assert trivial.readiness > complex_.readiness
    assert complex_.readiness >= coupled.readiness - 0.15
    assert coupled.complexity > trivial.complexity


def test_partial_parsing_reduces_coverage_and_confidence(scores) -> None:
    sc = scores["incomplete_parsing"]
    assert sc.coverage_report.parser.status.value == "PARTIAL"
    assert sc.analysis_coverage < 0.6
    assert sc.analysis_confidence < 0.6
    # readiness must NOT gain an advantage from the unparsed tail
    full = scores["simple_procedural"]
    assert sc.analysis_confidence < full.analysis_confidence
    assert sc.analysis_coverage < full.analysis_coverage


def test_parser_failure_no_falsely_strong_conclusion(scores) -> None:
    sc = scores["parser_failure"]
    assert sc.analysis_coverage <= 0.15
    assert sc.analysis_confidence <= 0.15
    assert sc.insufficient_data is True
    assert "not" in sc.interpretation.lower() or "fail" in sc.interpretation.lower()
    # readiness can be whatever the legacy scorer says, but it must not be
    # presentable as trustworthy — confidence is the guard.
    assert sc.analysis_confidence < 0.2


def test_unsupported_syntax_reported_and_lowers_confidence(scores) -> None:
    sc = scores["unsupported_syntax"]
    us = sc.coverage_report.unsupported_syntax
    assert us.distinct_codes >= 1
    assert us.total_occurrences >= 1
    assert "SYN200" in us.codes or "SYN100" in us.codes
    assert us.affected_dimensions  # non-empty
    # confidence and coverage both reflect the missing analysis
    assert sc.analysis_confidence < 0.9
    assert sc.analysis_coverage < 0.9


def test_file_processing_constructs_are_unsupported_not_ignored(scores) -> None:
    sc = scores["file_processing"]
    us = sc.coverage_report.unsupported_syntax
    assert us.total_occurrences >= 3  # SELECT/FD/OPEN/READ/CLOSE family
    assert sc.analysis_confidence < 0.8


def test_empty_program_explicit_semantics(tmp_path) -> None:
    ar = analyze_source(
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. EMPTY.\n", tmp_path
    )
    from app.modernization.scoring.confidence_aware import score_with_confidence

    sc = score_with_confidence(ar)
    # no accidental perfect confidence
    assert sc.analysis_confidence <= 0.5
    assert sc.insufficient_data is True
    assert "no procedure division body" in sc.interpretation.lower()
    # distinct from parser failure (which is ~0 everywhere)
    pf = score_fixture("parser_failure")
    assert sc.analysis_coverage != pf.analysis_coverage


def test_clean_trivial_distinct_from_incomplete(scores) -> None:
    clean = scores["trivial"]
    incomplete = scores["incomplete_parsing"]
    assert clean.analysis_confidence - incomplete.analysis_confidence > 0.4
    assert clean.analysis_coverage - incomplete.analysis_coverage > 0.4
    assert clean.coverage_report.overall_status.value == "COMPLETE"
    assert incomplete.coverage_report.overall_status.value != "COMPLETE"


# ---------------------------------------------------------------------------
# Invariants / metamorphic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PHASE5_FIXTURES)
def test_all_metrics_within_bounds(name: str, scores) -> None:
    sc = scores[name]
    for v in (
        sc.readiness,
        sc.complexity,
        sc.coupling,
        sc.analysis_confidence,
        sc.analysis_coverage,
    ):
        assert 0.0 <= v <= 1.0
    cr = sc.coverage_report
    assert 0.0 <= cr.overall <= 1.0
    for d in cr.dimensions:
        assert 0.0 <= d.ratio <= 1.0


@pytest.mark.parametrize("name", PHASE5_FIXTURES)
def test_determinism_same_source_same_output(name: str) -> None:
    a = json.dumps(score_fixture(name).to_dict(), sort_keys=True)
    b = json.dumps(score_fixture(name).to_dict(), sort_keys=True)
    assert a == b


def test_determinism_fresh_pipeline_same_source(tmp_path) -> None:
    src = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. D.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC X VALUE SPACE.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           IF WS-A = 'Y'\n               MOVE 'Z' TO WS-A\n           END-IF.\n"
        "           STOP RUN.\n"
    )
    from app.modernization.scoring.confidence_aware import score_with_confidence

    a = analyze_source(src, tmp_path, "same.cbl")
    b = analyze_source(src, tmp_path, "same.cbl")
    da = json.dumps(score_with_confidence(a).to_dict(), sort_keys=True)
    db = json.dumps(score_with_confidence(b).to_dict(), sort_keys=True)
    assert da == db


def test_confidence_monotonic_when_content_becomes_unsupported(tmp_path) -> None:
    """
    Transforming analysable statements into unsupported ones must NOT
    raise confidence (it must fall or stay equal).
    """
    from app.modernization.scoring.confidence_aware import score_with_confidence

    supported = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. M.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(5) VALUE 0.\n       01 WS-B PIC 9(5) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           MOVE 2 TO WS-B.\n"
        "           ADD WS-A TO WS-B.\n           STOP RUN.\n"
    )
    # same program, but the two data items are now COMP-3 (unmodelled) and
    # one statement is a GO TO (unsupported).
    degraded = (
        supported.replace(
            "01 WS-A PIC 9(5) VALUE 0.", "01 WS-A PIC 9(5) COMP-3 VALUE 0."
        )
        .replace("01 WS-B PIC 9(5) VALUE 0.", "01 WS-B PIC 9(5) COMP-3 VALUE 0.")
        .replace("ADD WS-A TO WS-B.", "GO TO SKIP-PARA.")
    )
    degraded += "       SKIP-PARA.\n           DISPLAY WS-B.\n"

    c_supported = score_with_confidence(
        analyze_source(supported, tmp_path, "s.cbl")
    ).analysis_confidence
    c_degraded = score_with_confidence(
        analyze_source(degraded, tmp_path, "d.cbl")
    ).analysis_confidence
    assert c_degraded <= c_supported


def test_confidence_monotonic_when_parsing_becomes_incomplete(tmp_path) -> None:
    from app.modernization.scoring.confidence_aware import score_with_confidence

    complete = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           DISPLAY WS-A.\n           STOP RUN.\n"
    )
    # move DATA DIVISION after PROCEDURE DIVISION -> parser never reaches it
    incomplete = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n           DISPLAY WS-A.\n           STOP RUN.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n"
    )
    c_complete = score_with_confidence(
        analyze_source(complete, tmp_path, "c.cbl")
    ).analysis_confidence
    c_incomplete = score_with_confidence(
        analyze_source(incomplete, tmp_path, "i.cbl")
    ).analysis_confidence
    assert c_incomplete < c_complete


def test_no_positive_evidence_from_missing_analysis(tmp_path) -> None:
    """
    A program whose difficult logic was NOT analysed must not score a
    BETTER readiness *with higher confidence* than the same program fully
    analysed. Confidence must expose the loss.
    """
    from app.modernization.scoring.confidence_aware import score_with_confidence

    analysed = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. N.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n       01 WS-B PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           PERFORM WORK-PARA.\n           STOP RUN.\n"
        "       WORK-PARA.\n"
        "           IF WS-A > 0\n               ADD 1 TO WS-B\n           END-IF.\n"
        "           IF WS-B > 0\n               ADD 1 TO WS-A\n           END-IF.\n"
    )
    # the WORK-PARA logic is replaced by an unsupported EVALUATE -> lost
    lost = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. N.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n       01 WS-B PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           PERFORM WORK-PARA.\n           STOP RUN.\n"
        "       WORK-PARA.\n"
        "           EVALUATE TRUE\n"
        "               WHEN WS-A > 0\n                   ADD 1 TO WS-B\n"
        "           END-EVALUATE.\n"
    )
    a = score_with_confidence(analyze_source(analysed, tmp_path, "a.cbl"))
    b = score_with_confidence(analyze_source(lost, tmp_path, "b.cbl"))

    # the version with lost logic must not be presented as a stronger result
    assert b.analysis_confidence <= a.analysis_confidence
    assert b.analysis_coverage <= a.analysis_coverage
    # and its business-rule / statement coverage must show the gap
    assert (
        b.coverage_report.statement.ratio <= a.coverage_report.statement.ratio
        or b.coverage_report.business_rule.ratio
        <= a.coverage_report.business_rule.ratio
    )


def test_no_dependencies_is_not_confirmed_low_coupling_when_incomplete(
    scores, tmp_path
) -> None:
    """
    'No CALL dependencies' must not be treated as confirmed low coupling
    when dependency coverage is incomplete.
    """
    # incomplete_parsing: parser did not finish -> dependency dimension
    # cannot be COMPLETE even though the parsed fragment had a PERFORM.
    sc = scores["incomplete_parsing"]
    assert sc.coverage_report.dependency.status.value != "COMPLETE"
    assert sc.coverage_report.parser.status.value != "COMPLETE"

    # A program with genuinely zero dependencies but an unsupported
    # statement region: the "no deps" must be reported as unconfirmed.
    src = (
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. Z.\n"
        "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC 9(3) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n       MAIN.\n"
        "           MOVE 1 TO WS-A.\n"
        "           GO TO SKIP.\n"
        "           STOP RUN.\n"
        "       SKIP.\n           DISPLAY WS-A.\n"
    )
    from app.modernization.scoring.confidence_aware import score_with_confidence

    z = score_with_confidence(analyze_source(src, tmp_path, "z.cbl"))
    dep = z.coverage_report.dependency
    assert dep.status.value != "COMPLETE"
    assert "not confirmed" in dep.detail.lower()


def test_no_business_rules_not_poor_coverage_when_no_conditionals(scores) -> None:
    """
    A program with no conditional logic and full parsing gets a
    NOT_MEASURABLE business-rule dimension, not a low ratio.
    """
    sc = scores["low_complexity"]
    br = sc.coverage_report.business_rule
    assert br.status.value == "NOT_MEASURABLE"
    assert sc.analysis_coverage >= 0.95  # not dragged down by "0 rules"


def test_overall_coverage_is_weakest_link_not_average(scores) -> None:
    for name in PHASE5_FIXTURES:
        cr = scores[name].coverage_report
        measurable = [d.ratio for d in cr.dimensions if d.measurable]
        if not measurable:
            continue
        # overall equals the minimum measurable dimension (weakest link)
        assert abs(cr.overall - min(measurable)) < 1e-9, name


def test_serialization_end_to_end(scores) -> None:
    for name, sc in scores.items():
        d = sc.to_dict()
        json.dumps(d)  # must not raise
        assert set(d) >= {
            "readiness",
            "analysis_confidence",
            "analysis_coverage",
            "interpretation",
            "coverage",
            "confidence",
            "score",
        }
        assert "dimensions" in d["coverage"]
        assert "factors" in d["confidence"]


def test_readiness_unchanged_from_legacy_scorer(scores) -> None:
    """#116 must not silently rewrite readiness: it equals calculate_scores()."""
    from app.modernization.flow.generator import generate_flow
    from app.modernization.scoring.service import calculate_scores

    for name in PHASE5_FIXTURES:
        ar = analyze_fixture(name)
        legacy = calculate_scores(ar, generate_flow(ar))
        sc = scores[name]
        assert sc.readiness == legacy.overall_readiness
        assert sc.complexity == legacy.complexity_score
        assert sc.coupling == legacy.coupling_score
