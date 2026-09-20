"""
Regression tests for the CFG/flow generator's ``PERFORM A THRU C`` target
resolution (Stage 16, following Stage 15's empty-paragraph fix).

Purpose:
    Before this fix, ``PERFORM A THRU C`` was not parsed at all (see
    ``tests/parser/test_perform_thru_parsing_fix.py``): the parser captured
    only ``target="A"``, so ``B``/``C`` and the very existence of a range
    were entirely lost by the time IR/CFG construction ran -- a genuine
    ``PERFORM A THRU C`` was indistinguishable from a plain ``PERFORM A``.

    The fix threads ``PerformStatementNode.thru_target`` through
    ``IRCall.thru_target`` to ``FlowGenerationVisitor``, which now resolves
    a THRU range to the ordered slice of the program's *real* paragraphs
    (by physical source position, exactly as COBOL itself defines a THRU
    range -- not by paragraph naming) from the start name to the end name
    inclusive, and adds one ``PERFORMS`` edge from the PERFORM statement's
    own node to *each* paragraph's resolved entry -- reusing Stage 15's
    exact per-paragraph resolution (IR-derived entry / cached
    ``empty_<module>_<name>`` anchor / ``ext_<name>`` external), so an
    empty paragraph inside the range resolves the same way a directly
    PERFORMed one does, and a genuinely missing endpoint still resolves
    ``EXTERNAL``/unresolved rather than being silently upgraded.

    Every test drives the real pipeline (source -> ``CobolLexer`` ->
    ``ProgramParser`` -> ``SemanticAnalyzer`` -> ``IRBuilder`` ->
    ``generate_flow``), matching
    ``tests/modernization/flow/test_control_flow_graph.py`` and
    ``tests/modernization/flow/test_empty_paragraph_perform_target_fix.py``'s
    conventions.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.analysis.models import AnalysisResult
from app.analysis.service import AnalysisService
from app.ir.builder import IRBuilder
from app.modernization.flow.generator import generate_flow
from app.modernization.flow.models import EdgeType, Flow, NodeType
from app.modernization.risk import RiskAnalyzer, RiskCategory
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
SOURCES = Path("data/sources/phase6-v2")


def _flow_for(source: str) -> tuple[AnalysisResult, Flow]:
    """Run *source* through the full pipeline and build its Flow graph."""
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    ctx = SemanticAnalyzer().analyse(program)
    ir = IRBuilder(context=ctx).build(program)
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        ast=program,
        ir=ir,
    )
    return result, generate_flow(result)


def _node_by_name(flow: Flow, name: str) -> Any:
    matches = [n for n in flow.nodes if n.name == name]
    assert len(matches) == 1, f"expected exactly one node named {name!r}, got {matches}"
    return matches[0]


def _edges_from(flow: Flow, source_id: str) -> list[Any]:
    return [e for e in flow.edges if e.source_id == source_id]


def _thru_targets(flow: Flow, perform_node_name: str) -> list[Any]:
    """Every ``PERFORMS``-edge target of the *one* node named
    *perform_node_name* -- a THRU perform has one edge per paragraph in
    its resolved range, unlike a plain PERFORM's single edge."""
    node = _node_by_name(flow, perform_node_name)
    node_by_id = {n.id: n for n in flow.nodes}
    return [
        node_by_id[e.target_id]
        for e in _edges_from(flow, node.id)
        if e.edge_type is EdgeType.PERFORMS
    ]


def _unresolved_risk(result: AnalysisResult, flow: Flow) -> list[Any]:
    risks = RiskAnalyzer().analyze(result, flow)
    return [r for r in risks if r.category is RiskCategory.UNRESOLVED_PERFORM_TARGET]


# ===========================================================================
# 1. PERFORM A THRU C -- the basic case
# ===========================================================================


def test_perform_a_thru_c_resolves_both_endpoints() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    node = _node_by_name(flow, "PERFORM A THRU C")
    assert node.node_type is NodeType.PROCESS

    targets = _thru_targets(flow, "PERFORM A THRU C")
    names = {t.name for t in targets}
    assert names == {'DISPLAY "A"', 'DISPLAY "C"'}
    assert all(t.node_type is NodeType.PROCESS for t in targets)
    assert not _unresolved_risk(result, flow)


# ===========================================================================
# 2. Multiple paragraphs inside the range
# ===========================================================================


def test_multiple_paragraphs_inside_the_range_all_resolve() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU E.\n    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        'B.\n    DISPLAY "B".\n'
        'C.\n    DISPLAY "C".\n'
        'D.\n    DISPLAY "D".\n'
        'E.\n    DISPLAY "E".\n'
    )
    result, flow = _flow_for(source)
    targets = _thru_targets(flow, "PERFORM A THRU E")
    names = {t.name for t in targets}
    assert names == {
        'DISPLAY "A"',
        'DISPLAY "B"',
        'DISPLAY "C"',
        'DISPLAY "D"',
        'DISPLAY "E"',
    }
    assert not _unresolved_risk(result, flow)


def test_perform_thru_does_not_include_paragraphs_outside_the_range() -> None:
    """A paragraph physically before A or after E is not part of PERFORM A
    THRU E's range and must not receive an edge from it."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n    STOP RUN.\n"
        'BEFORE-A.\n    DISPLAY "BEFORE".\n'
        'A.\n    DISPLAY "A".\n'
        'C.\n    DISPLAY "C".\n'
        'AFTER-C.\n    DISPLAY "AFTER".\n'
    )
    result, flow = _flow_for(source)
    names = {t.name for t in _thru_targets(flow, "PERFORM A THRU C")}
    assert names == {'DISPLAY "A"', 'DISPLAY "C"'}
    assert 'DISPLAY "BEFORE"' not in names
    assert 'DISPLAY "AFTER"' not in names


# ===========================================================================
# 3. Empty paragraph inside the range
# ===========================================================================


def test_empty_paragraph_inside_the_range_resolves_as_a_real_process_node() -> None:
    """B has no representable statements (its only statement, OPEN, is
    unsupported) -- it must still resolve via Stage 15's empty-paragraph
    anchor, not be silently dropped from the range or misclassified."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        "B.\n    OPEN INPUT SOME-FILE.\n"
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    targets = _thru_targets(flow, "PERFORM A THRU C")
    by_id = {t.id: t for t in targets}
    assert "empty_T_B" in by_id
    assert by_id["empty_T_B"].node_type is NodeType.PROCESS
    assert by_id["empty_T_B"].name == "B (no representable statements)"
    assert not any(t.id.startswith("ext_") for t in targets)
    assert not _unresolved_risk(result, flow)


# ===========================================================================
# 4/5. Missing start/end target
# ===========================================================================


def test_missing_end_target_stays_external_start_still_resolves() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU NOT-DEFINED.\n    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
    )
    result, flow = _flow_for(source)
    targets = _thru_targets(flow, "PERFORM A THRU NOT-DEFINED")
    by_id = {t.id: t for t in targets}
    assert by_id["stmt_T_A_0"].node_type is NodeType.PROCESS
    assert by_id["ext_NOT-DEFINED"].node_type is NodeType.EXTERNAL

    risks = _unresolved_risk(result, flow)
    assert len(risks) == 1
    assert risks[0].occurrence_count == 1
    assert any("NOT-DEFINED" in e for e in risks[0].evidence)


def test_missing_start_target_stays_external_end_still_resolves() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM NOT-DEFINED THRU C.\n    STOP RUN.\n"
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    targets = _thru_targets(flow, "PERFORM NOT-DEFINED THRU C")
    by_id = {t.id: t for t in targets}
    assert by_id["ext_NOT-DEFINED"].node_type is NodeType.EXTERNAL
    assert by_id["stmt_T_C_0"].node_type is NodeType.PROCESS

    risks = _unresolved_risk(result, flow)
    assert len(risks) == 1
    assert risks[0].occurrence_count == 1


def test_both_targets_missing_are_each_reported_external() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM NOWHERE-A THRU NOWHERE-B.\n    STOP RUN.\n"
    )
    result, flow = _flow_for(source)
    targets = _thru_targets(flow, "PERFORM NOWHERE-A THRU NOWHERE-B")
    ids = {t.id for t in targets}
    assert ids == {"ext_NOWHERE-A", "ext_NOWHERE-B"}
    assert all(t.node_type is NodeType.EXTERNAL for t in targets)


# ===========================================================================
# 6. Ordinary PERFORM remains unchanged
# ===========================================================================


def test_ordinary_perform_is_completely_unaffected() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM SUB1.\n    STOP RUN.\n"
        'SUB1.\n    DISPLAY "IN-SUB".\n'
    )
    result, flow = _flow_for(source)
    node = _node_by_name(flow, "PERFORM SUB1")
    targets = _thru_targets(flow, "PERFORM SUB1")
    assert len(targets) == 1
    assert targets[0].name == 'DISPLAY "IN-SUB"'
    assert not _unresolved_risk(result, flow)
    # The node label carries no THRU suffix for a plain PERFORM.
    assert node.name == "PERFORM SUB1"


def test_ordinary_perform_to_a_missing_target_is_unaffected() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    PERFORM NOT-DEFINED.\n    STOP RUN.\n"
    )
    result, flow = _flow_for(source)
    risks = _unresolved_risk(result, flow)
    assert len(risks) == 1
    assert risks[0].occurrence_count == 1


# ===========================================================================
# 7. Real corpus regression: t_fallthrough_flow
# ===========================================================================
#
# `grep -ilE "PERFORM .* (THRU|THROUGH) .*" data/sources/phase6-v2/*.cbl`
# over all 45 sources finds exactly one real PERFORM THRU occurrence, in
# t_fallthrough_flow: "PERFORM 1000-STAGE-ALPHA THRU 3000-STAGE-GAMMA",
# spanning 1000-STAGE-ALPHA, 2000-STAGE-BETA, 3000-STAGE-GAMMA (all three
# have real statements -- no empty paragraph in this particular range).


@pytest.fixture(scope="module")
def fallthrough_result() -> AnalysisResult:
    return AnalysisService().analyze_file(SOURCES / "fallthrough_flow.cbl")


def test_real_fallthrough_flow_thru_range_resolves_all_three_stages(
    fallthrough_result,
):
    flow = generate_flow(fallthrough_result)
    targets = _thru_targets(flow, "PERFORM 1000-STAGE-ALPHA THRU 3000-STAGE-GAMMA")
    names = {t.name for t in targets}
    assert names == {
        "ADD 1 TO STEP-A-HIT-COUNT",
        "ADD 1 TO STEP-B-HIT-COUNT",
        "ADD 1 TO STEP-C-HIT-COUNT",
    }
    assert all(t.node_type is NodeType.PROCESS for t in targets)
    assert not any(
        t.id.startswith("ext_") or t.id.startswith("empty_") for t in targets
    )


def test_real_fallthrough_flow_no_unresolved_perform_target_risk(fallthrough_result):
    flow = generate_flow(fallthrough_result)
    assert not _unresolved_risk(fallthrough_result, flow)


def test_real_fallthrough_flow_node_and_edge_counts(fallthrough_result):
    """4 paragraphs in source -> at least 3 PERFORMS edges from the THRU
    node (one per range member) plus the ordinary sequential/return nodes;
    a basic sanity check that nothing else in the CFG collapsed."""
    flow = generate_flow(fallthrough_result)
    assert len(fallthrough_result.ast.procedure_division.paragraphs) == 4
    thru_node = _node_by_name(flow, "PERFORM 1000-STAGE-ALPHA THRU 3000-STAGE-GAMMA")
    performs_edges = [
        e for e in _edges_from(flow, thru_node.id) if e.edge_type is EdgeType.PERFORMS
    ]
    assert len(performs_edges) == 3


# ===========================================================================
# 8. Source-order preservation
# ===========================================================================


def test_range_follows_physical_source_order_not_alphabetical_name_order() -> None:
    """Z-FIRST is physically first, A-SECOND physically second: a THRU
    range from Z-FIRST to A-SECOND must resolve both (source order), and
    must NOT be reinterpreted as if sorted by name (which would reverse
    them and, under this fix's conservative reversed-range handling,
    still resolve only the two endpoints rather than fabricate a
    nonsensical walk)."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM Z-FIRST THRU A-SECOND.\n    STOP RUN.\n"
        'Z-FIRST.\n    DISPLAY "Z".\n'
        'A-SECOND.\n    DISPLAY "A".\n'
    )
    result, flow = _flow_for(source)
    targets = _thru_targets(flow, "PERFORM Z-FIRST THRU A-SECOND")
    names = {t.name for t in targets}
    assert names == {'DISPLAY "Z"', 'DISPLAY "A"'}
    assert not any(t.id.startswith("ext_") for t in targets)


def test_range_walks_paragraphs_in_the_order_they_appear_in_source() -> None:
    """The range's middle paragraph (M) is named so that it would sort
    alphabetically *outside* [A, C] if names were used for ordering; it
    must still be included because it is physically between A and C."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        'ZZZ-MIDDLE.\n    DISPLAY "MID".\n'
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    names = {t.name for t in _thru_targets(flow, "PERFORM A THRU C")}
    assert names == {'DISPLAY "A"', 'DISPLAY "MID"', 'DISPLAY "C"'}


# ===========================================================================
# 9. No duplicate nodes for repeated PERFORM THRU
# ===========================================================================


def test_repeated_perform_thru_of_the_same_range_shares_target_nodes() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n"
        "    PERFORM A THRU C.\n"
        "    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        'B.\n    DISPLAY "B".\n'
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    perform_nodes = [n for n in flow.nodes if n.name == "PERFORM A THRU C"]
    assert len(perform_nodes) == 2  # two distinct call-site nodes

    target_ids_per_call = []
    for pn in perform_nodes:
        ids = {
            e.target_id
            for e in _edges_from(flow, pn.id)
            if e.edge_type is EdgeType.PERFORMS
        }
        target_ids_per_call.append(ids)
    # Both call sites resolve to the identical three target node ids --
    # no duplicate paragraph representation was created for the second
    # PERFORM THRU.
    assert target_ids_per_call[0] == target_ids_per_call[1]
    assert len(target_ids_per_call[0]) == 3

    # Exactly one node per real paragraph exists anywhere in the flow.
    for name in ('DISPLAY "A"', 'DISPLAY "B"', 'DISPLAY "C"'):
        matches = [n for n in flow.nodes if n.name == name]
        assert len(matches) == 1, name


def test_repeated_perform_thru_with_an_empty_member_shares_the_anchor_node() -> None:
    """Same as above, but the shared range member is itself empty -- the
    cached empty_<module>_<paragraph> anchor (Stage 15) must be reused,
    not recreated, across both call sites."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n"
        "    PERFORM A THRU C.\n"
        "    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        "B.\n    OPEN INPUT SOME-FILE.\n"
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    empty_nodes = [n for n in flow.nodes if n.id.startswith("empty_")]
    assert len(empty_nodes) == 1
    assert empty_nodes[0].id == "empty_T_B"


# ===========================================================================
# 10. Risk analysis does not misreport resolved real targets
# ===========================================================================


def test_risk_analysis_reports_nothing_when_the_whole_range_resolves() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        "B.\n    OPEN INPUT SOME-FILE.\n"
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    assert not _unresolved_risk(result, flow)


def test_risk_analysis_reports_only_the_genuinely_missing_endpoint() -> None:
    """A resolved start + an unresolved end in the same PERFORM THRU must
    not cause the *resolved* endpoint to be reported too."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU NOT-DEFINED.\n    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
    )
    result, flow = _flow_for(source)
    risks = _unresolved_risk(result, flow)
    assert len(risks) == 1
    assert risks[0].occurrence_count == 1
    evidence_text = " ".join(risks[0].evidence)
    assert "NOT-DEFINED" in evidence_text
    assert "PERFORM 'A'" not in evidence_text  # the resolved paragraph never appears


def test_risk_analysis_alongside_an_unrelated_genuinely_missing_plain_perform() -> None:
    """A resolved PERFORM THRU range and a separate, genuinely unresolved
    plain PERFORM in the same program: only the plain one is reported."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM A THRU C.\n"
        "    PERFORM ALSO-MISSING.\n"
        "    STOP RUN.\n"
        'A.\n    DISPLAY "A".\n'
        'C.\n    DISPLAY "C".\n'
    )
    result, flow = _flow_for(source)
    risks = _unresolved_risk(result, flow)
    assert len(risks) == 1
    assert risks[0].occurrence_count == 1
    assert any("ALSO-MISSING" in e for e in risks[0].evidence)
