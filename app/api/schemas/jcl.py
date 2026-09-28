"""
JCL Analysis API Schemas.

Purpose:
    Define Pydantic v2 request and response models for the JCL
    analysis API endpoint -- the JCL analogue of
    :mod:`app.api.schemas.analysis`, exposing
    :class:`~app.jcl.service.JclAnalysisService`'s output (previously
    only exercised by ``tests/jcl/``) over HTTP for the first time.

Responsibilities:
    - Expose ``JclAnalysisRequest`` -- typed request schema identifying
      the ``.jcl`` file to analyze within a workspace.
    - Expose ``JclAnalysisResponse`` -- response envelope carrying the
      serialized :class:`~app.jcl.models.JclAnalysisResult`: the parsed
      job (when parsing succeeded at all), every step and its DD
      statements, every unsupported statement, and every diagnostic.

Non-responsibilities:
    - JCL lexing/parsing (delegated to :mod:`app.jcl`).
    - Cross-referencing a step's ``PGM=`` target against COBOL programs
      in the workspace (see :mod:`app.workspace.jcl_correlation`, wired
      into the modernization intelligence endpoint instead).

Dependencies:
    - pydantic -- Pydantic v2 BaseModel, Field, StringConstraints

Examples:
    Building a request::

        from app.api.schemas.jcl import JclAnalysisRequest

        request = JclAnalysisRequest(filename="payroll.jcl")

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

__all__ = [
    "JclAnalysisRequest",
    "JclAnalysisResponse",
    "JclDDStatementResponse",
    "JclDiagnosticResponse",
    "JclJobResponse",
    "JclParameterResponse",
    "JclProgramResponse",
    "JclStepResponse",
    "JclUnsupportedStatementResponse",
]


class JclAnalysisRequest(BaseModel):
    """
    Request schema for the JCL analysis endpoint.

    Attributes:
        filename:
            Basename of the ``.jcl`` file to analyze within the
            requested workspace.
    """

    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = (
        Field(..., description="The .jcl filename to analyze within the workspace.")
    )


class JclParameterResponse(BaseModel):
    """One JCL statement parameter (``key=value`` or positional)."""

    key: str | None
    value: str


class JclJobResponse(BaseModel):
    """The job stream's own ``JOB`` statement."""

    name: str
    parameters: list[JclParameterResponse]
    line: int


class JclDDStatementResponse(BaseModel):
    """One ``DD`` statement within a step."""

    name: str | None
    parameters: list[JclParameterResponse]
    line: int


class JclUnsupportedStatementResponse(BaseModel):
    """A recognised-but-unmodelled JCL statement, captured whole."""

    name: str | None
    operation: str
    parameters: list[JclParameterResponse]
    line: int


class JclStepResponse(BaseModel):
    """One job step: its ``EXEC`` statement plus its ``DD`` statements."""

    name: str
    parameters: list[JclParameterResponse]
    line: int
    dd_statements: list[JclDDStatementResponse]
    program: str | None = Field(
        default=None, description="The step's PGM= target, or null if it runs PROC=."
    )
    procedure: str | None = Field(
        default=None, description="The step's PROC= target, or null if it runs PGM=."
    )


class JclProgramResponse(BaseModel):
    """A fully parsed JCL job stream."""

    job: JclJobResponse | None
    steps: list[JclStepResponse]
    unsupported: list[JclUnsupportedStatementResponse]


class JclDiagnosticResponse(BaseModel):
    """One diagnostic raised while analysing a JCL job stream."""

    code: str
    message: str
    line: int
    severity: str


class JclAnalysisResponse(BaseModel):
    """
    Response schema for the JCL analysis endpoint.

    Attributes:
        success:
            ``True`` if the file was read and parsed without a fatal
            error -- independent of whether every statement was fully
            understood; see ``diagnostics`` for that.
        program:
            The parsed job stream, or ``null`` if analysis failed
            before any AST could be built (e.g. the file could not be
            read).
        diagnostics:
            Every diagnostic raised, in the order recorded.
        error:
            Human-readable error message, or ``null`` if analysis
            succeeded.
    """

    success: bool
    program: JclProgramResponse | None
    diagnostics: list[JclDiagnosticResponse]
    error: str | None = None
