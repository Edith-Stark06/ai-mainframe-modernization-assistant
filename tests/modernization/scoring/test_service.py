from app.analysis.models import AnalysisResult
from app.modernization.flow.models import Flow, FlowNode, FlowEdge, NodeType, EdgeType
from app.modernization.scoring.models import ModernizationScore
from app.modernization.scoring.service import calculate_scores


def test_scoring_empty_flow() -> None:
    flow = Flow(id="f1", name="F1", nodes=[], edges=[])
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=None,
    )
    score = calculate_scores(result, flow)
    assert score.complexity_score == 0.0
    assert score.coupling_score == 0.0
    assert score.overall_readiness == 0.0
    assert score.metadata.get("insufficient_data") is True


def test_scoring_complex_flow() -> None:
    # 5 nodes, 10 edges -> 5/50 = 0.1 complexity. Coupling = (10/5)/5 = 0.4
    nodes = [
        FlowNode(id=f"n{i}", node_type=NodeType.PROCESS, name=f"N{i}") for i in range(5)
    ]
    edges = [
        FlowEdge(id=f"e{i}", source_id="n0", target_id="n1", edge_type=EdgeType.CALLS)
        for i in range(10)
    ]

    flow = Flow(id="f1", name="F1", nodes=nodes, edges=edges)
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=None,
    )

    score = calculate_scores(result, flow)
    assert score.complexity_score == 0.1
    assert score.coupling_score == 0.4
    assert score.overall_readiness == 0.75


def test_scoring_with_analysis_diagnostics() -> None:
    # 5 nodes, 10 edges -> 0.1 complexity. 2 diagnostics -> +0.10 complexity -> 0.2
    nodes = [
        FlowNode(id=f"n{i}", node_type=NodeType.PROCESS, name=f"N{i}") for i in range(5)
    ]
    edges = [
        FlowEdge(id=f"e{i}", source_id="n0", target_id="n1", edge_type=EdgeType.CALLS)
        for i in range(10)
    ]

    flow = Flow(id="f1", name="F1", nodes=nodes, edges=edges)
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[
            Exception("Semantic error 1"),
            Exception("Semantic error 2"),
        ],  # length 2
        success=False,
        dependencies=[],
        error=None,
        ast=None,
        ir=None,
    )

    score = calculate_scores(result, flow)
    assert score.complexity_score == 0.2
    assert score.coupling_score == 0.4
    assert score.overall_readiness == 0.7


def test_scoring_boundary_values() -> None:
    # Very complex
    nodes = [
        FlowNode(id=f"n{i}", node_type=NodeType.PROCESS, name=f"N{i}")
        for i in range(100)
    ]
    edges = [
        FlowEdge(id=f"e{i}", source_id="n0", target_id="n1", edge_type=EdgeType.CALLS)
        for i in range(1000)
    ]

    flow = Flow(id="f1", name="F1", nodes=nodes, edges=edges)
    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[Exception("Err")] * 50,  # very high error count
        success=False,
        dependencies=[],
        error=None,
        ast=None,
        ir=None,
    )

    score = calculate_scores(result, flow)
    assert score.complexity_score == 1.0
    assert score.coupling_score == 1.0
    assert score.overall_readiness == 0.0


def test_score_to_dict_and_immutability() -> None:
    score = ModernizationScore(
        complexity_score=0.1, coupling_score=0.2, overall_readiness=0.85
    )
    d = score.to_dict()
    assert d["complexity_score"] == 0.1
    assert d["coupling_score"] == 0.2
    assert d["overall_readiness"] == 0.85

    import pytest
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        score.complexity_score = 0.5  # type: ignore


def test_scoring_deduplicated_flow() -> None:
    from app.modernization.flow.generator import generate_flow
    from app.ir.program import IRProgram, IRModule, IRFunction
    from app.ir.blocks import IRBasicBlock
    from app.ir.instructions import IRCall

    # 10 identical calls to SUB1
    calls = tuple(IRCall(target="SUB1") for _ in range(10))
    bb1 = IRBasicBlock(label="L1", instructions=calls)
    func1 = IRFunction(name="MAIN", blocks=(bb1,))

    bb2 = IRBasicBlock(label="L2", instructions=())
    func2 = IRFunction(name="SUB1", blocks=(bb2,))

    mod = IRModule(name="MOD1", functions=(func1, func2))
    prog = IRProgram(name="PROG1", modules=(mod,))

    result = AnalysisResult(
        java_source="",
        backend_diagnostics=[],
        semantic_diagnostics=[],
        success=True,
        dependencies=[],
        error=None,
        ast=None,
        ir=prog,
    )

    flow = generate_flow(result)

    # 2 nodes, 1 logical edge (deduplicated from 10 identical calls)
    assert len(flow.nodes) == 2
    assert len(flow.edges) == 1

    score = calculate_scores(result, flow)
    # complexity: 2/50.0 = 0.04
    assert score.complexity_score == 0.04
    # coupling: (1 edge / 2 nodes) / 5.0 = 0.5 / 5.0 = 0.1
    assert score.coupling_score == 0.1
