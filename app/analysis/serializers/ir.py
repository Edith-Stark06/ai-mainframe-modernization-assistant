"""
IR Serializer.

Purpose:
    Convert existing IR nodes into deterministic JSON-safe Python structures
    without mutating the original objects.

Responsibilities:
    - Recursively serialize nested IR structures.
    - Preserve module/function/block relationships.
    - Preserve instruction ordering.
    - Convert enums and custom values to JSON-safe representations.
    - Produce only dict/list/str/int/float/bool/None.

Non-responsibilities:
    - Modifying IR nodes.
    - IR deserialization.
    - Persistence or API exposure.

Dependencies:
    - :mod:`app.analysis.serializers._common` — shared serialization helpers.
    - Python standard library.

Examples:
    Serializing an IR program::

        from app.analysis.serializers.ir import serialize_ir

        data = serialize_ir(ir_program)
        assert data["type"] == "IRProgram"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.analysis.serializers._common import serialize_value

__all__ = ["serialize_ir"]


def serialize_ir(node: Any) -> Any:
    """
    Serialize an IR node (or nested structure) into JSON-safe Python values.

    Args:
        node:
            An IR node, a collection of nodes, or a primitive value
            originating from the compiler's IR hierarchy.

    Returns:
        A JSON-safe representation containing only dict, list, str, int,
        float, bool, and None values.
    """
    if node is None:
        return None
    return serialize_value(node)
