"""
Semantic Diagnostics.

Purpose:
    Define the immutable value types used to represent semantic errors
    detected during the analysis of a COBOL AST.

    Semantic diagnostics are distinct from *syntax* diagnostics
    (see :mod:`app.parser.diagnostics.recovery`): syntax diagnostics are
    produced by the parser when it cannot match a token stream to the
    grammar; semantic diagnostics are produced *after* a well-formed AST
    has been produced, during the analysis phase.

Responsibilities:
    - Provide :class:`SemanticSeverity` — an enumeration of diagnostic
      severity levels (currently only ERROR is emitted; the type is kept
      open for future WARNING support).
    - Provide :class:`SemanticDiagnostic` — an immutable, hashable record
      carrying a message, source position, severity, and a short
      ``code`` string that identifies the rule that was violated.
    - Maintain :data:`DIAGNOSTIC_CODES` — the registry of all known codes:

      ========  =====================================================
      Code      Description
      ========  =====================================================
      SEM001    Duplicate variable declaration
      SEM002    Duplicate paragraph declaration
      SEM003    Undefined variable reference
      SEM004    Undefined paragraph reference
      SEM005    Undefined section reference
      SEM006    Missing or empty PROGRAM-ID
      SEM007    Empty PROCEDURE DIVISION
      SEM008    Reserved word used as identifier
      SEM009    Invalid static CALL target
      SEM010    Incompatible MOVE (alphanumeric source to numeric target)
      SEM011    Invalid arithmetic operand (non-numeric type)
      SEM012    Missing semantic type (variable not typed by TypeBuilder)
      SEM013    Unsupported operation on this type
      ========  =====================================================

Non-responsibilities:
    - Syntax error reporting (see :mod:`app.parser.diagnostics.recovery`).
    - Automatic correction or fix-it hints.
    - IDE integration.

Dependencies:
    - :mod:`app.parser.lexer.position` — ``Position`` value type.
    - Python standard library only (``dataclasses``, ``enum``).

Examples:
    Creating a duplicate-variable diagnostic::

        from app.parser.lexer.position import Position
        from app.parser.semantic.diagnostics import (
            SemanticDiagnostic,
            SemanticSeverity,
        )

        pos = Position(line=10, column=4, offset=200, filename="prog.cbl")
        diag = SemanticDiagnostic(
            message="duplicate variable 'WS-COUNT'",
            position=pos,
            severity=SemanticSeverity.ERROR,
            code="SEM001",
        )
        str(diag)  # "prog.cbl:10:4 [ERROR SEM001] duplicate variable 'WS-COUNT'"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.parser.lexer.position import Position

__all__ = [
    "SemanticDiagnostic",
    "SemanticSeverity",
]

# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

# Diagnostic codes — extend this mapping as new rules are added.
#: Registered diagnostic codes and their human-readable descriptions.
DIAGNOSTIC_CODES: dict[str, str] = {
    # Symbol-collection pass (TASK-018 / TASK-019)
    "SEM001": "Duplicate variable declaration",
    "SEM002": "Duplicate paragraph declaration",
    # Reference-resolution pass (TASK-020)
    "SEM003": "Undefined variable reference",
    "SEM004": "Undefined paragraph reference",
    "SEM005": "Undefined section reference",
    # Semantic-validation pass (TASK-021)
    "SEM006": "Missing or empty PROGRAM-ID",
    "SEM007": "Empty PROCEDURE DIVISION",
    "SEM008": "Reserved word used as identifier",
    "SEM009": "Invalid static CALL target",
    # Type-checking pass (TASK-023)
    "SEM010": "Incompatible MOVE (alphanumeric source to numeric target)",
    "SEM011": "Invalid arithmetic operand (non-numeric type)",
    "SEM012": "Missing semantic type (variable not typed by TypeBuilder)",
    "SEM013": "Unsupported operation on this type",
}


@unique
class SemanticSeverity(Enum):
    """
    Severity level of a :class:`SemanticDiagnostic`.

    Only ``ERROR`` is currently emitted by the analyser.  ``WARNING`` is
    reserved for future use (e.g. unreferenced variables).

    Attributes:
        ERROR:
            A condition that violates a COBOL semantic rule.  The program
            may still be parseable but is not correct.
        WARNING:
            A condition that is suspicious but not necessarily incorrect.
            Reserved for future use.

    Examples:
        >>> SemanticSeverity.ERROR.value
        'error'
    """

    ERROR = "error"
    WARNING = "warning"


# ---------------------------------------------------------------------------
# Diagnostic value type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SemanticDiagnostic:
    """
    An immutable record of a single semantic error or warning.

    :class:`SemanticDiagnostic` is a pure value type that carries no
    references to mutable parser state and can be safely serialised,
    stored in sets, or compared for equality.

    Attributes:
        message:
            Human-readable description of the semantic issue.
        position:
            The source position (line, column, offset, filename) of the
            offending construct.
        severity:
            The :class:`SemanticSeverity` level.
        code:
            A short rule identifier (e.g. ``"SEM001"``).  Codes are
            defined in :data:`DIAGNOSTIC_CODES`.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=10, column=4, offset=200, filename="p.cbl")
        >>> d = SemanticDiagnostic(
        ...     message="duplicate variable 'WS-COUNT'",
        ...     position=pos,
        ...     severity=SemanticSeverity.ERROR,
        ...     code="SEM001",
        ... )
        >>> d.severity is SemanticSeverity.ERROR
        True
        >>> "WS-COUNT" in str(d)
        True
    """

    message: str
    position: Position
    severity: SemanticSeverity
    code: str

    def __str__(self) -> str:
        """
        Return a human-readable one-line representation.

        Format::

            <filename>:<line>:<column> [<SEVERITY> <code>] <message>

        Returns:
            A formatted diagnostic string.
        """
        pos = self.position
        sev = self.severity.value.upper()
        return (
            f"{pos.filename}:{pos.line}:{pos.column} [{sev} {self.code}] {self.message}"
        )
