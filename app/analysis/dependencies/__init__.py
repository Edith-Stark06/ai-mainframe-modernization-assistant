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
from app.analysis.dependencies.resolver import (
    DependencyResolution,
    ResolutionStatus,
    WorkspaceDependencyResolver,
)
from app.analysis.dependencies.summary import DependencyAnalysisSummary

__all__ = [
    "Dependency",
    "DependencyAnalyzer",
    "DependencyAnalysisSummary",
    "DependencyGraph",
    "DependencyGraphEdge",
    "DependencyGraphNode",
    "DependencyResolution",
    "DependencyType",
    "ResolutionStatus",
    "WorkspaceDependencyResolver",
]
