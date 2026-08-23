"""
Workspace Dependency Resolver.

Purpose:
    Resolve dependency graph targets against the existing workspace inventory.

Responsibilities:
    - Match target identifiers to existing workspace files.
    - Preserve nested workspace paths if the inventory provides them.
    - Provide a deterministic resolution outcome.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.analysis.dependencies.graph import DependencyGraph
from app.workspace.models import FileType, ScannedFile, WorkspaceInventory

__all__ = [
    "DependencyResolution",
    "ResolutionStatus",
    "WorkspaceDependencyResolver",
]


class ResolutionStatus(Enum):
    """Status of a dependency target resolution."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class DependencyResolution:
    """
    Immutable result of resolving a dependency target.

    Attributes:
        target: The original dependency target identifier.
        status: The outcome of the resolution attempt.
        resolved_file: The matched workspace file, if uniquely resolved.
    """

    target: str
    status: ResolutionStatus
    resolved_file: Optional[ScannedFile] = None


class WorkspaceDependencyResolver:
    """
    Resolves dependency targets against a workspace inventory.
    """

    def resolve(
        self,
        graph: DependencyGraph,
        inventory: WorkspaceInventory,
    ) -> list[DependencyResolution]:
        """
        Resolve all targets present in the dependency graph.

        The source node of the graph (index 0) is not resolved. Only
        targets (subsequent nodes) are resolved. The result is returned
        deterministically in the order nodes appear in the graph.

        Args:
            graph: The immutable DependencyGraph.
            inventory: The WorkspaceInventory to match against.

        Returns:
            A deterministic list of DependencyResolution objects.
        """
        resolutions: list[DependencyResolution] = []

        # Graph nodes are already deduplicated and ordered deterministically.
        # Node 0 is the source program itself.
        if len(graph.nodes) <= 1:
            return resolutions

        for node in graph.nodes[1:]:
            target = node.identifier
            matches = self._find_matches(target, inventory)

            if not matches:
                resolutions.append(
                    DependencyResolution(
                        target=target,
                        status=ResolutionStatus.UNRESOLVED,
                    )
                )
            elif len(matches) == 1:
                resolutions.append(
                    DependencyResolution(
                        target=target,
                        status=ResolutionStatus.RESOLVED,
                        resolved_file=matches[0],
                    )
                )
            else:
                resolutions.append(
                    DependencyResolution(
                        target=target,
                        status=ResolutionStatus.AMBIGUOUS,
                    )
                )

        return resolutions

    def _find_matches(
        self, target: str, inventory: WorkspaceInventory
    ) -> list[ScannedFile]:
        """
        Find all ScannedFile records matching the target identifier.

        Matches either exact basename (case-insensitive) or basename
        without extension (case-insensitive), restricted strictly to
        valid COBOL source file candidates.
        """
        matches: list[ScannedFile] = []
        target_lower = target.lower()

        for f in inventory.files:
            # Task-055 explicitly filters out JCL and other non-COBOL types.
            if f.file_type != FileType.COBOL:
                continue

            if f.filename.lower() == target_lower:
                matches.append(f)
                continue

            stem = f.filename[: -len(f.extension)] if f.extension else f.filename
            if stem.lower() == target_lower:
                matches.append(f)

        return matches
