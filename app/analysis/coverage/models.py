"""
Analysis Coverage Models (task #115 — Phase 5).

Purpose:
    Represent *how much of a COBOL source file was actually understood*
    by the analysis pipeline, split into the pipeline's natural stages,
    so that a consumer can tell "the program is simple" apart from "the
    program was not sufficiently analyzed".

    This is a **superset** of the parser-only
    :class:`app.analysis.models.AnalysisCoverage` value type introduced
    in #108 — the parser dimension here is derived directly from that
    object. Nothing is duplicated: #108's type stays the low-level
    evidence container; this module is the multi-dimensional view built
    on top of it plus the AST / IR / CFG / dependency / business-rule
    outputs of Phases 3–4.

Semantics (read before interpreting a ratio):
    Every ratio is ``covered / total`` where *covered* is content that
    was carried successfully through that stage and *total* is the
    content that stage should have handled given what earlier stages
    produced. A ratio is therefore **relative to what was recognised**,
    not to the (unknowable) full program:

    * ``parser`` measures tokens the parser's cursor consumed.
    * ``statement`` measures parsed statements against parsed statements
      plus statement-level failures (recoverable syntax errors +
      unsupported statements). It cannot see statements inside an
      *abandoned* region — those are the ``parser`` dimension's job.
    * ``ast`` / ``ir`` measure representation of what was recognised.
    * ``control_flow`` / ``dependency`` / ``business_rule`` measure
      whether the downstream analysis could inspect the relevant logic.

    A dimension with genuinely nothing to cover (a program with no
    conditional logic, for the ``business_rule`` dimension) is reported
    ``NOT_MEASURABLE`` with ``ratio = 1.0`` and is excluded from the
    ``overall`` roll-up — absence of a construct is not incompleteness.

    ``overall`` is the **weakest measurable link**, not an average: if
    any stage lost a material fraction of the program, the analysis as a
    whole did not understand that fraction, regardless of how well the
    other stages did.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any

__all__ = [
    "CoverageStatus",
    "CoverageDimension",
    "UnsupportedSyntaxCoverage",
    "CoverageReport",
]

# A ratio at or above this counts as "complete" (guards float noise).
_COMPLETE_THRESHOLD = 0.999


@unique
class CoverageStatus(Enum):
    """
    Qualitative status of one coverage dimension.

    Members:
        COMPLETE:
            Everything the stage should have handled was handled.
        PARTIAL:
            The stage handled some but not all of its input.
        FAILED:
            The stage produced nothing despite having input (e.g. the
            parser crashed, IR construction raised).
        NOT_MEASURABLE:
            There was genuinely nothing for this stage to do (no
            statements, no conditional logic, …). ``ratio`` is ``1.0``
            and the dimension is excluded from ``overall``.
    """

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NOT_MEASURABLE = "NOT_MEASURABLE"


@dataclass(frozen=True)
class CoverageDimension:
    """
    One measured stage of the analysis pipeline.

    Attributes:
        name:
            Stable dimension key (``"lexical"``, ``"parser"`` …).
        ratio:
            ``covered / total`` clamped to ``[0.0, 1.0]``. ``1.0`` when
            ``status`` is ``NOT_MEASURABLE``.
        covered:
            Units carried successfully through the stage.
        total:
            Units the stage should have handled.
        status:
            See :class:`CoverageStatus`.
        detail:
            One-line human explanation, including any caveat about the
            denominator.
    """

    name: str
    ratio: float
    covered: int
    total: int
    status: CoverageStatus
    detail: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.ratio <= 1.0:
            raise ValueError(
                f"CoverageDimension '{self.name}' ratio must be in [0.0, 1.0], "
                f"got {self.ratio!r}."
            )
        if self.covered < 0 or self.total < 0:
            raise ValueError(
                f"CoverageDimension '{self.name}' counts must be non-negative."
            )

    @property
    def measurable(self) -> bool:
        return self.status is not CoverageStatus.NOT_MEASURABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ratio": round(self.ratio, 4),
            "covered": self.covered,
            "total": self.total,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class UnsupportedSyntaxCoverage:
    """
    The unsupported/unmodelled syntax the analysis could not represent.

    Attributes:
        distinct_codes:
            Number of distinct ``SYN1xx``/``SYN2xx`` diagnostic codes.
        total_occurrences:
            Total occurrences across those codes.
        codes:
            The distinct codes, sorted.
        affected_dimensions:
            Which coverage dimensions each present code degrades, sorted
            and de-duplicated (e.g. an unsupported statement degrades
            ``statement``, ``ast``, ``ir``, ``control_flow``,
            ``dependency`` and ``business_rule``).
        detail:
            One-line summary.
    """

    distinct_codes: int
    total_occurrences: int
    codes: tuple[str, ...] = ()
    affected_dimensions: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if self.distinct_codes < 0 or self.total_occurrences < 0:
            raise ValueError("UnsupportedSyntaxCoverage counts must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "distinct_codes": self.distinct_codes,
            "total_occurrences": self.total_occurrences,
            "codes": list(self.codes),
            "affected_dimensions": list(self.affected_dimensions),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CoverageReport:
    """
    The full multi-dimensional coverage picture for one analysis.

    Attributes:
        lexical / parser / statement / ast / ir / control_flow /
        dependency / business_rule:
            The eight measured :class:`CoverageDimension` stages.
        unsupported_syntax:
            The unsupported-syntax summary (:class:`UnsupportedSyntaxCoverage`).
        overall:
            The weakest **measurable** dimension ratio (see the module
            docstring — deliberately not an average).
        overall_status:
            ``COMPLETE`` iff every measurable dimension is ``COMPLETE``;
            ``FAILED`` if any measurable dimension is ``FAILED``;
            ``PARTIAL`` otherwise.
    """

    lexical: CoverageDimension
    parser: CoverageDimension
    statement: CoverageDimension
    ast: CoverageDimension
    ir: CoverageDimension
    control_flow: CoverageDimension
    dependency: CoverageDimension
    business_rule: CoverageDimension
    unsupported_syntax: UnsupportedSyntaxCoverage
    overall: float = 0.0
    overall_status: CoverageStatus = CoverageStatus.FAILED
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0.0 <= self.overall <= 1.0:
            raise ValueError(
                f"CoverageReport overall must be in [0.0, 1.0], got {self.overall!r}."
            )

    @property
    def dimensions(self) -> tuple[CoverageDimension, ...]:
        return (
            self.lexical,
            self.parser,
            self.statement,
            self.ast,
            self.ir,
            self.control_flow,
            self.dependency,
            self.business_rule,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "overall_status": self.overall_status.value,
            "dimensions": {d.name: d.to_dict() for d in self.dimensions},
            "unsupported_syntax": self.unsupported_syntax.to_dict(),
            "notes": list(self.notes),
        }
