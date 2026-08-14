"""
AST Serializer.

Purpose:
    Convert existing AST nodes into deterministic JSON-safe Python structures
    without mutating the original objects.

Responsibilities:
    - Recursively serialize nested AST nodes.
    - Preserve source position information.
    - Preserve child ordering.
    - Convert enums and custom values to JSON-safe representations.
    - Produce only dict/list/str/int/float/bool/None.

Non-responsibilities:
    - Modifying AST nodes.
    - AST deserialization.
    - Persistence or API exposure.

Dependencies:
    - :mod:`app.analysis.serializers._common` — shared serialization helpers.
    - Python standard library.

Examples:
    Serializing a program node::

        from app.analysis.serializers.ast import serialize_ast

        data = serialize_ast(program_node)
        assert data["type"] == "ProgramNode"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.analysis.serializers._common import serialize_value

__all__ = ["serialize_ast"]


def serialize_ast(node: Any) -> Any:
    """
    Serialize an AST node (or nested structure) into JSON-safe Python values.

    Args:
        node:
            An AST node, a collection of nodes, or a primitive value
            originating from the parser's AST hierarchy.

    Returns:
        A JSON-safe representation containing only dict, list, str, int,
        float, bool, and None values.
    """
    if node is None:
        return None
    return serialize_value(node)
