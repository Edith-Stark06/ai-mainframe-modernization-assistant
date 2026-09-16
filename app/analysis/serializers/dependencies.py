"""
Dependencies Serializer.

Purpose:
    Convert extracted dependencies into deterministic JSON-safe Python structures.

Responsibilities:
    - Serialize a list of Dependency objects.
    - Convert DependencyType enums to their string values.
    - Preserve source position using existing position serialization.

Dependencies:
    - :mod:`app.analysis.serializers._common` — shared serialization helpers.
"""

from __future__ import annotations

from typing import Any

from app.analysis.serializers._common import serialize_value

__all__ = ["serialize_dependencies"]


def serialize_dependencies(dependencies: list[Any]) -> list[dict[str, Any]]:
    """
    Serialize a list of dependencies into JSON-safe structures.

    Args:
        dependencies: A list of :class:`~app.analysis.dependencies.models.Dependency` objects.

    Returns:
        A list of JSON-safe dicts representing the dependencies.
    """
    if not dependencies:
        return []
    return [serialize_value(dep) for dep in dependencies]
