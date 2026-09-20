"""
Regression tests for the ``UNRESOLVED_GO_TO_TARGET`` risk (Stage 18,
following Stage 17's real ``GO TO`` parsing).

Purpose:
    Stage 17 made real ``GO TO paragraph-name`` reach the CFG as a
    ``GOES_TO`` edge, resolved by the same ``_resolve_target_entry`` logic
    PERFORM shares (existing paragraph / Stage-15 empty-paragraph anchor /
    ``EXTERNAL`` for a paragraph that does not exist). But
    ``RiskAnalyzer._detect_unresolved_perform_targets`` only ever looked at
    ``PERFORMS`` edges, so a ``GO TO`` to a nonexistent paragraph produced
    an ``EXTERNAL`` node and a ``GOES_TO`` edge yet **no unresolved-target
    risk at all** (only ``COMPLEX_CONTROL_FLOW`` counted the edge).

    ``_detect_unresolved_go_to_targets`` mirrors the PERFORM detector for
    ``GOES_TO`` edges under a dedicated category (the PERFORM category's
    title, explanation, evidence and mitigation are PERFORM-specific, and
    the strategy analyzer sums it as "unresolved PERFORM target(s)").

    Category values are compared as *strings* throughout, so these tests
    fail on a pre-fix tree because the risk is absent -- not because a
    missing enum member raises ``AttributeError``.

    Every pipeline test drives real COBOL source (lexer -> parser ->
    semantic -> IR -> ``generate_flow`` -> ``RiskAnalyzer``); the
    detector-level tests use a hand-built ``Flow``.

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
from app.dataset.corpus import load_training_corpus
from app.ir.builder import IRBuilder
from app.modernization.flow.generator import generate_flow
from app.modernization.flow.models import (
    EdgeType,
    Flow,
    FlowEdge,
    FlowNode,
    NodeType,
)
from app.modernization.risk import RiskAnalyzer
from app.parser.lexer.lexer import CobolLexer
from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.syntax.program_parser import ProgramParser

GOTO_RISK = "UNRESOLVED_GO_TO_TARGET"
PERFORM_RISK = "UNRESOLVED_PERFORM_TARGET"
_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
SOURCES = Path("data/sources/phase6-v2")


def _pipeline(source: str) -> tuple[AnalysisResult, Flow, list[Any]]:
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
    return result, flow, RiskAnalyzer().analyze(result, flow)


def _service_pipeline(
    source: str, tmp_path: Path
) -> tuple[AnalysisResult, Flow, list[Any]]:
    """Like :func:`_pipeline` but through ``AnalysisService``, which (unlike
    the hand-assembled ``AnalysisResult`` above) also populates
    ``dependencies`` -- the input the EXTERNAL_CALL detector reads."""
    path = tmp_path / "t.cbl"
    path.write_text(source, encoding="utf-8")
    result = AnalysisService().analyze_file(path)
    flow = generate_flow(result)
    return result, flow, RiskAnalyzer().analyze(result, flow)


def _of(risks: list[Any], value: str) -> list[Any]:
    return [r for r in risks if r.category.value == value]


def _goes_to(flow: Flow) -> list[Any]:
    return [e for e in flow.edges if e.edge_type is EdgeType.GOES_TO]


def _node(flow: Flow, node_id: str) -> Any:
    return next(n for n in flow.nodes if n.id == node_id)


# ===========================================================================
# 1-3. The three target classes (Phase 2's semantic distinction)
# ===========================================================================


def test_go_to_existing_nonempty_paragraph_raises_no_unresolved_risk() -> None:
    _, flow, risks = _pipeline(
        _ID + 'PROCEDURE DIVISION.\nMAIN.\n    GO TO B.\nB.\n    DISPLAY "B".\n'
    )
    (edge,) = _goes_to(flow)
    target = _node(flow, edge.target_id)
    assert target.node_type is NodeType.PROCESS
    assert not target.id.startswith(("ext_", "empty_"))
    assert _of(risks, GOTO_RISK) == []


def test_go_to_existing_empty_paragraph_raises_no_unresolved_risk() -> None:
    """Stage 15's PROCESS anchor: the paragraph exists, it just has no
    representable statements -- not an unresolved target."""
    _, flow, risks = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    GO TO B.\nB.\n    OPEN INPUT F.\n"
    )
    (edge,) = _goes_to(flow)
    target = _node(flow, edge.target_id)
    assert target.node_type is NodeType.PROCESS
    assert target.id == "empty_T_B"
    assert _of(risks, GOTO_RISK) == []


def test_go_to_missing_paragraph_raises_an_unresolved_go_to_risk() -> None:
    _, flow, risks = _pipeline(_ID + "PROCEDURE DIVISION.\nMAIN.\n    GO TO NOWHERE.\n")
    (edge,) = _goes_to(flow)
    target = _node(flow, edge.target_id)
    assert target.node_type is NodeType.EXTERNAL
    assert target.id == "ext_NOWHERE"

    (risk,) = _of(risks, GOTO_RISK)
    assert risk.severity.value == "MEDIUM"
    assert risk.confidence == 1.0
    assert risk.occurrence_count == 1
    assert risk.title == "GO TO an unresolved target"
    assert risk.evidence == ("GO TO 'NOWHERE' (unresolved) — 1 site(s)",)
    assert risk.risk_id == "RISK-unresolved-go-to-target-001"
    assert risk.recommended_mitigation
    # a dedicated category: the PERFORM one must NOT be (mis)used for it
    assert _of(risks, PERFORM_RISK) == []


# ===========================================================================
# 4/5/11. Repeated targets, node reuse, aggregation
# ===========================================================================


def test_multiple_go_tos_to_the_same_missing_target_aggregate_into_one_risk() -> None:
    _, flow, risks = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    IF WS-A = 1\n        GO TO NOWHERE\n    END-IF\n"
        "    IF WS-A = 2\n        GO TO NOWHERE\n    END-IF\n"
        "    GO TO NOWHERE.\n"
    )
    edges = _goes_to(flow)
    assert len(edges) == 3
    # target node reuse: three call sites, ONE shared EXTERNAL node
    assert {e.target_id for e in edges} == {"ext_NOWHERE"}
    assert [n.id for n in flow.nodes if n.id.startswith("ext_")] == ["ext_NOWHERE"]
    assert len({e.source_id for e in edges}) == 3

    (risk,) = _of(risks, GOTO_RISK)
    assert risk.occurrence_count == 3
    assert risk.evidence == ("GO TO 'NOWHERE' (unresolved) — 3 site(s)",)


def test_go_tos_to_two_different_missing_targets_are_listed_sorted() -> None:
    _, _, risks = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    IF WS-A = 1\n        GO TO ZED\n    END-IF\n"
        "    IF WS-A = 2\n        GO TO ALPHA\n    END-IF\n"
        "    GO TO ALPHA.\n"
    )
    (risk,) = _of(risks, GOTO_RISK)
    assert risk.occurrence_count == 3
    assert risk.evidence == (
        "GO TO 'ALPHA' (unresolved) — 2 site(s)",
        "GO TO 'ZED' (unresolved) — 1 site(s)",
    )


def test_multiple_go_tos_to_the_same_valid_target_raise_nothing_and_share_a_node() -> (
    None
):
    _, flow, risks = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    IF WS-A = 1\n        GO TO B\n    END-IF\n"
        "    GO TO B.\n"
        'B.\n    DISPLAY "B".\n'
    )
    edges = _goes_to(flow)
    assert len(edges) == 2
    assert len({e.target_id for e in edges}) == 1  # one shared, real node
    assert not _node(flow, edges[0].target_id).id.startswith("ext_")
    assert _of(risks, GOTO_RISK) == []


def test_a_mix_of_valid_and_missing_targets_reports_only_the_missing_one() -> None:
    _, _, risks = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    IF WS-A = 1\n        GO TO B\n    END-IF\n"
        "    GO TO NOWHERE.\n"
        'B.\n    DISPLAY "B".\n'
    )
    (risk,) = _of(risks, GOTO_RISK)
    assert risk.occurrence_count == 1
    assert risk.evidence == ("GO TO 'NOWHERE' (unresolved) — 1 site(s)",)
    assert "'B'" not in " ".join(risk.evidence)


# ===========================================================================
# 6/7. PERFORM and external-CALL behavior remain unchanged
# ===========================================================================


def test_unresolved_perform_still_reports_the_perform_risk_only() -> None:
    _, _, risks = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    PERFORM NOWHERE.\n    STOP RUN.\n"
    )
    (risk,) = _of(risks, PERFORM_RISK)
    assert risk.evidence == ("PERFORM 'NOWHERE' (unresolved) — 1 site(s)",)
    assert risk.risk_id == "RISK-unresolved-perform-target-001"
    assert _of(risks, GOTO_RISK) == []


def test_unresolved_perform_and_go_to_are_reported_independently() -> None:
    _, _, risks = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    PERFORM P1.\n    GO TO P2.\n"
    )
    (perform,) = _of(risks, PERFORM_RISK)
    (goto,) = _of(risks, GOTO_RISK)
    assert perform.evidence == ("PERFORM 'P1' (unresolved) — 1 site(s)",)
    assert goto.evidence == ("GO TO 'P2' (unresolved) — 1 site(s)",)
    # each category keeps its own independent running ordinal
    assert perform.risk_id == "RISK-unresolved-perform-target-001"
    assert goto.risk_id == "RISK-unresolved-go-to-target-001"


def test_external_call_is_not_reported_as_an_unresolved_go_to(tmp_path) -> None:
    _, flow, risks = _service_pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    CALL 'EXT'.\n    STOP RUN.\n",
        tmp_path,
    )
    assert "ext_EXT" in {n.id for n in flow.nodes if n.node_type is NodeType.EXTERNAL}
    assert _goes_to(flow) == []
    assert len(_of(risks, "EXTERNAL_CALL")) == 1
    assert _of(risks, GOTO_RISK) == []


def test_external_call_and_go_to_sharing_a_name_are_still_told_apart(tmp_path) -> None:
    """``CALL 'X'`` and ``GO TO X`` (X not a paragraph) resolve to the *same*
    ``ext_X`` node id, so an EXTERNAL-node-based detector would conflate
    them. The edge type is what keeps this precise: the GO TO is reported
    once, the CALL still reported once as an external call."""
    _, flow, risks = _service_pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    CALL 'X'.\n    GO TO X.\n",
        tmp_path,
    )
    assert [n.id for n in flow.nodes if n.id.startswith("ext_")] == ["ext_X"]
    (goto,) = _of(risks, GOTO_RISK)
    assert goto.occurrence_count == 1
    (call,) = _of(risks, "EXTERNAL_CALL")
    assert call.occurrence_count == 1


# ===========================================================================
# 9/10. CFG semantics are unchanged: a GO TO still terminates the path
# ===========================================================================


def test_missing_go_to_terminates_the_path_no_edge_to_following_code() -> None:
    _, flow, _ = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    GO TO NOWHERE.\n"
        '    DISPLAY "UNREACHABLE".\n'
    )
    goto = next(n for n in flow.nodes if n.name == "GO TO NOWHERE")
    out = [e for e in flow.edges if e.source_id == goto.id]
    assert [e.edge_type for e in out] == [EdgeType.GOES_TO]
    after = next(n for n in flow.nodes if n.name == 'DISPLAY "UNREACHABLE"')
    assert not any(e.target_id == after.id for e in flow.edges)


def test_missing_go_to_does_not_fabricate_a_fallthrough_edge() -> None:
    _, flow, _ = _pipeline(
        _ID + "PROCEDURE DIVISION.\nMAIN.\n    GO TO NOWHERE.\n"
        'NEXT-PARA.\n    DISPLAY "N".\n    STOP RUN.\n'
    )
    goto = next(n for n in flow.nodes if n.name == "GO TO NOWHERE")
    assert not any(
        e.source_id == goto.id and e.edge_type is EdgeType.FALLTHROUGH
        for e in flow.edges
    )
    assert not any(e.edge_type is EdgeType.FALLTHROUGH for e in flow.edges)


# ===========================================================================
# 12. Severity / occurrence aggregation / determinism
# ===========================================================================


def test_risk_analysis_is_deterministic_for_go_to_risks() -> None:
    source = (
        _ID + "PROCEDURE DIVISION.\nMAIN.\n"
        "    IF WS-A = 1\n        GO TO ZED\n    END-IF\n    GO TO ALPHA.\n"
    )
    _, _, a = _pipeline(source)
    _, _, b = _pipeline(source)
    assert a == b


# ===========================================================================
# Detector-level tests on a hand-built Flow (edge type is what matters)
# ===========================================================================


def _hand_flow(edges: list[tuple[str, str, EdgeType]]) -> Flow:
    ids = {i for e in edges for i in (e[0], e[1])}
    nodes = [
        FlowNode(
            id=i,
            node_type=NodeType.EXTERNAL if i.startswith("ext_") else NodeType.PROCESS,
            name=i.removeprefix("ext_"),
        )
        for i in sorted(ids)
    ]
    fedges = [
        FlowEdge(id=f"e{n}", source_id=s, target_id=t, edge_type=et)
        for n, (s, t, et) in enumerate(edges)
    ]
    return Flow(id="f", name="T", nodes=nodes, edges=fedges)


def _bare_result() -> AnalysisResult:
    return AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
    )


@pytest.mark.parametrize(
    ("edge_type", "expect_go_to_risk"),
    [
        (EdgeType.GOES_TO, True),
        (EdgeType.PERFORMS, False),
        (EdgeType.CALLS, False),
        (EdgeType.FLOWS_TO, False),
        (EdgeType.FALLTHROUGH, False),
    ],
)
def test_only_a_goes_to_edge_into_an_external_node_triggers_the_risk(
    edge_type, expect_go_to_risk
) -> None:
    flow = _hand_flow([("stmt_a", "ext_X", edge_type)])
    risks = RiskAnalyzer().analyze(_bare_result(), flow)
    assert bool(_of(risks, GOTO_RISK)) is expect_go_to_risk


def test_goes_to_into_a_non_external_node_triggers_nothing() -> None:
    flow = _hand_flow([("stmt_a", "stmt_b", EdgeType.GOES_TO)])
    assert _of(RiskAnalyzer().analyze(_bare_result(), flow), GOTO_RISK) == []


def test_no_flow_means_no_go_to_risk() -> None:
    assert _of(RiskAnalyzer().analyze(_bare_result(), None), GOTO_RISK) == []


# ===========================================================================
# 8. Real corpus
# ===========================================================================


@pytest.fixture(scope="module")
def goto_spaghetti() -> tuple[AnalysisResult, Flow, list[Any]]:
    result = AnalysisService().analyze_file(SOURCES / "goto_spaghetti.cbl")
    flow = generate_flow(result)
    return result, flow, RiskAnalyzer().analyze(result, flow)


def test_real_goto_spaghetti_every_go_to_target_is_real_so_no_risk(goto_spaghetti):
    """All 7 real GO TO targets in the corpus resolve to real paragraphs
    (verified against the paragraph list, not assumed)."""
    result, flow, risks = goto_spaghetti
    names = {p.name for p in result.ast.procedure_division.paragraphs}
    edges = _goes_to(flow)
    assert len(edges) == 7
    for e in edges:
        target = _node(flow, e.target_id)
        assert target.node_type is not NodeType.EXTERNAL
    assert {_node(flow, e.target_id).id.split("_")[2] for e in edges} <= names
    assert _of(risks, GOTO_RISK) == []


def test_real_goto_spaghetti_other_risks_are_unchanged(goto_spaghetti):
    _, _, risks = goto_spaghetti
    by = {}
    for r in risks:
        by[r.category.value] = by.get(r.category.value, 0) + r.occurrence_count
    assert by == {
        "COMPLEX_CONTROL_FLOW": 10,
        "SHARED_MUTABLE_STATE": 4,
        "SYNTAX_ERROR": 1,
    }


def test_no_real_corpus_source_has_an_unresolved_go_to_target(tmp_path) -> None:
    """A whole-corpus guard: the corpus's only GO TO source resolves every
    target, so this stage must not change any source's risk output. Each
    record's own source text is analyzed (all 45, none skipped)."""
    records = load_training_corpus()
    assert len(records) == 45
    offenders = []
    for rec in records:
        path = tmp_path / f"{rec.source_id}.cbl"
        path.write_text(rec.source, encoding="utf-8")
        result = AnalysisService().analyze_file(path)
        assert result.ir is not None, rec.source_id
        flow = generate_flow(result)
        if _of(RiskAnalyzer().analyze(result, flow), GOTO_RISK):
            offenders.append(rec.source_id)
    assert offenders == []
