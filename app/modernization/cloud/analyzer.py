"""
Cloud Readiness Analyzer (task #stage48 — Phase 7 Modernization Intelligence).

Purpose:
    Assign one :class:`~app.modernization.cloud.models.CloudReadinessTier`
    to a COBOL program from a fixed set of observable *facts*
    (:class:`_CloudFacts`), matching
    :class:`~app.modernization.strategy.analyzer.ModernizationStrategyAnalyzer`'s
    own method: no fact is inferred or scored, every rule cites the exact
    facts that triggered it, and there is no numeric threshold anywhere.

    Five of the six facts (``EXEC SQL``/``EXEC CICS``/``EXEC DLI``/
    ``CALL 'CBLTDLI'``/VSAM organization) come from the *raw source
    text*, not the AST: this parser deliberately does not model ``EXEC
    SQL``/``EXEC CICS`` (see ``app/parser/lexer/lexer.py``'s own
    "Non-responsibilities"), so no AST-level signal exists to read them
    from. Detecting them is a handful of unambiguous, line-anchored
    regular expressions over the original file -- nothing here
    approximates COBOL parsing, and nothing claims to. ``CBLTDLI`` is
    IBM's own fixed, documented COBOL-to-DL/I call interface name (not
    a guessed or fuzzy library name -- there is exactly one standard
    entry point a COBOL program calls to reach IMS/DL-I), so a literal
    ``CALL 'CBLTDLI'`` is as unambiguous an IMS signal as ``EXEC
    DLI...END-EXEC`` and is counted as the same kind of evidence. The
    remaining two facts (external CALL count, parser coverage) reuse the
    exact same :class:`~app.analysis.models.AnalysisResult` fields
    :mod:`app.modernization.risk` and :mod:`app.modernization.strategy`
    already do.

Responsibilities:
    - :class:`CloudReadinessAnalyzer` -- its :meth:`~CloudReadinessAnalyzer.analyze`
      method gathers the observable facts above and applies four
      precedence-ordered rules to assign one
      :class:`~app.modernization.cloud.models.CloudReadinessTier`, always
      with cited evidence.

Non-responsibilities:
    - Assembler-callable IMS entry points (e.g. ``AERTDLI``) or any
      other DL/I call interface besides COBOL's own ``CBLTDLI`` --
      out of scope for a COBOL-only analyzer.
    - JCL-level signals (a job's DD statements referencing VSAM
      datasets, or step counts) -- this analyzer is scoped to one COBOL
      program, matching every other Phase 4/7 analyzer's own scope; a
      workspace-level correlation with the new JCL parser
      (:mod:`app.jcl`) is a natural follow-on, not built here.

Dependencies:
    - app.analysis.dependencies.models -- DependencyType
    - app.analysis.models -- AnalysisResult
    - app.modernization.cloud.models -- CloudReadinessAssessment, CloudReadinessTier
    - app.modernization.risk.models -- ModernizationRisk, RiskSeverity
    - Python standard library (re, dataclasses).

Examples:
    Assessing a source file already run through Phase 1-3::

        from app.modernization.cloud.analyzer import CloudReadinessAnalyzer

        assessment = CloudReadinessAnalyzer().analyze(source, analysis_result, risks)
        assert assessment.tier is not None
        assert assessment.evidence

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.analysis.dependencies.models import DependencyType
from app.analysis.models import AnalysisResult
from app.modernization.cloud.models import CloudReadinessAssessment, CloudReadinessTier
from app.modernization.risk.models import ModernizationRisk, RiskSeverity

__all__ = ["CloudReadinessAnalyzer"]

_EXEC_SQL_RE = re.compile(r"\bEXEC\s+SQL\b", re.IGNORECASE)
_EXEC_CICS_RE = re.compile(r"\bEXEC\s+CICS\b", re.IGNORECASE)
_EXEC_DLI_RE = re.compile(r"\bEXEC\s+DLI\b", re.IGNORECASE)
_CALL_CBLTDLI_RE = re.compile(r"\bCALL\s+['\"]CBLTDLI['\"]", re.IGNORECASE)
_VSAM_ORGANIZATION_RE = re.compile(
    r"\bORGANIZATION\s+(?:IS\s+)?(?:INDEXED|RELATIVE)\b", re.IGNORECASE
)
_VSAM_ACCESS_RE = re.compile(
    r"\bACCESS\s+(?:MODE\s+)?(?:IS\s+)?(?:DYNAMIC|RANDOM)\b", re.IGNORECASE
)

#: Coverage below this fraction of tokens consumed means the parser gave
#: up on enough of the file that this assessment's own facts (all of
#: which need the parser to have reached the relevant source) cannot be
#: trusted -- the same 50% figure
#: :meth:`app.modernization.risk.analyzer.RiskAnalyzer._detect_parser_coverage_gap`
#: uses as one of its own two CRITICAL-severity conditions (an abandoned
#: region *and* under 50% consumed).
_COVERAGE_GAP_THRESHOLD = 0.5


@dataclass(frozen=True)
class _CloudFacts:
    """Observable facts this analyzer's rules are built from."""

    exec_sql_lines: tuple[int, ...]
    exec_cics_lines: tuple[int, ...]
    exec_dli_lines: tuple[int, ...]
    call_cbltdli_lines: tuple[int, ...]
    vsam_lines: tuple[int, ...]
    external_call_count: int
    has_critical_risk: bool
    coverage_ratio: float | None

    @property
    def dli_lines(self) -> tuple[int, ...]:
        """Every IMS/DL-I signal line, ``EXEC DLI`` and ``CALL 'CBLTDLI'``
        combined and sorted -- the two forms are equally unambiguous
        evidence of the same coupling (see the module docstring)."""
        return tuple(sorted(self.exec_dli_lines + self.call_cbltdli_lines))


class CloudReadinessAnalyzer:
    """Assign a cloud readiness tier. Stateless between :meth:`analyze` calls."""

    def analyze(
        self,
        source: str,
        analysis_result: AnalysisResult,
        risks: list[ModernizationRisk] | None = None,
    ) -> CloudReadinessAssessment:
        """
        Assess *source*'s (and *analysis_result*'s) cloud readiness.

        Args:
            source: The raw COBOL source text (not normalized/lexed --
                the exact bytes the file was written in), used to detect
                ``EXEC SQL``/``EXEC CICS``/``EXEC DLI``/VSAM signals.
            analysis_result: Phase 1-3 output for the same source.
            risks: Phase 4 risks (see
                :class:`~app.modernization.risk.analyzer.RiskAnalyzer`).
                If ``None``, the CRITICAL-risk signal is skipped (treated
                as absent, never fabricated).

        Returns:
            A single :class:`~app.modernization.cloud.models.CloudReadinessAssessment`.
        """
        facts = self._gather_facts(source, analysis_result, risks or [])

        for rule in (
            self._rule_not_recommended,
            self._rule_requires_rearchitecture,
            self._rule_needs_refactoring,
        ):
            result = rule(facts)
            if result is not None:
                return result

        return self._rule_cloud_ready(facts)

    # ------------------------------------------------------------------
    # Fact gathering
    # ------------------------------------------------------------------

    def _gather_facts(
        self,
        source: str,
        analysis_result: AnalysisResult,
        risks: list[ModernizationRisk],
    ) -> _CloudFacts:
        external_call_count = len(
            {
                dep.target
                for dep in analysis_result.dependencies
                if dep.type is DependencyType.CALL
            }
        )
        has_critical_risk = any(r.severity is RiskSeverity.CRITICAL for r in risks)
        coverage = analysis_result.coverage
        coverage_ratio = (
            coverage.tokens_consumed / coverage.tokens_total
            if coverage is not None and coverage.tokens_total > 0
            else None
        )
        return _CloudFacts(
            exec_sql_lines=_matching_lines(source, _EXEC_SQL_RE),
            exec_cics_lines=_matching_lines(source, _EXEC_CICS_RE),
            exec_dli_lines=_matching_lines(source, _EXEC_DLI_RE),
            call_cbltdli_lines=_matching_lines(source, _CALL_CBLTDLI_RE),
            vsam_lines=(
                _matching_lines(source, _VSAM_ORGANIZATION_RE)
                + _matching_lines(source, _VSAM_ACCESS_RE)
            ),
            external_call_count=external_call_count,
            has_critical_risk=has_critical_risk,
            coverage_ratio=coverage_ratio,
        )

    # ------------------------------------------------------------------
    # Rules (checked in precedence order by :meth:`analyze`)
    # ------------------------------------------------------------------

    def _rule_not_recommended(
        self, facts: _CloudFacts
    ) -> CloudReadinessAssessment | None:
        evidence: list[str] = []
        if facts.coverage_ratio is not None and (
            facts.coverage_ratio < _COVERAGE_GAP_THRESHOLD
        ):
            evidence.append(
                f"parser coverage is only {facts.coverage_ratio:.0%} of tokens "
                "consumed -- this assessment's own facts cannot be trusted "
                "below that"
            )
        if facts.exec_cics_lines and facts.dli_lines:
            evidence.append(
                f"both EXEC CICS ({len(facts.exec_cics_lines)} occurrence(s), "
                f"line(s) {_format_lines(facts.exec_cics_lines)}) and IMS/DL-I "
                f"access ({_describe_dli(facts)}) are present -- coupled to "
                "both a transaction monitor and a hierarchical database at once"
            )
        if len(facts.dli_lines) >= 3:
            evidence.append(
                f"IMS/DL-I access ({_describe_dli(facts)}) appears "
                f"{len(facts.dli_lines)} times -- substantial IMS/DL-I coupling, "
                "an access pattern with no cloud-native equivalent"
            )
        if facts.has_critical_risk:
            evidence.append(
                "at least one CRITICAL modernization risk was already detected "
                "for this program"
            )
        if not evidence:
            return None
        return CloudReadinessAssessment(
            tier=CloudReadinessTier.NOT_RECOMMENDED,
            rationale=(
                "This program combines multiple mainframe-specific "
                "dependencies (or the analysis itself is too incomplete to "
                "trust) severely enough that migrating it as-is is not "
                "advisable; treat it as a candidate for a full rewrite "
                "against the target platform instead."
            ),
            evidence=tuple(evidence),
            prerequisites=(
                "Re-run analysis after resolving any parser coverage gap.",
                "Treat this program as a rewrite candidate, not a "
                "migration candidate.",
            ),
            confidence=(
                0.75
                if facts.coverage_ratio is not None
                and (facts.coverage_ratio < _COVERAGE_GAP_THRESHOLD)
                else 1.0
            ),
        )

    def _rule_requires_rearchitecture(
        self, facts: _CloudFacts
    ) -> CloudReadinessAssessment | None:
        evidence: list[str] = []
        if facts.exec_cics_lines:
            evidence.append(
                f"EXEC CICS appears {len(facts.exec_cics_lines)} time(s) "
                f"(line(s) {_format_lines(facts.exec_cics_lines)}) -- CICS "
                "transaction-processing coupling has no drop-in cloud "
                "equivalent"
            )
        if facts.dli_lines:
            evidence.append(
                f"IMS/DL-I access ({_describe_dli(facts)}) -- hierarchical "
                "database access has no drop-in cloud equivalent"
            )
        if len(facts.vsam_lines) >= 2:
            evidence.append(
                f"VSAM indexed/relative/dynamic file organization appears "
                f"{len(facts.vsam_lines)} time(s) (line(s) "
                f"{_format_lines(facts.vsam_lines)}) -- keyed/indexed file "
                "access has no drop-in cloud equivalent"
            )
        if not evidence:
            return None
        return CloudReadinessAssessment(
            tier=CloudReadinessTier.REQUIRES_REARCHITECTURE,
            rationale=(
                "This program is coupled to a mainframe-specific execution "
                "or data subsystem (CICS, IMS/DL-I, or indexed/relative VSAM "
                "access) with no cloud equivalent to relocate to as-is; the "
                "data or transaction layer needs redesigning, not just "
                "relocating."
            ),
            evidence=tuple(evidence),
            prerequisites=(
                "Design a cloud-native replacement for the affected "
                "transaction/data layer before migrating this program's "
                "own logic.",
            ),
        )

    def _rule_needs_refactoring(
        self, facts: _CloudFacts
    ) -> CloudReadinessAssessment | None:
        evidence: list[str] = []
        if facts.exec_sql_lines:
            evidence.append(
                f"EXEC SQL appears {len(facts.exec_sql_lines)} time(s) "
                f"(line(s) {_format_lines(facts.exec_sql_lines)}) -- DB2 "
                "coupling; most cloud providers offer a relational database "
                "this can be migrated onto, but the SQL/embedded-host-"
                "variable code needs adapting"
            )
        if len(facts.vsam_lines) == 1:
            evidence.append(
                f"VSAM indexed/relative/dynamic file organization appears "
                f"once (line {facts.vsam_lines[0]})"
            )
        if facts.external_call_count >= 3:
            evidence.append(
                f"{facts.external_call_count} distinct external CALL "
                "target(s) -- a meaningful integration surface to "
                "re-establish on the target platform"
            )
        if not evidence:
            return None
        return CloudReadinessAssessment(
            tier=CloudReadinessTier.NEEDS_REFACTORING,
            rationale=(
                "This program uses portable-but-coupled technology and/or "
                "has a real external integration surface; migration is "
                "feasible with moderate, targeted refactoring rather than a "
                "redesign."
            ),
            evidence=tuple(evidence),
            prerequisites=(
                "Inventory and re-point each external CALL target and "
                "EXEC SQL data source for the target environment.",
            ),
        )

    def _rule_cloud_ready(self, facts: _CloudFacts) -> CloudReadinessAssessment:
        evidence = [
            "no EXEC SQL, EXEC CICS, EXEC DLI, CALL 'CBLTDLI', or VSAM "
            "indexed/relative/dynamic file organization detected in the "
            "source",
            f"{facts.external_call_count} distinct external CALL target(s)",
        ]
        if facts.coverage_ratio is not None:
            evidence.append(
                f"parser reached {facts.coverage_ratio:.0%} of the source's " "tokens"
            )
        return CloudReadinessAssessment(
            tier=CloudReadinessTier.CLOUD_READY,
            rationale=(
                "No mainframe-specific data/transaction coupling was "
                "detected, and this program's integration surface is small; "
                "it is the most straightforward rehost/replatform candidate "
                "this assessment can identify."
            ),
            evidence=tuple(evidence),
        )


def _describe_dli(facts: _CloudFacts) -> str:
    """Render whichever IMS/DL-I form(s) *facts* actually has evidence
    for -- ``EXEC DLI``, ``CALL 'CBLTDLI'``, or both -- with line
    numbers, so evidence always names the exact syntax found."""
    parts: list[str] = []
    if facts.exec_dli_lines:
        parts.append(
            f"EXEC DLI x{len(facts.exec_dli_lines)} (line(s) "
            f"{_format_lines(facts.exec_dli_lines)})"
        )
    if facts.call_cbltdli_lines:
        parts.append(
            f"CALL 'CBLTDLI' x{len(facts.call_cbltdli_lines)} (line(s) "
            f"{_format_lines(facts.call_cbltdli_lines)})"
        )
    return "; ".join(parts)


def _matching_lines(source: str, pattern: re.Pattern[str]) -> tuple[int, ...]:
    """Return the 1-based line number of every *pattern* match in *source*."""
    return tuple(source.count("\n", 0, m.start()) + 1 for m in pattern.finditer(source))


def _format_lines(lines: tuple[int, ...]) -> str:
    """Render a tuple of line numbers as a short, human-readable list."""
    shown = lines[:5]
    text = ", ".join(str(n) for n in shown)
    if len(lines) > len(shown):
        text += f", +{len(lines) - len(shown)} more"
    return text
