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

from dataclasses import dataclass
from typing import Any, Iterable

from app.analysis.serializers._common import serialize_value
from app.parser.diagnostics.recovery import (
    SYNTAX_DIAGNOSTIC_CODES,
    SyntaxCategory,
    SyntaxDiagnostic,
    SyntaxSeverity,
)

__all__ = [
    "DiagnosticGroup",
    "group_syntax_diagnostics",
    "serialize_coverage",
    "serialize_diagnostic_groups",
    "serialize_diagnostics",
]


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


def serialize_coverage(coverage: Any | None) -> dict[str, Any] | None:
    """
    Serialize an :class:`~app.analysis.models.AnalysisCoverage`.

    Args:
        coverage:
            The coverage snapshot to serialize, or ``None`` if parsing
            did not complete far enough to measure it.

    Returns:
        A JSON-safe dict including the derived ``parse_complete`` flag
        (a property, so it is not picked up by the generic dataclass
        field serialization used elsewhere in this module), or ``None``.
        ``parse_complete`` describes parser coverage -- whether the
        parser's cursor reached every token without abandoning a region
        -- and must not be read as AST or semantic completeness; see
        :class:`~app.analysis.models.AnalysisCoverage`'s scope warning.
    """
    if coverage is None:
        return None
    data = serialize_value(coverage)
    data["parse_complete"] = coverage.parse_complete
    return data


@dataclass(frozen=True, slots=True)
class DiagnosticGroup:
    """
    Every :class:`~app.parser.diagnostics.recovery.SyntaxDiagnostic` that
    shares one diagnostic code, kept together for readability.

    This is a view over the diagnostics, not a replacement for them: it
    exists only to keep, say, sixteen ``SYN200`` "COMP-3 not represented"
    warnings from drowning out three genuine syntax errors when read by a
    person. ``occurrences`` holds every one of those sixteen records with
    its own location and message intact -- grouping never discards a
    source occurrence (task #108-07's explicit requirement).

    Attributes:
        code: The shared diagnostic code, e.g. ``"SYN200"``.
        category: The code's registered :class:`SyntaxCategory`.
        severity: The code's registered :class:`SyntaxSeverity`.
        description: The code's registered short description.
        count: ``len(occurrences)``.
        occurrences: Every diagnostic with this code, in the order
            recorded, each retaining its own source location and message.
    """

    code: str
    category: SyntaxCategory
    severity: SyntaxSeverity
    description: str
    count: int
    occurrences: list[SyntaxDiagnostic]


def group_syntax_diagnostics(
    diagnostics: Iterable[SyntaxDiagnostic],
) -> list[DiagnosticGroup]:
    """
    Group syntax diagnostics by code without discarding any occurrence.

    Args:
        diagnostics:
            The diagnostics to group.  Not mutated; each one is placed,
            unmodified, into exactly one group's ``occurrences`` list.

    Returns:
        One :class:`DiagnosticGroup` per distinct code present in
        *diagnostics*, in order of each code's first appearance.  Every
        input diagnostic appears in exactly one group's ``occurrences``,
        so ``sum(g.count for g in groups) == len(list(diagnostics))``.
    """
    by_code: dict[str, list[SyntaxDiagnostic]] = {}
    for diag in diagnostics:
        by_code.setdefault(diag.code, []).append(diag)

    groups: list[DiagnosticGroup] = []
    for code, occurrences in by_code.items():
        spec = SYNTAX_DIAGNOSTIC_CODES.get(code)
        groups.append(
            DiagnosticGroup(
                code=code,
                category=spec.category if spec else SyntaxCategory.SYNTAX_ERROR,
                severity=spec.severity if spec else SyntaxSeverity.ERROR,
                description=spec.description if spec else "",
                count=len(occurrences),
                occurrences=occurrences,
            )
        )
    return groups


def serialize_diagnostic_groups(diagnostics: list[Any]) -> list[dict[str, Any]]:
    """
    Group and serialize syntax diagnostics into JSON-safe structures.

    Args:
        diagnostics:
            The syntax diagnostics to group (see
            :func:`group_syntax_diagnostics`).

    Returns:
        One JSON-safe dict per distinct code, each with an
        ``occurrences`` list holding every matching diagnostic's full
        serialized form (via :func:`serialize_diagnostics`) -- no
        occurrence or source location is discarded by grouping.
    """
    groups = group_syntax_diagnostics(diagnostics)
    return [
        {
            "code": group.code,
            "category": group.category.value,
            "severity": group.severity.value,
            "description": group.description,
            "count": group.count,
            "occurrences": serialize_diagnostics(group.occurrences),
        }
        for group in groups
    ]
