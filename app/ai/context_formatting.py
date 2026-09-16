"""
Shared prompt-context formatting helpers.

Purpose:
    Deterministically format the modernization pipeline payload
    (``flow``/``score``/``recommendations``, as produced by
    ``app.modernization.*`` and attached to the RAG/AI context under the
    ``modernization_data`` key) into prompt-ready lines shared by both the
    explanation and documentation prompt builders.
"""

from typing import Any


def format_modernization_context(data: dict[str, Any]) -> list[str]:
    """
    Format a modernization pipeline payload into deterministic prompt lines.

    Args:
        data: The ``modernization_data`` dict (``ModernizationPipelineResponse``
            shape: ``{"flow": ..., "score": ..., "recommendations": [...]}``).

    Returns:
        Human-readable lines summarizing readiness and recommendations, in
        the order the backend already provides them.
    """
    lines: list[str] = []

    score = data.get("score") or {}
    if score:
        if score.get("metadata", {}).get("insufficient_data"):
            lines.append(
                "Modernization readiness: insufficient flow data was extracted "
                "to produce a meaningful score."
            )
        else:
            lines.append(
                f"Modernization readiness: {score.get('overall_readiness', 0):.2f} "
                f"(complexity: {score.get('complexity_score', 0):.2f}, "
                f"coupling: {score.get('coupling_score', 0):.2f})"
            )

    for rec in data.get("recommendations") or []:
        title = rec.get("title", "")
        priority = rec.get("priority", "INFO")
        description = rec.get("description", "")
        lines.append(f"- [{priority}] {title}: {description}")

    return lines
