from app.analysis.models import AnalysisResult
from app.modernization.flow.models import Flow, FlowNode, FlowEdge, NodeType, EdgeType
from app.modernization.scoring.models import ModernizationScore
from app.modernization.scoring.service import calculate_scores


def test_scoring_empty_flow() -> None:
    flow = Flow(id="f1", name="F1", nodes=[], edges=[])
    result = AnalysisResult(
        java_source="", backend_diagnostics=[], semantic_diagnostics=[],
        success=True, dependencies=[], error=None, ast=None, ir=None
    )
    score = calculate_scores(result, flow)
    assert score.complexity_score == 0.0
    assert score.coupling_score == 0.0
    assert score.overall_readiness == 1.0


def test_scoring_complex_flow() -> None:
    # 5 nodes, 10 edges -> 5/50 = 0.1 complexity. Coupling = (10/5)/5 = 0.4
    nodes = [FlowNode(id=f"n{i}", node_type=NodeType.PROCESS, name=f"N{i}") for i in range(5)]
    edges = [FlowEdge(id=f"e{i}", source_id="n0", target_id="n1", edge_type=EdgeType.CALLS) for i in range(10)]
    
    flow = Flow(id="f1", name="F1", nodes=nodes, edges=edges)
    result = AnalysisResult(
        java_source="", backend_diagnostics=[], semantic_diagnostics=[],
        success=True, dependencies=[], error=None, ast=None, ir=None
    )
    
    score = calculate_scores(result, flow)
    assert score.complexity_score == 0.1
    assert score.coupling_score == 0.4
    assert score.overall_readiness == 0.75


def test_scoring_boundary_values() -> None:
    # Very complex
    nodes = [FlowNode(id=f"n{i}", node_type=NodeType.PROCESS, name=f"N{i}") for i in range(100)]
    edges = [FlowEdge(id=f"e{i}", source_id="n0", target_id="n1", edge_type=EdgeType.CALLS) for i in range(1000)]
    
    flow = Flow(id="f1", name="F1", nodes=nodes, edges=edges)
    result = AnalysisResult(
        java_source="", backend_diagnostics=[], semantic_diagnostics=[],
        success=True, dependencies=[], error=None, ast=None, ir=None
    )
    
    score = calculate_scores(result, flow)
    assert score.complexity_score == 1.0
    assert score.coupling_score == 1.0
    assert score.overall_readiness == 0.0

def test_score_to_dict_and_immutability() -> None:
    score = ModernizationScore(complexity_score=0.1, coupling_score=0.2, overall_readiness=0.85)
    d = score.to_dict()
    assert d["complexity_score"] == 0.1
    assert d["coupling_score"] == 0.2
    assert d["overall_readiness"] == 0.85
    
    import pytest
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        score.complexity_score = 0.5  # type: ignore
