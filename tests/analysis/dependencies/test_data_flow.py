"""
Tests for :func:`~app.analysis.dependencies.data_flow.build_data_flow_graph`
(task #stage49).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.dependencies.data_flow import build_data_flow_graph
from app.analysis.models import AnalysisResult
from app.analysis.service import AnalysisService
from app.modernization.flow.models import EdgeType, NodeType


@pytest.fixture
def analyze(tmp_path: Path):
    def _run(source: str, name: str = "prog.cbl") -> AnalysisResult:
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        return AnalysisService().analyze_file(path)

    return _run


def test_empty_dependencies_produce_empty_graph(analyze) -> None:
    """A program with no VARIABLE_READ/WRITE dependencies yields an empty flow."""
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
    """
    result = analyze(source)
    flow = build_data_flow_graph(result)
    assert flow.nodes == ()
    assert flow.edges == ()


def test_move_produces_read_and_write_nodes_and_edges(analyze) -> None:
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SOURCE PIC 9(5) VALUE 0.
       01 WS-TARGET PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-SOURCE TO WS-TARGET.
    """
    result = analyze(source)
    flow = build_data_flow_graph(result)

    node_ids = {n.id for n in flow.nodes}
    assert "para_MAIN-PARA" in node_ids
    assert "var_WS-SOURCE" in node_ids
    assert "var_WS-TARGET" in node_ids

    para_node = next(n for n in flow.nodes if n.id == "para_MAIN-PARA")
    assert para_node.node_type is NodeType.PROCESS
    source_node = next(n for n in flow.nodes if n.id == "var_WS-SOURCE")
    assert source_node.node_type is NodeType.DATA_ITEM

    read_edges = [e for e in flow.edges if e.edge_type is EdgeType.READS]
    write_edges = [e for e in flow.edges if e.edge_type is EdgeType.WRITES]
    assert len(read_edges) == 1
    assert read_edges[0].source_id == "para_MAIN-PARA"
    assert read_edges[0].target_id == "var_WS-SOURCE"
    assert len(write_edges) == 1
    assert write_edges[0].source_id == "para_MAIN-PARA"
    assert write_edges[0].target_id == "var_WS-TARGET"


def test_two_paragraphs_produce_distinct_process_nodes(analyze) -> None:
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 0.
       01 WS-B PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       PARA-1.
           MOVE 1 TO WS-A.
       PARA-2.
           MOVE WS-A TO WS-B.
    """
    result = analyze(source)
    flow = build_data_flow_graph(result)

    para_nodes = {n.id for n in flow.nodes if n.node_type is NodeType.PROCESS}
    assert para_nodes == {"para_PARA-1", "para_PARA-2"}

    write_from_para1 = [
        e
        for e in flow.edges
        if e.source_id == "para_PARA-1" and e.edge_type is EdgeType.WRITES
    ]
    read_from_para2 = [
        e
        for e in flow.edges
        if e.source_id == "para_PARA-2" and e.edge_type is EdgeType.READS
    ]
    assert any(e.target_id == "var_WS-A" for e in write_from_para1)
    assert any(e.target_id == "var_WS-A" for e in read_from_para2)


def test_duplicate_dependency_does_not_duplicate_edge(analyze) -> None:
    """The same paragraph reading the same variable twice yields one edge, not two."""
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 0.
       01 WS-B PIC 9(5) VALUE 0.
       01 WS-C PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-A TO WS-B.
           MOVE WS-A TO WS-C.
    """
    result = analyze(source)
    flow = build_data_flow_graph(result)

    read_edges = [
        e
        for e in flow.edges
        if e.edge_type is EdgeType.READS and e.target_id == "var_WS-A"
    ]
    assert len(read_edges) == 1


def test_condition_dependencies_are_excluded(analyze) -> None:
    """An IF test on a variable is neither a READS nor a WRITES edge here."""
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-FLAG PIC 9(1) VALUE 0.
       01 WS-A PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-FLAG = 1
               MOVE 1 TO WS-A
           END-IF.
    """
    result = analyze(source)
    flow = build_data_flow_graph(result)

    assert "var_WS-FLAG" not in {n.id for n in flow.nodes}


def test_to_dict_is_json_safe(analyze) -> None:
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SOURCE PIC 9(5) VALUE 0.
       01 WS-TARGET PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-SOURCE TO WS-TARGET.
    """
    result = analyze(source)
    flow = build_data_flow_graph(result)
    d = flow.to_dict()
    assert isinstance(d["nodes"], list)
    assert isinstance(d["edges"], list)
    assert all(n["node_type"] in {"PROCESS", "DATA_ITEM"} for n in d["nodes"])
