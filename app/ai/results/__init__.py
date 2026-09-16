"""
AI Results Package.

Exposes models and normalization routines for deterministic AI results.
"""

from app.ai.results.models import AIArtifact, ArtifactType, NormalizedAIResult
from app.ai.results.normalization import normalize_result

__all__ = [
    "AIArtifact",
    "ArtifactType",
    "NormalizedAIResult",
    "normalize_result",
]
