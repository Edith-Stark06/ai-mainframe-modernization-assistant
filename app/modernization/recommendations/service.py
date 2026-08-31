from typing import List
from app.modernization.flow.models import Flow
from app.modernization.scoring.models import ModernizationScore
from app.modernization.recommendations.models import Recommendation, Priority


def generate_recommendations(
    flow: Flow, score: ModernizationScore
) -> List[Recommendation]:
    """
    Generate modernization recommendations based on Flow and ModernizationScore.
    Results are deterministically ordered.
    """
    recs = []

    if score.complexity_score >= 0.8:
        recs.append(
            Recommendation(
                id="rec_complex_high",
                title="High Complexity Detected",
                description="The module has very high complexity. Consider splitting it into smaller, focused sub-modules.",
                priority=Priority.HIGH,
            )
        )
    elif score.complexity_score >= 0.5:
        recs.append(
            Recommendation(
                id="rec_complex_med",
                title="Moderate Complexity",
                description="The module has moderate complexity. Review large functions for potential refactoring.",
                priority=Priority.MEDIUM,
            )
        )

    if score.coupling_score >= 0.7:
        recs.append(
            Recommendation(
                id="rec_coupling_high",
                title="High Coupling Detected",
                description="The module has a high number of inter-dependencies. Consider abstracting common logic.",
                priority=Priority.HIGH,
            )
        )

    if score.overall_readiness < 0.3:
        recs.append(
            Recommendation(
                id="rec_readiness_low",
                title="Low Modernization Readiness",
                description="This module requires significant refactoring before modernization.",
                priority=Priority.HIGH,
            )
        )
    elif score.overall_readiness > 0.8:
        recs.append(
            Recommendation(
                id="rec_ready",
                title="Ready for Modernization",
                description="This module is well-structured and ready for direct modernization.",
                priority=Priority.LOW,
            )
        )

    priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}

    # Sort by priority first (HIGH -> LOW), then by ID alphabetically
    recs.sort(key=lambda r: (priority_order[r.priority], r.id))

    return recs
