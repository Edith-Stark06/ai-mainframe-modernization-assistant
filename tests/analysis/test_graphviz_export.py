"""
Tests for :mod:`app.analysis.graphviz_export`.

Purpose:
    Verify :func:`to_dot` produces syntactically valid, correctly
    escaped DOT source for arbitrary node/edge input, including COBOL
    identifiers containing hyphens and quotes -- and never fabricates
    a node or edge not present in the input.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.analysis.graphviz_export import to_dot


def test_empty_graph_is_valid_dot() -> None:
    dot = to_dot(nodes=[], edges=[])
    assert dot == "digraph G {\n}\n"


def test_single_node_no_edges() -> None:
    dot = to_dot(nodes=[("MAIN", "MAIN")], edges=[])
    assert '"MAIN" [label="MAIN"];' in dot
    assert "->" not in dot


def test_node_and_edge_with_hyphenated_cobol_identifiers() -> None:
    dot = to_dot(
        nodes=[("MAIN-PARA", "MAIN-PARA"), ("SUB-PARA", "SUB-PARA")],
        edges=[("MAIN-PARA", "SUB-PARA", "PERFORM")],
    )
    assert '"MAIN-PARA" [label="MAIN-PARA"];' in dot
    assert '"SUB-PARA" [label="SUB-PARA"];' in dot
    assert '"MAIN-PARA" -> "SUB-PARA" [label="PERFORM"];' in dot


def test_edge_without_label_omits_label_attribute() -> None:
    dot = to_dot(nodes=[("A", "A"), ("B", "B")], edges=[("A", "B", "")])
    assert '"A" -> "B";' in dot
    assert "[label=" not in dot.split("->")[1]


def test_embedded_quote_in_label_is_escaped() -> None:
    dot = to_dot(nodes=[("MAIN", 'PROGRAM "X"')], edges=[])
    assert '\\"X\\"' in dot
    # A naive/unescaped quote would break DOT parsing -- verify the
    # quoted label is still bounded by exactly one pair of real quotes.
    assert 'label="PROGRAM \\"X\\""' in dot


def test_embedded_backslash_is_escaped() -> None:
    dot = to_dot(nodes=[("MAIN", "C:\\path")], edges=[])
    assert 'label="C:\\\\path"' in dot


def test_custom_graph_name_is_quoted_when_not_a_bare_identifier() -> None:
    dot = to_dot(nodes=[], edges=[], name="data-flow")
    assert dot.startswith('digraph "data-flow" {')


def test_bare_identifier_graph_name_is_not_quoted() -> None:
    dot = to_dot(nodes=[], edges=[], name="dependency_graph")
    assert dot.startswith("digraph dependency_graph {")


def test_output_starts_with_digraph_and_ends_with_closing_brace() -> None:
    dot = to_dot(nodes=[("A", "A")], edges=[])
    assert dot.startswith("digraph")
    assert dot.rstrip("\n").endswith("}")


def test_never_fabricates_nodes_beyond_input() -> None:
    dot = to_dot(nodes=[("A", "A")], edges=[("A", "B", "CALL")])
    # "B" only appears as an edge target, never declared as its own
    # node -- this module does not invent a node declaration for it;
    # DOT itself treats an undeclared endpoint as an implicit node,
    # which is standard, expected DOT behavior, not fabrication here.
    assert dot.count("[label=") == 2  # one node + one edge label
