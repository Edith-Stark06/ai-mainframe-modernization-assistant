"""
JCL Analysis Service (task #stage46).

Purpose:
    Provide :class:`JclAnalysisService` -- the production entry point
    for analysing a JCL file, mirroring
    :class:`app.analysis.service.AnalysisService`'s own role for COBOL:
    read the file, run the parser, and return a structured
    :class:`~app.jcl.models.JclAnalysisResult` that never raises for a
    malformed or partial job stream.

Responsibilities:
    - Accept a JCL file path.
    - Read it, catching and reporting file-system errors the same way
      :meth:`AnalysisService.analyze_file` does.
    - Run :class:`~app.jcl.parser.JclParser` and return its result.

Dependencies:
    - app.jcl.models -- JclAnalysisResult
    - app.jcl.parser -- JclParser
    - loguru -- structured logging
    - Python standard library (pathlib).

Examples:
    Analysing a JCL file::

        from app.jcl.service import JclAnalysisService

        result = JclAnalysisService().analyze_file("payroll.jcl")
        assert result.success or result.error is not None

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.jcl.models import JclAnalysisResult
from app.jcl.parser import JclParser

__all__ = ["JclAnalysisService"]


class JclAnalysisService:
    """Production entry point for JCL analysis."""

    def analyze_file(self, source_path: str | Path) -> JclAnalysisResult:
        """
        Analyse the JCL file at *source_path*.

        Args:
            source_path: Path to the ``.jcl`` file to analyse.

        Returns:
            A :class:`~app.jcl.models.JclAnalysisResult`. A missing or
            unreadable file produces ``success=False`` with ``error``
            set; a malformed or partial job stream never raises --
            see :meth:`~app.jcl.parser.JclParser.parse`.
        """
        path = Path(source_path)
        logger.debug("JclAnalysisService: reading JCL file '{}'.", path)

        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("JclAnalysisService: file not found: {}.", path)
            return JclAnalysisResult(
                program=None,
                success=False,
                error=FileNotFoundError(f"file not found: {path}"),
            )
        except OSError as exc:
            logger.error("JclAnalysisService: cannot read '{}': {}.", path, exc)
            return JclAnalysisResult(program=None, success=False, error=exc)

        program, diagnostics = JclParser().parse(source)
        logger.debug(
            "JclAnalysisService: parsed '{}' -- {} step(s), {} diagnostic(s).",
            path,
            len(program.steps),
            len(diagnostics),
        )
        return JclAnalysisResult(
            program=program, diagnostics=tuple(diagnostics), success=True
        )
