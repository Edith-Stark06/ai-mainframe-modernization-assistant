from app.analysis.models import AnalysisResult
from app.modernization.flow.models import Flow
from app.modernization.scoring.models import ModernizationScore


def calculate_scores(analysis: AnalysisResult, flow: Flow) -> ModernizationScore:
    """
    Calculates modernization scores based on the flow structure and analysis result.
    Deterministic output.
    """
    num_nodes = len(flow.nodes)
    num_edges = len(flow.edges)

    # Simple deterministic heuristic
    raw_complexity = num_nodes / 50.0

    if num_nodes > 0:
        raw_coupling = (num_edges / num_nodes) / 5.0
    else:
        raw_coupling = 0.0

    readiness = 1.0 - ((min(1.0, raw_complexity) + min(1.0, raw_coupling)) / 2.0)

    return ModernizationScore(
        complexity_score=raw_complexity,
        coupling_score=raw_coupling,
        overall_readiness=readiness,
        metadata={"node_count": num_nodes, "edge_count": num_edges},
    )
