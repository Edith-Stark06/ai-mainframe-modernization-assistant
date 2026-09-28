"""
JCL Diagnostic and Result Models (task #stage46).

Purpose:
    Define the small, self-contained diagnostic and result types
    :mod:`app.jcl.parser` and :mod:`app.jcl.service` return -- the JCL
    analogue of :mod:`app.parser.diagnostics.recovery` and
    :mod:`app.analysis.models`, scaled down to match JCL's much simpler
    grammar (no multi-pass recovery manager is needed; a JCL statement
    either parses as one of the three modelled kinds or is captured
    whole as unsupported -- there is no equivalent of a COBOL clause
    partially consuming the wrong tokens).

Responsibilities:
    - :class:`JclSeverity` -- diagnostic severity levels.
    - :class:`JclDiagnostic` -- one diagnostic (code, message, line,
      severity).
    - :class:`JclAnalysisResult` -- the structured outcome of analysing
      one JCL file: its AST (when parsing succeeded at all), every
      diagnostic, and a success flag.

Dependencies:
    - app.jcl.ast -- JclProgram
    - Python standard library (dataclasses, enum).

Examples:
    Inspecting an analysis result::

        from app.jcl.service import JclAnalysisService

        result = JclAnalysisService().analyze_file("payroll.jcl")
        assert result.success or result.error is not None

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.jcl.ast import JclProgram

__all__ = ["JclAnalysisResult", "JclDiagnostic", "JclSeverity"]


class JclSeverity(Enum):
    """Diagnostic severity levels for JCL analysis."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class JclDiagnostic:
    """
    One diagnostic raised while analysing a JCL job stream.

    Attributes:
        code: A short, stable code (e.g. ``"JCL001"``) identifying the
            diagnostic's kind, for programmatic filtering.
        message: A human-readable description.
        line: 1-based source line the diagnostic refers to.
        severity: :class:`JclSeverity`.
    """

    code: str
    message: str
    line: int
    severity: JclSeverity = JclSeverity.WARNING


@dataclass(frozen=True)
class JclAnalysisResult:
    """
    The structured outcome of analysing one JCL file.

    Attributes:
        program: The parsed :class:`~app.jcl.ast.JclProgram`, or
            ``None`` if analysis failed before any AST could be built
            (e.g. the file could not be read).
        diagnostics: Every :class:`JclDiagnostic` raised, in the order
            recorded.
        success: ``True`` if the file was read and parsed without a
            fatal error -- independent of whether every statement was
            fully understood; see ``diagnostics`` for that.
        error: The exception that caused a fatal failure, or ``None``.
    """

    program: JclProgram | None
    diagnostics: tuple[JclDiagnostic, ...] = field(default_factory=tuple)
    success: bool = True
    error: Exception | None = None
