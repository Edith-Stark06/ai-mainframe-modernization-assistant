"""
Modernization Strategy Analyzer (task #114 — Phase 4).

Purpose:
    Turn the Phase 1–3 analysis, the CFG, the Phase 4 business rules, and
    the Phase 4 risks into deterministic modernization strategy
    recommendations.

Method:
    1. Compute a fixed set of observable *facts* from the inputs
       (:class:`_StrategyFacts`). No fact is inferred or scored.
    2. Evaluate one boolean *decision rule* per strategy. Each rule cites
       the exact facts and risk IDs that triggered it.
    3. Suppress rules that contradict a fired ``REWRITE``
       (``REHOST``/``REFACTOR`` keep the COBOL and cannot co-exist with a
       full rewrite).
    4. Mark the highest-:data:`STRATEGY_PRECEDENCE` survivor as primary.
    5. Sort (primary first, then precedence) and assign ``STRAT-NNN`` IDs.

    There is no ``if score > X`` anywhere. Every threshold is a concrete
    structural count with a documented meaning, and every recommendation
    is reproducible from identical inputs.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.analysis.dependencies.models import DependencyType
from app.analysis.models import AnalysisResult
from app.modernization.business_rules.models import BusinessRule
from app.modernization.flow.models import EdgeType, Flow, NodeType
from app.modernization.risk.models import ModernizationRisk, RiskCategory, RiskSeverity
from app.modernization.strategy.models import (
    STRATEGY_PRECEDENCE,
    ModernizationStrategy,
    StrategyRecommendation,
)

__all__ = ["ModernizationStrategyAnalyzer"]

_CONF_DIAGNOSTIC = (
    1.0  # decisive evidence includes a diagnostic-derived risk / CALL edge
)
_CONF_STRUCTURAL = 0.8  # decisive evidence is structural counts
_CONF_FALLBACK = 0.5  # no analyzable procedure logic


@dataclass(frozen=True)
class _StrategyFacts:
    """Observable facts used by the decision rules (all directly derived)."""

    parse_complete: bool
    coverage_ratio: float
    abandoned: bool
    unsupported_occurrences: int
    syntax_error_occurrences: int
    paragraph_count: int
    statement_count: int
    business_rule_count: int
    paragraphs_with_rules: int
    external_call_targets: tuple[str, ...]
    unresolved_perform_count: int
    perform_dependency_count: int
    has_loops: bool
    decision_count: int
    shared_state_high_count: int
    shared_state_any_count: int
    critical_risk_count: int
    high_risk_count: int
    medium_risk_count: int
    has_data_complexity: bool

    @property
    def has_procedure_logic(self) -> bool:
        return self.paragraph_count > 0 and self.statement_count > 0


def _facts(
    ar: AnalysisResult,
    flow: Flow,
    rules: list[BusinessRule],
    risks: list[ModernizationRisk],
) -> _StrategyFacts:
    cov = ar.coverage
    coverage_ratio = 1.0
    abandoned = False
    parse_complete = True
    if cov is not None:
        coverage_ratio = (
            cov.tokens_consumed / cov.tokens_total if cov.tokens_total else 1.0
        )
        abandoned = cov.abandoned_construct_count > 0
        parse_complete = cov.parse_complete
    else:
        parse_complete = False

    paragraphs = (
        ar.ast.procedure_division.paragraphs
        if ar.ast is not None and ar.ast.procedure_division is not None
        else ()
    )
    statement_count = sum(len(p.statements) for p in paragraphs)

    external_call_targets = tuple(
        sorted(
            {
                _strip_quotes(d.target).upper()
                for d in ar.dependencies
                if d.type is DependencyType.CALL and d.target
            }
        )
    )
    perform_dependency_count = sum(
        1 for d in ar.dependencies if d.type is DependencyType.PERFORM
    )

    by_cat: dict[RiskCategory, list[ModernizationRisk]] = {}
    for r in risks:
        by_cat.setdefault(r.category, []).append(r)

    unsupported_occurrences = sum(
        r.occurrence_count for r in by_cat.get(RiskCategory.UNSUPPORTED_SYNTAX, [])
    )
    syntax_error_occurrences = sum(
        r.occurrence_count for r in by_cat.get(RiskCategory.SYNTAX_ERROR, [])
    )
    unresolved_perform_count = sum(
        r.occurrence_count
        for r in by_cat.get(RiskCategory.UNRESOLVED_PERFORM_TARGET, [])
    )
    shared = by_cat.get(RiskCategory.SHARED_MUTABLE_STATE, [])
    shared_state_high_count = sum(1 for r in shared if r.severity is RiskSeverity.HIGH)

    decision_count = sum(1 for n in flow.nodes if n.node_type is NodeType.DECISION)
    has_loops = any(e.edge_type is EdgeType.LOOP_BACK for e in flow.edges)

    return _StrategyFacts(
        parse_complete=parse_complete,
        coverage_ratio=coverage_ratio,
        abandoned=abandoned,
        unsupported_occurrences=unsupported_occurrences,
        syntax_error_occurrences=syntax_error_occurrences,
        paragraph_count=len(paragraphs),
        statement_count=statement_count,
        business_rule_count=len(rules),
        paragraphs_with_rules=len({r.paragraph for r in rules if r.paragraph}),
        external_call_targets=external_call_targets,
        unresolved_perform_count=unresolved_perform_count,
        perform_dependency_count=perform_dependency_count,
        has_loops=has_loops,
        decision_count=decision_count,
        shared_state_high_count=shared_state_high_count,
        shared_state_any_count=len(shared),
        critical_risk_count=sum(
            1 for r in risks if r.severity is RiskSeverity.CRITICAL
        ),
        high_risk_count=sum(1 for r in risks if r.severity is RiskSeverity.HIGH),
        medium_risk_count=sum(1 for r in risks if r.severity is RiskSeverity.MEDIUM),
        has_data_complexity=bool(by_cat.get(RiskCategory.DATA_COMPLEXITY)),
    )


def _risk_ids(
    risks: list[ModernizationRisk], *categories: RiskCategory
) -> tuple[str, ...]:
    return tuple(r.risk_id for r in risks if r.category in categories)


def _risk_ids_by_severity(
    risks: list[ModernizationRisk], *severities: RiskSeverity
) -> tuple[str, ...]:
    return tuple(r.risk_id for r in risks if r.severity in severities)


class ModernizationStrategyAnalyzer:
    """Produce deterministic strategy recommendations. Stateless."""

    def analyze(
        self,
        analysis_result: AnalysisResult,
        flow: Flow,
        business_rules: list[BusinessRule],
        risks: list[ModernizationRisk],
    ) -> list[StrategyRecommendation]:
        """Return the deterministically ordered strategy recommendations."""
        f = _facts(analysis_result, flow, business_rules, risks)
        emitted: list[StrategyRecommendation] = []

        for builder in (
            self._rule_rewrite,
            self._rule_rehost,
            self._rule_refactor,
            self._rule_replatform,
            self._rule_service_extraction,
            self._rule_strangler,
            self._rule_phased_migration,
        ):
            rec = builder(f, risks)
            if rec is not None:
                emitted.append(rec)

        # Contradiction suppression: a full REWRITE excludes the two
        # strategies that keep the existing COBOL running as-is.
        if any(r.strategy is ModernizationStrategy.REWRITE for r in emitted):
            emitted = [
                r
                for r in emitted
                if r.strategy
                not in (
                    ModernizationStrategy.REHOST,
                    ModernizationStrategy.REFACTOR,
                )
            ]

        if not emitted:
            emitted.append(self._fallback(f))

        # Primary = highest-precedence survivor.
        primary_strategy = min(
            (r.strategy for r in emitted), key=lambda s: STRATEGY_PRECEDENCE[s]
        )
        emitted = [
            replace(r, is_primary=(r.strategy is primary_strategy)) for r in emitted
        ]

        emitted.sort(key=lambda r: (not r.is_primary, STRATEGY_PRECEDENCE[r.strategy]))
        return [
            replace(r, recommendation_id=f"STRAT-{i:03d}")
            for i, r in enumerate(emitted, start=1)
        ]

    # ------------------------------------------------------------------
    # Decision rules
    # ------------------------------------------------------------------

    def _rule_rewrite(
        self, f: _StrategyFacts, risks: list[ModernizationRisk]
    ) -> StrategyRecommendation | None:
        """
        REWRITE when the source cannot be relied on for behaviour-
        preserving automation: a region was abandoned, a CRITICAL risk
        exists, or there are 10+ unsupported-construct occurrences.
        """
        triggers: list[str] = []
        if f.abandoned:
            triggers.append("the parser abandoned a region of the source")
        if f.critical_risk_count:
            triggers.append(f"{f.critical_risk_count} CRITICAL risk(s) detected")
        if f.unsupported_occurrences >= 10:
            triggers.append(
                f"{f.unsupported_occurrences} unsupported/unmodelled construct "
                "occurrences"
            )
        if not triggers:
            return None
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.REWRITE,
            is_primary=False,
            rationale=(
                "So much of the program is unparseable, unsupported, or structurally "
                "broken that automated behaviour-preserving transformation is not "
                "trustworthy. Re-implementing against a validated behavioural "
                "specification is lower risk than transforming code the tools cannot "
                "fully read."
            ),
            evidence=tuple(triggers),
            referenced_risk_ids=_risk_ids_by_severity(risks, RiskSeverity.CRITICAL)
            + _risk_ids(
                risks,
                RiskCategory.UNSUPPORTED_SYNTAX,
                RiskCategory.PARSER_COVERAGE_GAP,
            ),
            prerequisites=(
                "Build a full behavioural test suite from the current system's "
                "observable outputs.",
                "Catalogue every unsupported construct and abandoned region and "
                "define its intended behaviour.",
                "Confirm data formats (including COMP-3 / edited fields) against "
                "production samples.",
            ),
            confidence=_CONF_DIAGNOSTIC,
        )

    def _rule_rehost(
        self, f: _StrategyFacts, risks: list[ModernizationRisk]
    ) -> StrategyRecommendation | None:
        """
        REHOST when the program is fully parsed, fully supported, has no
        branching/looping, no external CALLs, and no shared mutable state
        — nothing to restructure, so move it to a supported host as-is.
        """
        if not (
            f.parse_complete
            and f.has_procedure_logic
            and f.unsupported_occurrences == 0
            and f.syntax_error_occurrences == 0
            and not f.has_loops
            and f.decision_count == 0
            and not f.external_call_targets
            and f.shared_state_any_count == 0
        ):
            return None
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.REHOST,
            is_primary=False,
            rationale=(
                "The program parses completely, uses only supported constructs, has "
                "linear control flow, no external calls, and no cross-paragraph "
                "shared state. There is nothing to restructure — recompiling it on a "
                "supported host preserves behaviour at the lowest cost."
            ),
            evidence=(
                f"parse complete ({f.coverage_ratio:.0%} of tokens)",
                "0 unsupported constructs, 0 syntax errors",
                "no loops, no decision points in the CFG",
                "no external CALL dependencies",
                "no cross-paragraph shared mutable state",
            ),
            referenced_risk_ids=(),
            prerequisites=(
                "Validate runtime/JCL and file-system equivalence on the target "
                "host.",
                "Run the existing regression fixtures against the rehosted binary.",
            ),
            confidence=_CONF_STRUCTURAL,
        )

    def _rule_refactor(
        self, f: _StrategyFacts, risks: list[ModernizationRisk]
    ) -> StrategyRecommendation | None:
        """
        REFACTOR when the source is fully parsed and supported, business
        rules are recoverable, dependencies are minimal (<=1 external
        CALL), and there is no HIGH shared-state or CRITICAL risk —
        localized complexity that can be cleaned up in place.
        """
        if not (
            f.parse_complete
            and f.has_procedure_logic
            and f.unsupported_occurrences == 0
            and f.syntax_error_occurrences == 0
            and f.business_rule_count >= 1
            and len(f.external_call_targets) <= 1
            and f.shared_state_high_count == 0
            and f.critical_risk_count == 0
        ):
            return None
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.REFACTOR,
            is_primary=False,
            rationale=(
                "The whole program is parsed and supported, its business rules were "
                "recovered cleanly, and its dependencies are limited. The complexity "
                "is local and can be improved in place (extract paragraphs, flatten "
                "conditionals, name the rules) without changing the architecture."
            ),
            evidence=(
                "parse complete, 0 unsupported constructs",
                f"{f.business_rule_count} business rule(s) extracted from "
                f"{f.paragraphs_with_rules} paragraph(s)",
                f"{len(f.external_call_targets)} external CALL target(s)",
                "no HIGH shared-state or CRITICAL risk",
            ),
            referenced_risk_ids=_risk_ids(
                risks,
                RiskCategory.DEEPLY_NESTED_CONDITIONS,
                RiskCategory.COMPLEX_CONTROL_FLOW,
                RiskCategory.SHARED_MUTABLE_STATE,
            ),
            prerequisites=(
                "Add characterization tests for every extracted business rule.",
                "Resolve ownership of any MEDIUM shared-state variables before "
                "splitting paragraphs.",
            ),
            confidence=_CONF_STRUCTURAL,
        )

    def _rule_replatform(
        self, f: _StrategyFacts, risks: list[ModernizationRisk]
    ) -> StrategyRecommendation | None:
        """
        REPLATFORM when the source itself is clean and fully supported but
        it is bound to one or more external units — move the platform
        while preserving the integration seams.
        """
        if not (
            f.parse_complete
            and f.unsupported_occurrences == 0
            and len(f.external_call_targets) >= 1
        ):
            return None
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.REPLATFORM,
            is_primary=False,
            rationale=(
                "The program's own source is clean and fully supported, but it "
                "depends on separately-compiled units. Moving to a new platform while "
                "keeping the CALL seams intact isolates the migration to the runtime "
                "and the integration points."
            ),
            evidence=(
                "parse complete, 0 unsupported constructs",
                "external CALL dependencies: " + ", ".join(f.external_call_targets),
            ),
            referenced_risk_ids=_risk_ids(risks, RiskCategory.EXTERNAL_CALL),
            prerequisites=(
                "Inventory every external CALL contract (inputs, outputs, failure "
                "modes).",
                "Confirm the target platform provides an equivalent for each "
                "external unit or a bridge to it.",
            ),
            confidence=_CONF_DIAGNOSTIC,
        )

    def _rule_service_extraction(
        self, f: _StrategyFacts, risks: list[ModernizationRisk]
    ) -> StrategyRecommendation | None:
        """
        SERVICE_EXTRACTION when there are multiple rule-bearing paragraphs,
        a defined external boundary (a CALL), and no HIGH shared-state
        risk — cohesive units that can be carved out behind an interface.
        """
        if not (
            f.paragraphs_with_rules >= 2
            and f.paragraph_count >= 3
            and len(f.external_call_targets) >= 1
            and f.shared_state_high_count == 0
        ):
            return None
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.SERVICE_EXTRACTION,
            is_primary=False,
            rationale=(
                "Several paragraphs each carry their own business rules and the "
                "program already has an explicit external boundary at its CALL sites. "
                "Cohesive rule clusters with bounded shared state can be lifted out "
                "as independently deployable services."
            ),
            evidence=(
                f"{f.paragraphs_with_rules} rule-bearing paragraph(s) of "
                f"{f.paragraph_count} total",
                "external boundary present: " + ", ".join(f.external_call_targets),
                "no HIGH shared-state risk",
            ),
            referenced_risk_ids=_risk_ids(
                risks,
                RiskCategory.EXTERNAL_CALL,
                RiskCategory.SHARED_MUTABLE_STATE,
            ),
            prerequisites=(
                "Define the interface contract at the chosen CALL boundary.",
                "Assign an owner for every MEDIUM shared-state variable the "
                "candidate service touches.",
                "Confirm the candidate paragraphs have no inbound GO TO.",
            ),
            confidence=_CONF_DIAGNOSTIC,
        )

    def _rule_strangler(
        self, f: _StrategyFacts, risks: list[ModernizationRisk]
    ) -> StrategyRecommendation | None:
        """
        STRANGLER_MODERNIZATION when the program is large with identifiable
        component boundaries (>=5 paragraphs, >=3 PERFORM edges, >=2 rule
        clusters) and has an external or unresolved boundary to route
        around.
        """
        if not (
            f.paragraph_count >= 5
            and f.business_rule_count >= 2
            and f.perform_dependency_count >= 3
            and (len(f.external_call_targets) >= 1 or f.unresolved_perform_count >= 1)
        ):
            return None
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.STRANGLER_MODERNIZATION,
            is_primary=False,
            rationale=(
                "The PERFORM graph and paragraph structure give clear component "
                "seams, and there is an external/unresolved boundary to place a "
                "façade at. Components can be re-implemented one at a time behind "
                "that façade while the rest of the program keeps running."
            ),
            evidence=(
                f"{f.paragraph_count} paragraphs, "
                f"{f.perform_dependency_count} PERFORM dependencies",
                f"{f.business_rule_count} business rules across "
                f"{f.paragraphs_with_rules} paragraphs",
                (
                    "external CALL boundary"
                    if f.external_call_targets
                    else f"{f.unresolved_perform_count} unresolved PERFORM target(s)"
                ),
            ),
            referenced_risk_ids=_risk_ids(
                risks,
                RiskCategory.EXTERNAL_CALL,
                RiskCategory.UNRESOLVED_PERFORM_TARGET,
                RiskCategory.COMPLEX_CONTROL_FLOW,
            ),
            prerequisites=(
                "Stand up a routing façade in front of the program's entry points.",
                "Pick the first component as the paragraph cluster with the fewest "
                "inbound PERFORM/CALL edges.",
                "Add end-to-end tests that exercise the façade before moving any "
                "component.",
            ),
            confidence=_CONF_STRUCTURAL,
        )

    def _rule_phased_migration(
        self, f: _StrategyFacts, risks: list[ModernizationRisk]
    ) -> StrategyRecommendation | None:
        """
        PHASED_MIGRATION when the program is large (>=5 paragraphs), has
        multiple rule clusters (>=2), multiple PERFORM dependencies
        (>=3), and non-trivial risk (>=2 MEDIUM-or-higher risks).
        """
        if not (
            f.paragraph_count >= 5
            and f.business_rule_count >= 2
            and f.perform_dependency_count >= 3
            and (f.high_risk_count + f.medium_risk_count) >= 2
        ):
            return None
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.PHASED_MIGRATION,
            is_primary=False,
            rationale=(
                "The program is large enough, has enough distinct rule clusters and "
                "internal dependencies, and carries enough risk that a single "
                "cut-over would be hard to validate. Migrating in dependency-ordered "
                "phases keeps each step testable."
            ),
            evidence=(
                f"{f.paragraph_count} paragraphs, "
                f"{f.perform_dependency_count} PERFORM dependencies",
                f"{f.business_rule_count} business rules across "
                f"{f.paragraphs_with_rules} paragraphs",
                f"{f.high_risk_count} HIGH + {f.medium_risk_count} MEDIUM risk(s)",
            ),
            referenced_risk_ids=_risk_ids_by_severity(
                risks, RiskSeverity.HIGH, RiskSeverity.MEDIUM
            ),
            prerequisites=(
                "Order phases by the PERFORM/CALL dependency graph (leaves first).",
                "Freeze scope per phase and regression-test between phases.",
                "Resolve HIGH-severity risks before the phase that touches them.",
            ),
            confidence=_CONF_STRUCTURAL,
        )

    def _fallback(self, f: _StrategyFacts) -> StrategyRecommendation:
        """No decision rule fired — state that plainly."""
        return StrategyRecommendation(
            recommendation_id="STRAT-PENDING",
            strategy=ModernizationStrategy.REHOST,
            is_primary=True,
            rationale=(
                "The analysis found no procedure logic, no business rules, and no "
                "risks to act on. There is nothing to refactor or decompose; if the "
                "program is still needed it can simply be hosted on a supported "
                "runtime."
            ),
            evidence=(
                f"{f.paragraph_count} paragraph(s), {f.statement_count} statement(s)",
                f"{f.business_rule_count} business rule(s)",
                "no decision rule matched",
            ),
            referenced_risk_ids=(),
            prerequisites=(
                "Confirm the program is still in use before investing in it at all.",
            ),
            confidence=_CONF_FALLBACK,
        )


def _strip_quotes(text: str) -> str:
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in {"'", '"'}:
        return t[1:-1]
    return t
