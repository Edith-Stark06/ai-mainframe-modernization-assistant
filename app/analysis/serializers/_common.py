"""
Shared serialization helpers for the analysis serializers package.

Purpose:
    Provide small, reusable primitives for converting compiler objects into
    JSON-safe Python structures.

Responsibilities:
    - Recursively serialize dataclass instances.
    - Handle enums, collections, primitives, and None.
    - Allow callers to inject custom dataclass field visitors.

Non-responsibilities:
    - Compiler-specific type knowledge.
    - Deserialization.
    - Persistence or API exposure.

Dependencies:
    - Python standard library (``dataclasses``, ``enum``).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, Callable, Dict

DataclassVisitor = Callable[[Any], Dict[str, Any]]


def serialize_value(
    value: Any,
    dataclass_visitor: DataclassVisitor | None = None,
) -> Any:
    """
    Recursively convert *value* into a JSON-safe Python structure.

    Args:
        value:
            The value to serialize.  May be a primitive, enum, dataclass,
            list, tuple, or None.
        dataclass_visitor:
            Optional callback invoked for each dataclass instance before
            the default field-by-field serialization.  If the callback
            returns a dict, that dict is used as the serialized result;
            otherwise the default field serialization is applied.

    Returns:
        A JSON-safe representation.
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [serialize_value(item, dataclass_visitor) for item in value]
    if isinstance(value, enum.Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        if dataclass_visitor is not None:
            custom = dataclass_visitor(value)
            if isinstance(custom, dict):
                return custom
        return _serialize_dataclass_default(value, dataclass_visitor)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _serialize_dataclass_default(
    node: Any,
    dataclass_visitor: DataclassVisitor | None,
) -> dict[str, Any]:
    """Serialize a dataclass by iterating over its fields."""
    return {
        "type": type(node).__name__,
        **{
            field.name: serialize_value(getattr(node, field.name), dataclass_visitor)
            for field in dataclasses.fields(node)
        },
    }
