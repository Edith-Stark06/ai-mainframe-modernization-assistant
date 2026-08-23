"""
Unit tests for the Workspace Dependency Resolver.
"""

from app.analysis.dependencies.graph import DependencyGraph
from app.analysis.dependencies.models import Dependency, DependencyType
from app.analysis.dependencies.resolver import (
    ResolutionStatus,
    WorkspaceDependencyResolver,
)
from app.parser.lexer.position import Position
from app.workspace.models import FileType, ScannedFile, WorkspaceInventory


def _pos() -> Position:
    return Position(line=1, column=1, offset=0, filename="test.cbl")


def _scanned_file(
    filename: str, file_type: FileType = FileType.COBOL, path: str = ""
) -> ScannedFile:
    ext_idx = filename.rfind(".")
    ext = filename[ext_idx:].lower() if ext_idx != -1 else ""
    return ScannedFile(
        path=path or f"/workspace/test-ws/{filename}",
        filename=filename,
        extension=ext,
        sha256="0" * 64,
        size_bytes=100,
        file_type=file_type,
    )


def test_resolve_empty_graph():
    """An empty graph produces no resolutions."""
    graph = DependencyGraph.from_dependencies("MAIN", [])
    inventory = WorkspaceInventory(workspace_id="test-ws", files=[], total_files=0)
    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)
    assert resolutions == []


def test_resolved_target_exact_match():
    """A target exactly matching a filename is RESOLVED."""
    deps = [
        Dependency(
            type=DependencyType.CALL, target="SUBPROG.cbl", source_location=_pos()
        )
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf = _scanned_file("SUBPROG.cbl")
    inventory = WorkspaceInventory(workspace_id="test-ws", files=[sf], total_files=1)

    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)

    assert len(resolutions) == 1
    assert resolutions[0].target == "SUBPROG.cbl"
    assert resolutions[0].status == ResolutionStatus.RESOLVED
    assert resolutions[0].resolved_file == sf


def test_resolved_target_stem_match():
    """A target matching a file's stem (basename without extension) is RESOLVED."""
    deps = [
        Dependency(type=DependencyType.CALL, target="CUSTOMER", source_location=_pos())
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf = _scanned_file("CUSTOMER.cbl")
    inventory = WorkspaceInventory(workspace_id="test-ws", files=[sf], total_files=1)

    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)

    assert len(resolutions) == 1
    assert resolutions[0].target == "CUSTOMER"
    assert resolutions[0].status == ResolutionStatus.RESOLVED
    assert resolutions[0].resolved_file == sf


def test_unresolved_target():
    """A target that does not match any file is UNRESOLVED."""
    deps = [
        Dependency(type=DependencyType.CALL, target="MISSING", source_location=_pos())
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf = _scanned_file("OTHER.cbl")
    inventory = WorkspaceInventory(workspace_id="test-ws", files=[sf], total_files=1)

    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)

    assert len(resolutions) == 1
    assert resolutions[0].target == "MISSING"
    assert resolutions[0].status == ResolutionStatus.UNRESOLVED
    assert resolutions[0].resolved_file is None


def test_multiple_resolved_and_unresolved_targets():
    """Multiple targets are resolved in graph node order."""
    deps = [
        Dependency(type=DependencyType.CALL, target="FOUND", source_location=_pos()),
        Dependency(
            type=DependencyType.PERFORM, target="MISSING", source_location=_pos()
        ),
        Dependency(
            type=DependencyType.CALL, target="ALSO-FOUND", source_location=_pos()
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf1 = _scanned_file("FOUND.cbl")
    sf2 = _scanned_file("ALSO-FOUND.jcl", file_type=FileType.JCL)
    inventory = WorkspaceInventory(
        workspace_id="test-ws", files=[sf1, sf2], total_files=2
    )

    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)

    assert len(resolutions) == 3
    assert resolutions[0].target == "FOUND"
    assert resolutions[0].status == ResolutionStatus.RESOLVED
    assert resolutions[0].resolved_file == sf1

    assert resolutions[1].target == "MISSING"
    assert resolutions[1].status == ResolutionStatus.UNRESOLVED

    assert resolutions[2].target == "ALSO-FOUND"
    assert resolutions[2].status == ResolutionStatus.RESOLVED
    assert resolutions[2].resolved_file == sf2


def test_nested_workspace_path():
    """The resolved file correctly preserves the nested relative path of the ScannedFile."""
    deps = [
        Dependency(type=DependencyType.CALL, target="REPORT", source_location=_pos())
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf = _scanned_file("REPORT.cbl", path="/workspace/test-ws/nested/dir/REPORT.cbl")
    inventory = WorkspaceInventory(workspace_id="test-ws", files=[sf], total_files=1)

    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)

    assert len(resolutions) == 1
    assert resolutions[0].status == ResolutionStatus.RESOLVED
    assert resolutions[0].resolved_file is not None
    assert (
        resolutions[0].resolved_file.path == "/workspace/test-ws/nested/dir/REPORT.cbl"
    )


def test_deterministic_resolution():
    """Resolution results are deterministic regardless of inventory order."""
    deps = [
        Dependency(type=DependencyType.CALL, target="A", source_location=_pos()),
        Dependency(type=DependencyType.CALL, target="B", source_location=_pos()),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf_a = _scanned_file("A.cbl")
    sf_b = _scanned_file("B.cbl")

    inv1 = WorkspaceInventory(workspace_id="test-ws", files=[sf_a, sf_b], total_files=2)
    inv2 = WorkspaceInventory(workspace_id="test-ws", files=[sf_b, sf_a], total_files=2)

    resolver = WorkspaceDependencyResolver()
    res1 = resolver.resolve(graph, inv1)
    res2 = resolver.resolve(graph, inv2)

    assert res1 == res2
    assert [r.target for r in res1] == ["A", "B"]


def test_graph_remains_unchanged():
    """The dependency graph is not mutated by the resolver."""
    deps = [Dependency(type=DependencyType.CALL, target="MOD", source_location=_pos())]
    graph = DependencyGraph.from_dependencies("MAIN", deps)
    original_nodes = list(graph.nodes)
    original_edges = list(graph.edges)

    sf = _scanned_file("MOD.cbl")
    inventory = WorkspaceInventory(workspace_id="test-ws", files=[sf], total_files=1)

    resolver = WorkspaceDependencyResolver()
    resolver.resolve(graph, inventory)

    assert list(graph.nodes) == original_nodes
    assert list(graph.edges) == original_edges


def test_shared_target_from_multiple_graph_edges():
    """Multiple edges to the same target result in one resolution (one graph node)."""
    deps = [
        Dependency(type=DependencyType.CALL, target="COMMON", source_location=_pos()),
        Dependency(
            type=DependencyType.PERFORM, target="COMMON", source_location=_pos()
        ),
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf = _scanned_file("COMMON.cbl")
    inventory = WorkspaceInventory(workspace_id="test-ws", files=[sf], total_files=1)

    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)

    # Graph has 2 nodes: MAIN, COMMON.
    # Therefore, exactly 1 target is resolved.
    assert len(resolutions) == 1
    assert resolutions[0].target == "COMMON"
    assert resolutions[0].status == ResolutionStatus.RESOLVED


def test_ambiguous_target():
    """A target matching multiple files in the inventory is AMBIGUOUS."""
    deps = [
        Dependency(type=DependencyType.CALL, target="CUSTOMER", source_location=_pos())
    ]
    graph = DependencyGraph.from_dependencies("MAIN", deps)

    sf1 = _scanned_file("CUSTOMER.cbl")
    sf2 = _scanned_file("CUSTOMER.cpy", file_type=FileType.COPYBOOK)
    inventory = WorkspaceInventory(
        workspace_id="test-ws", files=[sf1, sf2], total_files=2
    )

    resolver = WorkspaceDependencyResolver()
    resolutions = resolver.resolve(graph, inventory)

    assert len(resolutions) == 1
    assert resolutions[0].target == "CUSTOMER"
    assert resolutions[0].status == ResolutionStatus.AMBIGUOUS
    assert resolutions[0].resolved_file is None
