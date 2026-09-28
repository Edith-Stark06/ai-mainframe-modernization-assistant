"""
JCL AST Node Definitions (task #stage46).

Purpose:
    Define the immutable node types that make up a parsed JCL job
    stream's structure: the ``JOB`` statement, each ``EXEC`` step and
    its ``DD`` statements, and any statement recognised but out of this
    stage's scope (``PROC``/``PEND``, conditional JCL, ``SET``,
    ``INCLUDE``, ``OUTPUT``).

Responsibilities:
    - Provide :class:`JclJob`, :class:`JclStep`, :class:`JclDDStatement`,
      :class:`JclUnsupportedStatement`, and the top-level
      :class:`JclProgram`.
    - Carry every parameter (:class:`~app.jcl.lexer.JclParameter`) and
      source line verbatim -- nothing is dropped, even for a
      construct this stage does not deeply model.
    - Remain immutable (``frozen=True`` dataclasses), matching the
      COBOL AST's own convention.

Non-responsibilities:
    - Parsing (:mod:`app.jcl.parser`).
    - Resolving an ``EXEC PGM=``/``EXEC PROC=`` target to an actual
      COBOL program or procedure library member.

Dependencies:
    - app.jcl.lexer -- JclParameter
    - Python standard library (dataclasses).

Examples:
    Building a program node directly (normally produced by
    :class:`~app.jcl.parser.JclParser`, not constructed by hand)::

        from app.jcl.ast import JclJob, JclProgram

        program = JclProgram(job=JclJob(name="PAYROLL", parameters=(), line=1))
        assert program.job is not None

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.jcl.lexer import JclParameter

__all__ = [
    "JclDDStatement",
    "JclJob",
    "JclProgram",
    "JclStep",
    "JclUnsupportedStatement",
]


@dataclass(frozen=True)
class JclJob:
    """
    The job stream's ``//jobname JOB parameters`` statement.

    Attributes:
        name: The job name (the statement's name field).
        parameters: Every ``JOB`` parameter, verbatim.
        line: 1-based source line the ``JOB`` statement started on.
    """

    name: str
    parameters: tuple[JclParameter, ...]
    line: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "name": self.name,
            "parameters": [p.to_dict() for p in self.parameters],
            "line": self.line,
        }


@dataclass(frozen=True)
class JclDDStatement:
    """
    One ``//ddname DD parameters`` statement within a step.

    Attributes:
        name: The DD name, or ``None`` for an unnamed continuation-only
            artifact (unevidenced; kept for completeness).
        parameters: Every ``DD`` parameter, verbatim (e.g.
            ``DSN=MY.DATA.SET``, ``DISP=(NEW,CATLG,DELETE)``).
        line: 1-based source line the ``DD`` statement started on.
    """

    name: str | None
    parameters: tuple[JclParameter, ...]
    line: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "name": self.name,
            "parameters": [p.to_dict() for p in self.parameters],
            "line": self.line,
        }


@dataclass(frozen=True)
class JclUnsupportedStatement:
    """
    A recognised JCL statement this stage does not deeply model
    (``PROC``, ``PEND``, ``IF``, ``THEN``, ``ELSE``, ``ENDIF``,
    ``SET``, ``INCLUDE``, ``OUTPUT``, or any other operation keyword
    that is not ``JOB``/``EXEC``/``DD``).

    Captured whole -- name, operation, every parameter, and its source
    line -- so nothing is silently lost; it is simply not interpreted.

    Attributes:
        name: The statement's name field, or ``None``.
        operation: The operation keyword, uppercased.
        parameters: Every parameter, verbatim.
        line: 1-based source line the statement started on.
    """

    name: str | None
    operation: str
    parameters: tuple[JclParameter, ...]
    line: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "name": self.name,
            "operation": self.operation,
            "parameters": [p.to_dict() for p in self.parameters],
            "line": self.line,
        }


@dataclass(frozen=True)
class JclStep:
    """
    One job step: its ``EXEC`` statement plus every ``DD`` statement
    that follows it (up to the next ``EXEC`` or the end of the job).

    Attributes:
        name: The step name (the ``EXEC`` statement's name field).
        parameters: Every ``EXEC`` parameter (``PGM=``/``PROC=``, and
            any others such as ``PARM=``, ``COND=``).
        line: 1-based source line the ``EXEC`` statement started on.
        dd_statements: Every ``DD`` statement belonging to this step,
            in source order.
    """

    name: str
    parameters: tuple[JclParameter, ...]
    line: int
    dd_statements: tuple[JclDDStatement, ...] = field(default_factory=tuple)

    @property
    def program(self) -> str | None:
        """The step's ``PGM=`` target, or ``None`` if it runs a ``PROC=``
        (or unnamed positional procedure reference) instead."""
        for p in self.parameters:
            if p.key is not None and p.key.upper() == "PGM":
                return p.value
        return None

    @property
    def procedure(self) -> str | None:
        """The step's ``PROC=`` target (explicit keyword or bare
        positional procedure name), or ``None`` if it runs ``PGM=``
        instead."""
        for p in self.parameters:
            if p.key is not None and p.key.upper() == "PROC":
                return p.value
        if self.program is None and self.parameters:
            first = self.parameters[0]
            if first.key is None:
                return first.value
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "name": self.name,
            "parameters": [p.to_dict() for p in self.parameters],
            "line": self.line,
            "dd_statements": [d.to_dict() for d in self.dd_statements],
            "program": self.program,
            "procedure": self.procedure,
        }


@dataclass(frozen=True)
class JclProgram:
    """
    A fully parsed JCL job stream.

    Attributes:
        job: The job's own ``JOB`` statement, or ``None`` if the source
            had no recognisable ``JOB`` statement (a malformed or
            partial job stream -- captured, not rejected).
        steps: Every step, in source order.
        unsupported: Every recognised-but-unmodelled statement
            (``PROC``/``PEND``/conditional JCL/...), in source order.
    """

    job: JclJob | None
    steps: tuple[JclStep, ...] = field(default_factory=tuple)
    unsupported: tuple[JclUnsupportedStatement, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "job": self.job.to_dict() if self.job is not None else None,
            "steps": [s.to_dict() for s in self.steps],
            "unsupported": [u.to_dict() for u in self.unsupported],
        }
