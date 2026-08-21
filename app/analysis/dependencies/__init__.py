"""
Dependency Analysis Module.

Provides deterministic extraction of COBOL dependencies (COPY, CALL, PERFORM)
from the existing parsed representation.
"""

from app.analysis.dependencies.models import Dependency, DependencyType
from app.analysis.dependencies.analyzer import DependencyAnalyzer

__all__ = [
    "Dependency",
    "DependencyType",
    "DependencyAnalyzer",
]
