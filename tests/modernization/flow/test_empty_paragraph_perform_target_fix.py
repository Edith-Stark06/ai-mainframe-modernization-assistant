"""
Regression tests for the CFG/flow generator's incorrect treatment of an
existing but statement-empty ``PERFORM``/``GO TO`` target (Stage 15,
following the ``READ ... AT END`` parsing fix).

Purpose:
    ``FlowGenerationVisitor`` discovers a paragraph's existence (and its
    CFG entry node) purely from IR *instructions* -- ``_known_paragraphs``
    is built from ``{i.paragraph for i in block.instructions}`` and
    ``_paragraph_entry`` is populated only inside ``_new_node`` (i.e. only
    when a CFG node is actually created for one of that paragraph's
    statements). A paragraph whose only statement is one the parser cannot
    lower to IR (``READ``, ``OPEN``, ``WRITE``, ...) therefore produces
    *zero* instructions and is entirely invisible to the visitor -- a
    ``PERFORM``/``GO TO`` reaching it fell into the "target does not exist"
    branch of :meth:`FlowGenerationVisitor.finish`, creating a synthetic
    ``EXTERNAL`` node exactly as it would for a paragraph that genuinely
    does not exist in the program. This fed a false
    ``UNRESOLVED_PERFORM_TARGET`` risk finding.

    The fix threads the real PROCEDURE DIVISION paragraph name set (from
    the AST, not the IR) into the visitor. When a deferred edge's target
    has no IR-derived entry node but *is* one of those real paragraph
    names, a single, cached, ``NodeType.PROCESS`` "no representable
    statements" anchor node is used instead of an ``EXTERNAL`` one -- a
    structural CFG placeholder, not a fabricated executable statement. A
    target that matches no real paragraph at all is still, exactly as
    before, reported ``EXTERNAL``/unresolved.

    Every test drives the real pipeline (source -> ``CobolLexer`` ->
    ``ProgramParser`` -> ``SemanticAnalyzer`` -> ``IRBuilder`` ->
    ``generate_flow``), matching
    ``tests/modernization/flow/test_control_flow_graph.py``'s conventions.

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
from app.ir.blocks import IRBasicBlock
from app.ir.builder import IRBuilder
from app.ir.instructions import IRJump
from app.ir.program import IRFunction, IRModule, IRProgram
from app.ir.visitors import traverse_ir
from app.modernization.flow.generator import FlowGenerationVisitor, generate_flow
from app.modernization.flow.models import EdgeType, Flow, NodeType
from app.modernization.risk import RiskAnalyzer, RiskCategory
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
SOURCES = Path("data/sources/phase6-v2")


def _flow_for(source: str) -> Flow:
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
    return generate_flow(result)


def _node_by_name(flow: Flow, name: str) -> Any:
    matches = [n for n in flow.nodes if n.name == name]
    assert len(matches) == 1, f"expected exactly one node named {name!r}, got {matches}"
    return matches[0]


def _edges_from(flow: Flow, source_id: str) -> list[Any]:
    return [e for e in flow.edges if e.source_id == source_id]


def _performs_target(flow: Flow, perform_node_name: str) -> Any:
    """The PERFORMS target of the *one* node named *perform_node_name*.
    Use :func:`_performs_targets` when the same paragraph is PERFORMed
    from more than one call site (as in the real corpus)."""
    perform_node = _node_by_name(flow, perform_node_name)
    edge = next(
        e
        for e in _edges_from(flow, perform_node.id)
        if e.edge_type is EdgeType.PERFORMS
    )
    return next(n for n in flow.nodes if n.id == edge.target_id)


def _performs_targets(flow: Flow, perform_node_name: str) -> list[Any]:
    """The PERFORMS target of *every* node named *perform_node_name*
    (one COBOL paragraph performed from several call sites lowers to one
    such node per call site, all sharing that same rendered name)."""
    targets = []
    for perform_node in (n for n in flow.nodes if n.name == perform_node_name):
        edge = next(
            e
            for e in _edges_from(flow, perform_node.id)
            if e.edge_type is EdgeType.PERFORMS
        )
        targets.append(next(n for n in flow.nodes if n.id == edge.target_id))
    assert targets, f"no PERFORM node named {perform_node_name!r}"
    return targets


# ===========================================================================
# A. Existing non-empty target remains resolved
# ===========================================================================


def test_perform_of_a_nonempty_paragraph_is_unaffected() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM SUB1.\n    STOP RUN.\n"
        'SUB1.\n    DISPLAY "IN-SUB".\n'
    )
    flow = _flow_for(source)
    target = _performs_target(flow, "PERFORM SUB1")
    assert target.node_type is NodeType.PROCESS
    assert target.name == 'DISPLAY "IN-SUB"'
    assert not target.id.startswith("empty_")
    assert not target.id.startswith("ext_")


# ===========================================================================
# B. Existing empty target is resolved, not UNRESOLVED_PERFORM_TARGET
# ===========================================================================


class TestExistingEmptyTarget:
    """A paragraph whose only statement is unsupported (READ/OPEN/...)."""

    def _source(self, verb_body: str) -> str:
        return (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM EMPTY-PARA.\n    STOP RUN.\n"
            f"EMPTY-PARA.\n{verb_body}\n"
        )

    def test_read_only_paragraph_resolves_to_a_process_node(self) -> None:
        flow = _flow_for(
            self._source(
                "    READ SOME-FILE\n        AT END DISPLAY 'EOF'\n    END-READ.\n"
            )
        )
        target = _performs_target(flow, "PERFORM EMPTY-PARA")
        assert target.node_type is NodeType.PROCESS
        assert target.id == "empty_T_EMPTY-PARA"
        assert target.name == "EMPTY-PARA (no representable statements)"

    def test_open_only_paragraph_resolves_to_a_process_node(self) -> None:
        flow = _flow_for(self._source("    OPEN INPUT SOME-FILE.\n"))
        target = _performs_target(flow, "PERFORM EMPTY-PARA")
        assert target.node_type is NodeType.PROCESS

    def test_no_unresolved_perform_target_risk_is_raised(self) -> None:
        source = self._source(
            "    READ SOME-FILE\n        AT END DISPLAY 'EOF'\n    END-READ.\n"
        )
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
        flow = generate_flow(result)
        risks = RiskAnalyzer().analyze(result, flow)
        assert not [
            r for r in risks if r.category is RiskCategory.UNRESOLVED_PERFORM_TARGET
        ]

    def test_multiple_performs_of_the_same_empty_paragraph_share_one_node(
        self,
    ) -> None:
        """Two different PERFORMs of the same empty paragraph must resolve
        to the identical cached node, not two separate ones."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    PERFORM EMPTY-PARA.\n"
            "    PERFORM EMPTY-PARA.\n"
            "    STOP RUN.\n"
            "EMPTY-PARA.\n"
            "    OPEN INPUT SOME-FILE.\n"
        )
        flow = _flow_for(source)
        empty_nodes = [n for n in flow.nodes if n.id.startswith("empty_")]
        assert len(empty_nodes) == 1
        perform_nodes = [n for n in flow.nodes if n.name == "PERFORM EMPTY-PARA"]
        assert len(perform_nodes) == 2
        targets = {
            e.target_id
            for n in perform_nodes
            for e in _edges_from(flow, n.id)
            if e.edge_type is EdgeType.PERFORMS
        }
        assert targets == {empty_nodes[0].id}

    def test_go_to_an_empty_paragraph_also_resolves(self) -> None:
        """GO TO shares the same deferred-edge resolution as PERFORM (both
        produce a ``_DeferredEdge`` resolved by the same code in
        :meth:`FlowGenerationVisitor.finish`). At the time this test was
        written, ``GO TO`` was unsupported at the *parser* level (a
        separate, pre-existing, then-out-of-scope gap, confirmed directly:
        a source with only ``GO TO X.`` produced zero AST statements), so
        this exercised the generator's own ``GOES_TO`` resolution directly
        with hand-built IR, the same way
        ``tests/modernization/flow/test_generator.py`` tests the pre-#110
        call graph, rather than assuming the real pipeline could reach it.
        That parser gap is now fixed (task #stage17,
        docs/MMIM_GO_TO_FIX.md); this hand-built-IR test is kept as a
        lower-level unit test of :meth:`FlowGenerationVisitor.finish`
        itself, and the equivalent real-pipeline scenario is covered by
        ``tests/modernization/flow/test_go_to_fix.py``."""
        jump = IRJump(target="EMPTY-PARA", paragraph="MAIN")
        bb = IRBasicBlock(label="L1", instructions=(jump,))
        func = IRFunction(name="__entry__", blocks=(bb,))
        prog = IRProgram(name="T", modules=(IRModule(name="T", functions=(func,)),))

        visitor = FlowGenerationVisitor({}, real_paragraphs={"MAIN", "EMPTY-PARA"})
        traverse_ir(prog, visitor)
        visitor.finish()

        goto_node = next(
            n for n in visitor.nodes.values() if n.name == "GO TO EMPTY-PARA"
        )
        edge = next(
            e
            for e in visitor.edges
            if e.source_id == goto_node.id and e.edge_type is EdgeType.GOES_TO
        )
        target = visitor.nodes[edge.target_id]
        assert target.node_type is NodeType.PROCESS
        assert not target.id.startswith("ext_")
        assert target.id == "empty_T_EMPTY-PARA"


# ===========================================================================
# C. Missing target remains unresolved
# ===========================================================================


def test_perform_target_not_defined_is_still_external() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM MISSING-PARA.\n    STOP RUN.\n"
    )
    flow = _flow_for(source)
    target = _performs_target(flow, "PERFORM MISSING-PARA")
    assert target.node_type is NodeType.EXTERNAL
    assert target.id == "ext_MISSING-PARA"


def test_missing_target_still_raises_unresolved_perform_target_risk() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM MISSING-PARA.\n    STOP RUN.\n"
    )
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
    flow = generate_flow(result)
    risks = RiskAnalyzer().analyze(result, flow)
    matches = [r for r in risks if r.category is RiskCategory.UNRESOLVED_PERFORM_TARGET]
    assert len(matches) == 1
    assert matches[0].occurrence_count == 1


def test_existing_nonempty_and_missing_targets_in_the_same_program() -> None:
    """A defensive mix: the fix must not blur the two cases together."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM REAL-PARA.\n"
        "    PERFORM MISSING-PARA.\n"
        "    STOP RUN.\n"
        'REAL-PARA.\n    DISPLAY "X".\n'
    )
    flow = _flow_for(source)
    real_target = _performs_target(flow, "PERFORM REAL-PARA")
    missing_target = _performs_target(flow, "PERFORM MISSING-PARA")
    assert real_target.node_type is NodeType.PROCESS
    assert missing_target.node_type is NodeType.EXTERNAL


# ===========================================================================
# D. Real corpus: t_batch_acct_update
# ===========================================================================


@pytest.fixture(scope="module")
def batch_acct_result():
    return AnalysisService().analyze_file(SOURCES / "batch_acct_update.cbl")


def test_real_batch_acct_update_empty_targets_resolve(batch_acct_result):
    """``2000-READ-RECORD`` is PERFORMed from two call sites
    (``0000-PROCESS-ACCOUNTS`` and ``3000-PROCESS-LOOP``); both must
    resolve, to the identical shared node.

    ``1000-OPEN-FILES`` is included here too, but is no longer *empty*
    (task #stage25, docs/MMIM_NEGATED_COMPARISON_FIX.md): its
    ``IF WS-FILE-STATUS NOT = '00'`` used to fail to parse at all (dropped
    by recovery, leaving the paragraph with no representable statements --
    hence a ``PROCESS`` anchor node), so its expected node type is now
    ``DECISION`` -- the real ``IF`` -- while everything else about how its
    PERFORM call sites resolve is unchanged."""
    flow = generate_flow(batch_acct_result)
    for para, expected_sites, expected_type in (
        ("1000-OPEN-FILES", 1, NodeType.DECISION),
        ("2000-READ-RECORD", 2, NodeType.PROCESS),
    ):
        targets = _performs_targets(flow, f"PERFORM {para}")
        assert len(targets) == expected_sites, para
        for target in targets:
            assert target.node_type is expected_type, para
            assert not target.id.startswith("ext_"), para
        assert len({t.id for t in targets}) == 1, f"{para}: not sharing one node"


def test_real_batch_acct_update_no_unresolved_perform_target_risk(
    batch_acct_result,
):
    flow = generate_flow(batch_acct_result)
    risks = RiskAnalyzer().analyze(batch_acct_result, flow)
    assert not [
        r for r in risks if r.category is RiskCategory.UNRESOLVED_PERFORM_TARGET
    ]


def test_real_batch_acct_update_nonempty_perform_targets_still_resolve_normally(
    batch_acct_result,
):
    """3000-PROCESS-LOOP and 3100-APPLY-ACCOUNT-RULES have real statements
    and must keep resolving exactly as before -- unaffected by the fix."""
    flow = generate_flow(batch_acct_result)
    for para, first_stmt in (("3100-APPLY-ACCOUNT-RULES", "MOVE 0.00 TO WS-CALC-FEE"),):
        target = _performs_target(flow, f"PERFORM {para}")
        assert target.name == first_stmt


def test_real_batch_acct_update_paragraph_and_node_counts_are_stable(
    batch_acct_result,
):
    """Exactly the 1 expected empty-anchor node appears (was 2; task
    #stage25 made ``1000-OPEN-FILES`` no longer empty -- see
    test_real_batch_acct_update_empty_targets_resolve above); nothing else
    about the CFG shape moves."""
    flow = generate_flow(batch_acct_result)
    empty_nodes = sorted(n.name for n in flow.nodes if n.id.startswith("empty_"))
    assert empty_nodes == [
        "2000-READ-RECORD (no representable statements)",
    ]
    assert not [n for n in flow.nodes if n.id.startswith("ext_")]


# ===========================================================================
# E. PERFORM THRU
# ===========================================================================
#
# Originally this test proved that "PERFORM A THRU B" was a pre-existing,
# separate, out-of-scope parser gap (THRU/B were not consumed at all -- a
# SYN001 recovery diagnostic was raised, and only target="A" was ever
# represented). That gap is now fixed (task #stage16,
# docs/MMIM_PERFORM_THRU_FIX.md); full THRU coverage (multi-paragraph
# ranges, missing start/end targets, source-order, dedup across repeated
# PERFORM THRUs, real-corpus regression) lives in
# tests/modernization/flow/test_perform_thru_fix.py. This test is kept, in
# its original spot, updated to the new behaviour, as a regression anchor
# for the THRU + empty-paragraph interaction specifically.


def test_perform_thru_now_resolves_both_targets_including_when_one_is_empty() -> None:
    """``PERFORM A THRU B`` (task #stage16) is now fully parsed and
    resolved: both ``A`` and ``B`` get their own PERFORMS edge from the
    PERFORM's own node, and an empty target within the range (``A`` here)
    still resolves via the same Stage 15 empty-paragraph anchor node, not
    as unresolved/external."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM EMPTY-PARA THRU OTHER-PARA.\n"
        "    STOP RUN.\n"
        "EMPTY-PARA.\n"
        "    OPEN INPUT SOME-FILE.\n"
        "OTHER-PARA.\n"
        '    DISPLAY "DONE".\n'
    )
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
    flow = generate_flow(result)

    perform_nodes = [n for n in flow.nodes if n.name.startswith("PERFORM ")]
    assert len(perform_nodes) == 1
    perform_node = perform_nodes[0]
    assert perform_node.name == "PERFORM EMPTY-PARA THRU OTHER-PARA"

    # This one PERFORM THRU node has TWO PERFORMS edges (one per range
    # member) -- _performs_target/_performs_targets assume one edge per
    # node (one call site each), so the range's edges are read directly.
    node_by_id = {n.id: n for n in flow.nodes}
    targets = [
        node_by_id[e.target_id]
        for e in _edges_from(flow, perform_node.id)
        if e.edge_type is EdgeType.PERFORMS
    ]
    by_id = {t.id: t for t in targets}
    assert set(by_id) == {"empty_T_EMPTY-PARA", "stmt_T_OTHER-PARA_0"}
    assert by_id["empty_T_EMPTY-PARA"].node_type is NodeType.PROCESS
    other = by_id["stmt_T_OTHER-PARA_0"]
    assert other.node_type is NodeType.PROCESS
    assert other.name == 'DISPLAY "DONE"'

    risks = RiskAnalyzer().analyze(result, flow)
    assert not [
        r for r in risks if r.category is RiskCategory.UNRESOLVED_PERFORM_TARGET
    ]


# ===========================================================================
# Existing behaviour, explicitly re-proven unaffected
# ===========================================================================


def test_forward_referenced_perform_target_resolves() -> None:
    """Unaffected by the fix: a forward-referenced, non-empty paragraph
    still resolves via the normal IR-derived entry node, not the new
    empty-paragraph path."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM LATER-PARA.\n    STOP RUN.\n"
        "LATER-PARA.\n"
        '    DISPLAY "LATER".\n'
    )
    flow = _flow_for(source)
    target = _performs_target(flow, "PERFORM LATER-PARA")
    assert target.name == 'DISPLAY "LATER"'
    assert not target.id.startswith("empty_")


def test_nested_perform_within_a_paragraph_that_has_an_empty_target() -> None:
    """A PERFORM inside a paragraph that itself PERFORMs an empty target --
    both resolve independently and correctly."""
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    PERFORM SUB1.\n    STOP RUN.\n"
        "SUB1.\n"
        "    PERFORM EMPTY-PARA.\n"
        '    DISPLAY "AFTER".\n'
        "EMPTY-PARA.\n"
        "    OPEN INPUT SOME-FILE.\n"
    )
    flow = _flow_for(source)
    outer_target = _performs_target(flow, "PERFORM SUB1")
    assert outer_target.name == "PERFORM EMPTY-PARA"
    inner_target = _performs_target(flow, "PERFORM EMPTY-PARA")
    assert inner_target.node_type is NodeType.PROCESS
    assert inner_target.name == "EMPTY-PARA (no representable statements)"
