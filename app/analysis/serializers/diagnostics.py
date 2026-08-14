"""
Diagnostics Serializer.

Purpose:
    Convert compiler diagnostics (syntax, semantic, and backend) into
    deterministic JSON-safe Python structures without mutating the original
    objects.

Responsibilities:
    - Preserve all fields that actually exist on each diagnostic class.
    - Convert enums to JSON-safe string values.
    - Recursively serialize nested position/location objects.
    - Produce only dict/list/str/int/float/bool/None.

Non-responsibilities:
    - Modifying diagnostic objects.
    - Diagnostic deserialization.
    - Persistence or API exposure.

Dependencies:
    - :mod:`app.parser.diagnostics.recovery`   — ``SyntaxDiagnostic``,
      ``RecoveryContext``, ``SynchronisationPoint``.
    - :mod:`app.parser.semantic.diagnostics`   — ``SemanticDiagnostic``,
      ``SemanticSeverity``.
    - :mod:`app.backend.java.generator`        — ``BackendDiagnostic``,
      ``BackendSeverity``.
    - :mod:`app.analysis.serializers._common`  — shared serialization helpers.
    - Python standard library.

Examples:
    Serializing a semantic diagnostic::

        from app.analysis.serializers.diagnostics import serialize_diagnostics

        data = serialize_diagnostics([semantic_diag])
        assert data[0]["type"] == "SemanticDiagnostic"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.analysis.serializers._common import serialize_value

__all__ = ["serialize_diagnostics"]


def serialize_diagnostics(diagnostics: list[Any]) -> list[Any]:
    """
    Serialize a list of diagnostic objects into JSON-safe Python values.

    Args:
        diagnostics:
            Ordered list of diagnostic records from the parser, semantic
            analyser, or Java backend.

    Returns:
        A list of JSON-safe representations.  Each representation contains
        only dict, list, str, int, float, bool, and None values.
    """
    if not diagnostics:
        return []
    return [serialize_value(diag) for diag in diagnostics]
