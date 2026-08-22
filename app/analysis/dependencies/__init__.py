"""
Dependency Analysis Module.

Provides deterministic extraction of COBOL dependencies (COPY, CALL, PERFORM)
from the existing parsed representation, and in-memory dependency graph
construction from extracted dependencies.
"""

from app.analysis.dependencies.analyzer import DependencyAnalyzer
from app.analysis.dependencies.graph import (
    DependencyGraph,
    DependencyGraphEdge,
    DependencyGraphNode,
)
from app.analysis.dependencies.models import Dependency, DependencyType

__all__ = [
    "Dependency",
    "DependencyAnalyzer",
    "DependencyGraph",
    "DependencyGraphEdge",
    "DependencyGraphNode",
    "DependencyType",
]
