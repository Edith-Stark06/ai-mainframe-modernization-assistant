"""
JCL Parser (task #stage46).

Purpose:
    Build a :class:`~app.jcl.ast.JclProgram` from the
    :class:`~app.jcl.lexer.RawStatement` list :func:`app.jcl.lexer.tokenize`
    produces. Every ``JOB``/``EXEC``/``DD`` statement becomes a real AST
    node; every other recognised operation becomes a
    :class:`~app.jcl.ast.JclUnsupportedStatement` (captured whole, never
    dropped) with a diagnostic -- the same "represent what is understood,
    diagnose the rest, never fabricate or crash" discipline the COBOL
    parser follows.

Responsibilities:
    - Group statements into the job's own ``JOB`` line, each step's
      ``EXEC`` line and its following ``DD`` lines, and everything else.
    - Diagnose (never raise) a missing ``JOB`` statement, a ``DD``
      statement with no enclosing step, and any unrecognised operation.

Non-responsibilities:
    - Lexing (:mod:`app.jcl.lexer`).
    - ``PROC`` expansion, conditional JCL evaluation, symbolic parameter
      substitution -- see :mod:`app.jcl`'s own module docstring.

Dependencies:
    - app.jcl.ast -- JclDDStatement, JclJob, JclProgram, JclStep, JclUnsupportedStatement
    - app.jcl.lexer -- tokenize
    - app.jcl.models -- JclDiagnostic, JclSeverity
    - loguru -- structured logging

Examples:
    Parsing a JCL job stream::

        from app.jcl.parser import JclParser

        program, diagnostics = JclParser().parse(source)
        assert program.job is not None or diagnostics

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.jcl.ast import (
    JclDDStatement,
    JclJob,
    JclProgram,
    JclStep,
    JclUnsupportedStatement,
)
from app.jcl.lexer import tokenize
from app.jcl.models import JclDiagnostic, JclSeverity

__all__ = ["JclParser"]


class JclParser:
    """Recursive, single-pass parser for a tokenized JCL job stream."""

    def parse(self, source: str) -> tuple[JclProgram, list[JclDiagnostic]]:
        """
        Parse *source* into a :class:`~app.jcl.ast.JclProgram`.

        Args:
            source: The complete raw JCL text.

        Returns:
            A ``(program, diagnostics)`` pair. Parsing never raises for
            malformed or partial JCL -- a missing ``JOB`` statement, an
            orphaned ``DD``, or an unrecognised operation each produce a
            diagnostic instead, matching the COBOL parser's own
            recovery discipline.
        """
        statements = tokenize(source)
        diagnostics: list[JclDiagnostic] = []

        job: JclJob | None = None
        steps: list[JclStep] = []
        current_step: JclStep | None = None
        current_dds: list[JclDDStatement] = []
        unsupported: list[JclUnsupportedStatement] = []

        def _flush_step() -> None:
            nonlocal current_step
            if current_step is not None:
                steps.append(
                    JclStep(
                        name=current_step.name,
                        parameters=current_step.parameters,
                        line=current_step.line,
                        dd_statements=tuple(current_dds),
                    )
                )
            current_dds.clear()

        for stmt in statements:
            if stmt.is_comment:
                continue

            if stmt.operation is None:
                logger.debug(
                    "JclParser: null statement at line {}, no action taken.",
                    stmt.line,
                )
                continue

            op = stmt.operation

            if op == "JOB":
                if job is not None:
                    diagnostics.append(
                        JclDiagnostic(
                            code="JCL002",
                            message=(
                                f"a second 'JOB' statement at line {stmt.line} is "
                                "ignored; only the first defines this job stream"
                            ),
                            line=stmt.line,
                        )
                    )
                    continue
                job = JclJob(
                    name=stmt.name or "",
                    parameters=stmt.parameters,
                    line=stmt.line,
                )
                continue

            if op == "EXEC":
                _flush_step()
                current_step = JclStep(
                    name=stmt.name or "",
                    parameters=stmt.parameters,
                    line=stmt.line,
                )
                continue

            if op == "DD":
                if current_step is None:
                    diagnostics.append(
                        JclDiagnostic(
                            code="JCL003",
                            message=(
                                f"'DD' statement at line {stmt.line} has no "
                                "enclosing 'EXEC' step; ignored"
                            ),
                            line=stmt.line,
                        )
                    )
                    continue
                current_dds.append(
                    JclDDStatement(
                        name=stmt.name, parameters=stmt.parameters, line=stmt.line
                    )
                )
                continue

            # Recognised as a statement, but not one of the three
            # modelled kinds -- captured whole, diagnosed, never dropped.
            unsupported.append(
                JclUnsupportedStatement(
                    name=stmt.name,
                    operation=op,
                    parameters=stmt.parameters,
                    line=stmt.line,
                )
            )
            diagnostics.append(
                JclDiagnostic(
                    code="JCL100",
                    message=(
                        f"'{op}' statement at line {stmt.line} is not "
                        "represented in the AST and was skipped"
                    ),
                    line=stmt.line,
                )
            )

        _flush_step()

        if job is None:
            diagnostics.append(
                JclDiagnostic(
                    code="JCL001",
                    message="no 'JOB' statement found in this job stream",
                    line=1,
                    severity=JclSeverity.ERROR,
                )
            )

        return (
            JclProgram(job=job, steps=tuple(steps), unsupported=tuple(unsupported)),
            diagnostics,
        )
