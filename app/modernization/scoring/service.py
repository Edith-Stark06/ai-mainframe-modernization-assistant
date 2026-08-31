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

    if num_nodes == 0:
        # Explicit handling of empty/insufficient data
        return ModernizationScore(
            complexity_score=0.0,
            coupling_score=0.0,
            overall_readiness=0.0,
            metadata={"node_count": 0, "edge_count": 0, "insufficient_data": True},
        )

    # Base heuristic
    raw_complexity = num_nodes / 50.0

    # Incorporate analysis signals (e.g. semantic errors indicate higher complexity to modernize)
    diag_penalty = len(analysis.semantic_diagnostics) * 0.05
    raw_complexity += diag_penalty

    raw_coupling = (num_edges / num_nodes) / 5.0

    # Ensure bounds are strictly [0.0, 1.0]
    complexity = max(0.0, min(1.0, raw_complexity))
    coupling = max(0.0, min(1.0, raw_coupling))

    raw_readiness = 1.0 - ((complexity + coupling) / 2.0)
    readiness = max(0.0, min(1.0, raw_readiness))

    return ModernizationScore(
        complexity_score=complexity,
        coupling_score=coupling,
        overall_readiness=readiness,
        metadata={
            "node_count": num_nodes,
            "edge_count": num_edges,
            "diagnostics_count": len(analysis.semantic_diagnostics),
        },
    )
