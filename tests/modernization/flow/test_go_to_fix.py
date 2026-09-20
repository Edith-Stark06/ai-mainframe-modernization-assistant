"""
Regression tests for real COBOL ``GO TO`` reaching the CFG/flow pipeline
(Stage 17, following Stage 15's empty-paragraph fix and Stage 16's
PERFORM THRU fix).

Purpose:
    ``GoToStatementNode`` -> ``IRJump`` -> ``FlowGenerationVisitor.visit_jump``
    -> a deferred ``GOES_TO`` edge, resolved by the same
    :meth:`FlowGenerationVisitor.finish` logic Stage 15/16 already use for
    PERFORM, all existed and worked correctly *before* this stage -- but
    were entirely unreachable from real COBOL source, because the parser
    classified ``GO``/``GO TO`` as an unsupported statement (confirmed by
    ``tests/ir/test_ir_ast_node_coverage.py`` before this fix). Stage 17
    makes the parser produce ``GoToStatementNode`` for the single-target
    ``GO TO paragraph-name`` form (the only form in the real corpus), so
    these CFG-level behaviors -- already proven correct via hand-built IR
    in ``tests/modernization/flow/test_empty_paragraph_perform_target_fix.py``
    -- are now exercised end to end for the first time.

    No change was needed in ``FlowGenerationVisitor`` itself: ``visit_jump``
    already creates a ``GO TO <target>`` node, clears ``self._pending``
    (terminating the current path -- no accidental fallthrough), and
    defers a ``GOES_TO`` edge resolved by the exact same
    ``_resolve_target_entry`` helper PERFORM already shares (existing
    non-empty paragraph / Stage 15 empty-paragraph anchor / EXTERNAL for a
    genuinely missing target, cached so repeated targets share one node).

    Every test drives the real pipeline (source -> ``CobolLexer`` ->
    ``ProgramParser`` -> ``SemanticAnalyzer`` -> ``IRBuilder`` ->
    ``generate_flow``), matching
    ``tests/modernization/flow/test_perform_thru_fix.py``'s conventions.

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


def _goes_to_target(flow: Flow, goto_node_name: str) -> Any:
    """The GOES_TO target of the *one* node named *goto_node_name*. Use
    :func:`_goes_to_targets` when the same target is GO TO'd from more
    than one call site."""
    node = _node_by_name(flow, goto_node_name)
    edge = next(
        e for e in _edges_from(flow, node.id) if e.edge_type is EdgeType.GOES_TO
    )
    return next(n for n in flow.nodes if n.id == edge.target_id)


def _goes_to_targets(flow: Flow, goto_node_name: str) -> list[Any]:
    """The GOES_TO target of *every* node named *goto_node_name* (one
    call site each)."""
    targets = []
    for node in (n for n in flow.nodes if n.name == goto_node_name):
        edge = next(
            e for e in _edges_from(flow, node.id) if e.edge_type is EdgeType.GOES_TO
        )
        targets.append(next(n for n in flow.nodes if n.id == edge.target_id))
    assert targets, f"no GO TO node named {goto_node_name!r}"
    return targets


def _unresolved_perform_risk(result: AnalysisResult, flow: Flow) -> list[Any]:
    risks = RiskAnalyzer().analyze(result, flow)
    return [r for r in risks if r.category is RiskCategory.UNRESOLVED_PERFORM_TARGET]


# ===========================================================================
# A. Simple GO TO
# ===========================================================================


def test_simple_go_to_creates_a_goes_to_node_and_edge() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    GO TO PARA-B.\n"
        'PARA-B.\n    DISPLAY "IN-B".\n'
    )
    result, flow = _flow_for(source)
    node = _node_by_name(flow, "GO TO PARA-B")
    assert node.node_type is NodeType.PROCESS
    edges = _edges_from(flow, node.id)
    assert len(edges) == 1
    assert edges[0].edge_type is EdgeType.GOES_TO
    target = _goes_to_target(flow, "GO TO PARA-B")
    assert target.name == 'DISPLAY "IN-B"'


# ===========================================================================
# B. Target resolution
# ===========================================================================


def test_go_to_existing_nonempty_target_resolves() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    GO TO PARA-B.\n"
        'PARA-B.\n    DISPLAY "IN-B".\n'
    )
    result, flow = _flow_for(source)
    target = _goes_to_target(flow, "GO TO PARA-B")
    assert target.node_type is NodeType.PROCESS
    assert not target.id.startswith("empty_")
    assert not target.id.startswith("ext_")


def test_go_to_missing_target_resolves_external() -> None:
    source = _ID + "PROCEDURE DIVISION.\nMAIN.\n    GO TO NOT-DEFINED.\n"
    result, flow = _flow_for(source)
    target = _goes_to_target(flow, "GO TO NOT-DEFINED")
    assert target.node_type is NodeType.EXTERNAL
    assert target.id == "ext_NOT-DEFINED"


def test_go_to_empty_target_resolves_via_stage15_anchor() -> None:
    """A target paragraph whose only statement is unsupported (OPEN) has
    no representable IR statements -- it must still resolve as a real
    paragraph (Stage 15), not as EXTERNAL."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    GO TO EMPTY-PARA.\n"
        "EMPTY-PARA.\n    OPEN INPUT SOME-FILE.\n"
    )
    result, flow = _flow_for(source)
    target = _goes_to_target(flow, "GO TO EMPTY-PARA")
    assert target.node_type is NodeType.PROCESS
    assert target.id == "empty_T_EMPTY-PARA"
    assert target.name == "EMPTY-PARA (no representable statements)"


def test_repeated_go_to_target_reuses_the_same_node() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    GO TO PARA-B.\n"
        "ALSO-JUMPS.\n    GO TO PARA-B.\n"
        'PARA-B.\n    DISPLAY "IN-B".\n'
    )
    result, flow = _flow_for(source)
    goto_nodes = [n for n in flow.nodes if n.name == "GO TO PARA-B"]
    assert len(goto_nodes) == 2  # two distinct call-site nodes
    targets = _goes_to_targets(flow, "GO TO PARA-B")
    assert len(targets) == 2
    assert len({t.id for t in targets}) == 1


def test_repeated_go_to_of_an_empty_target_shares_the_cached_anchor() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    GO TO EMPTY-PARA.\n"
        "ALSO-JUMPS.\n    GO TO EMPTY-PARA.\n"
        "EMPTY-PARA.\n    OPEN INPUT SOME-FILE.\n"
    )
    result, flow = _flow_for(source)
    empty_nodes = [n for n in flow.nodes if n.id.startswith("empty_")]
    assert len(empty_nodes) == 1
    assert empty_nodes[0].id == "empty_T_EMPTY-PARA"


# ===========================================================================
# C. CFG semantics: terminating jump, no accidental fallthrough
# ===========================================================================


def test_go_to_is_terminal_no_fallthrough_to_the_next_paragraph() -> None:
    """A paragraph ending in an unconditional GO TO must not also gain a
    FALLTHROUGH edge into the next paragraph in source order."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    GO TO PARA-C.\n"
        'PARA-B.\n    DISPLAY "SKIPPED".\n'
        'PARA-C.\n    DISPLAY "TARGET".\n'
    )
    result, flow = _flow_for(source)
    node = _node_by_name(flow, "GO TO PARA-C")
    edges = _edges_from(flow, node.id)
    assert len(edges) == 1
    assert edges[0].edge_type is EdgeType.GOES_TO
    assert not any(e.edge_type is EdgeType.FALLTHROUGH for e in edges)
    # PARA-B is not reached by anything in this program at all
    para_b_node = _node_by_name(flow, 'DISPLAY "SKIPPED"')
    assert not any(e.target_id == para_b_node.id for e in flow.edges)


def test_conditional_go_to_in_both_if_branches_leaves_nothing_pending() -> None:
    """The real corpus shape: an IF whose THEN and ELSE both end in an
    unconditional GO TO. After the IF, there is nothing left to flow
    into a following statement (both paths already left unconditionally)
    -- MAIN itself contributes no FALLTHROUGH edge. (PARA-B/PARA-C each
    end in their own STOP RUN so *they* don't independently fall through
    into each other either -- isolating the assertion to MAIN's own,
    GO-TO-caused, behavior.)"""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    IF WS-FLAG = 1\n"
        "        GO TO PARA-B\n"
        "    ELSE\n"
        "        GO TO PARA-C\n"
        "    END-IF.\n"
        'PARA-B.\n    DISPLAY "B".\n    STOP RUN.\n'
        'PARA-C.\n    DISPLAY "C".\n    STOP RUN.\n'
    )
    result, flow = _flow_for(source)
    then_target = _goes_to_target(flow, "GO TO PARA-B")
    else_target = _goes_to_target(flow, "GO TO PARA-C")
    assert then_target.name == 'DISPLAY "B"'
    assert else_target.name == 'DISPLAY "C"'
    # neither the decision node nor either GO TO node has a FALLTHROUGH
    # edge -- both branches terminate unconditionally.
    assert not any(e.edge_type is EdgeType.FALLTHROUGH for e in flow.edges)


def test_conditional_go_to_in_only_the_then_branch_falls_through_on_false() -> None:
    """An IF with GO TO only in THEN (no ELSE): the FALSE path must still
    correctly reach whatever follows -- Stage-15-era fallthrough logic,
    unaffected by GO TO being newly reachable."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    IF WS-FLAG = 1\n"
        "        GO TO PARA-B\n"
        "    END-IF\n"
        '    DISPLAY "FALSE-PATH".\n'
        "    STOP RUN.\n"
        'PARA-B.\n    DISPLAY "B".\n'
    )
    result, flow = _flow_for(source)
    goto_target = _goes_to_target(flow, "GO TO PARA-B")
    assert goto_target.name == 'DISPLAY "B"'
    false_path_node = _node_by_name(flow, 'DISPLAY "FALSE-PATH"')
    decision_node = next(n for n in flow.nodes if n.node_type is NodeType.DECISION)
    assert any(
        e.source_id == decision_node.id
        and e.target_id == false_path_node.id
        and e.edge_type is EdgeType.FALSE_BRANCH
        for e in flow.edges
    )


# ===========================================================================
# D. AST -> IR: target preserved exactly
# ===========================================================================


def test_go_to_target_survives_ast_to_ir_unchanged() -> None:
    from app.ir.instructions import IRJump

    source = _ID + "PROCEDURE DIVISION.\nMAIN.\n    GO TO A-VERY-SPECIFIC-NAME.\n"
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    ctx = SemanticAnalyzer().analyse(program)
    ir = IRBuilder(context=ctx).build(program)
    block = ir.modules[0].functions[0].blocks[0]
    jumps = [i for i in block.instructions if isinstance(i, IRJump)]
    assert len(jumps) == 1
    assert jumps[0].target == "A-VERY-SPECIFIC-NAME"


# ===========================================================================
# E. Regression: programs without GO TO remain unchanged
# ===========================================================================


def test_program_without_go_to_is_unaffected() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM SUB1.\n    STOP RUN.\n"
        'SUB1.\n    DISPLAY "IN-SUB".\n'
    )
    result, flow = _flow_for(source)
    assert not any(n.name.startswith("GO TO") for n in flow.nodes)
    assert not any(e.edge_type is EdgeType.GOES_TO for e in flow.edges)
    assert not _unresolved_perform_risk(result, flow)


# ===========================================================================
# F. Real corpus: t_goto_spaghetti (the only real GO TO usage among the
# 45 sources -- confirmed by direct corpus search, not assumed)
# ===========================================================================


@pytest.fixture(scope="module")
def goto_spaghetti_result() -> AnalysisResult:
    return AnalysisService().analyze_file(SOURCES / "goto_spaghetti.cbl")


def test_real_goto_spaghetti_every_target_resolves(goto_spaghetti_result):
    flow = generate_flow(goto_spaghetti_result)
    node_by_id = {n.id: n for n in flow.nodes}
    goes_to_edges = [e for e in flow.edges if e.edge_type is EdgeType.GOES_TO]
    assert len(goes_to_edges) == 7  # one per real GO TO statement
    target_ids = {e.target_id for e in goes_to_edges}
    targets = [node_by_id[tid] for tid in target_ids]
    assert all(t.node_type is NodeType.PROCESS for t in targets)
    assert not any(t.id.startswith("ext_") for t in targets)
    assert not any(t.id.startswith("empty_") for t in targets)


def test_real_goto_spaghetti_loop_back_target_is_shared(goto_spaghetti_result):
    """2000-STAGE-ALPHA is GO TO'd from both 1000-ENTRY-POINT and (the
    loop-back from) 4000-LOOP-BACK -- both must resolve to the identical
    node."""
    flow = generate_flow(goto_spaghetti_result)
    alpha_entry = _node_by_name(flow, "ADD 10 TO ACCUMULATOR")
    incoming = {
        e.source_id
        for e in flow.edges
        if e.target_id == alpha_entry.id and e.edge_type is EdgeType.GOES_TO
    }
    assert len(incoming) == 2


def test_real_goto_spaghetti_no_fallthrough_between_paragraphs(goto_spaghetti_result):
    """Every paragraph in this source ends in either GOBACK or an
    unconditional GO TO (possibly via one IF's both branches) -- none of
    the source-order paragraph transitions should be a FALLTHROUGH edge."""
    flow = generate_flow(goto_spaghetti_result)
    assert not any(e.edge_type is EdgeType.FALLTHROUGH for e in flow.edges)


def test_real_goto_spaghetti_no_unresolved_perform_target_risk(
    goto_spaghetti_result,
):
    flow = generate_flow(goto_spaghetti_result)
    assert not _unresolved_perform_risk(goto_spaghetti_result, flow)


def test_real_goto_spaghetti_complex_control_flow_counts_goto_transfers(
    goto_spaghetti_result,
):
    """This risk detector already generically counted GOES_TO edges
    before this stage (task #110) -- now that they are reachable from
    real source, its evidence becomes accurate for the first time."""
    flow = generate_flow(goto_spaghetti_result)
    risks = RiskAnalyzer().analyze(goto_spaghetti_result, flow)
    complex_flow = next(
        r for r in risks if r.category is RiskCategory.COMPLEX_CONTROL_FLOW
    )
    assert any("7 GO TO transfer(s)" in e for e in complex_flow.evidence)
