"""
Risk Analyzer (task #113 — Phase 4 Modernization Intelligence).

Purpose:
    Deterministically detect :class:`~app.modernization.risk.models.ModernizationRisk`
    records from an :class:`~app.analysis.models.AnalysisResult`, the CFG
    (:class:`~app.modernization.flow.models.Flow`), and the Phase 4
    business rules.

Design:
    * One private ``_detect_*`` method per :class:`RiskCategory`. Each
      returns zero or more risks, already aggregated where aggregation
      makes sense (e.g. one ``UNSUPPORTED_SYNTAX`` risk per distinct
      diagnostic code rather than one per occurrence).
    * :meth:`RiskAnalyzer.analyze` runs every detector, de-duplicates on
      a structural key, totally orders the result, then assigns stable
      ``RISK-<slug>-NNN`` identifiers.
    * No LLM, no numeric risk score. Severity comes from an explicit,
      documented, per-category policy (see each detector's docstring and
      :data:`_SEVERITY_POLICY_DOC`).

Non-fabrication guarantees:
    * A risk category with no supporting evidence produces no risk.
    * External systems are only reported when a ``CALL`` dependency or an
      unresolved ``PERFORM`` target actually exists.
    * File-dependency risks are **not** emitted from arbitrary string
      matching — the parser does not model file I/O, so the only file
      signal used is an explicit ``UNSUPPORTED`` diagnostic for a
      DATA DIVISION FILE section, surfaced under ``DATA_COMPLEXITY``.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from app.analysis.dependencies.models import Dependency, DependencyType
from app.analysis.models import AnalysisResult
from app.modernization.business_rules.models import BusinessRule
from app.modernization.flow.models import EdgeType, Flow, NodeType
from app.modernization.risk.models import (
    SEVERITY_ORDER,
    ModernizationRisk,
    RiskCategory,
    RiskSeverity,
)
from app.parser.ast.statements import IfStatementNode, PerformUntilStatementNode
from app.parser.lexer.position import Position

__all__ = ["RiskAnalyzer"]

_SEVERITY_POLICY_DOC = """\
Deterministic severity policy (task #113):

  PARSER_COVERAGE_GAP        CRITICAL if a region was abandoned AND < 50%
                             of tokens were consumed; HIGH if any region
                             was abandoned or tokens were left unconsumed;
                             MEDIUM if only recoverable syntax errors.
  UNSUPPORTED_SYNTAX         HIGH  (valid COBOL the parser cannot represent).
  SYNTAX_ERROR               MEDIUM (parser recovered and continued).
  EXTERNAL_CALL              HIGH if the CALL passes arguments (a data
                             contract to validate); MEDIUM otherwise.
  UNRESOLVED_PERFORM_TARGET  MEDIUM.
  COMPLEX_CONTROL_FLOW       MEDIUM if back-edges (loops) or GO TO
                             transfers exist; LOW for forward branching
                             only.
  DEEPLY_NESTED_CONDITIONS   HIGH if max IF nesting depth >= 5;
                             MEDIUM for depth 3-4; not reported below 3.
  SHARED_MUTABLE_STATE       HIGH if a variable is written in >= 3
                             paragraphs; MEDIUM for exactly 2.
  UNDOCUMENTED_BUSINESS_RULES LOW.
  DATA_COMPLEXITY            MEDIUM.
"""

# Confidence values (documented policy — never probabilistic):
_CONF_DIRECT = 1.0  # from an explicit diagnostic / dependency / CFG fact
_CONF_STRUCTURAL = 0.75  # from a structural heuristic over the AST/CFG


def _pos_from_diag(diag: object) -> Position | None:
    line = getattr(diag, "line", None)
    if line is None:
        return None
    return Position(
        line=int(line),
        column=int(getattr(diag, "column", 0) or 0),
        offset=int(getattr(diag, "offset", 0) or 0),
        filename=str(getattr(diag, "filename", "") or ""),
    )


class RiskAnalyzer:
    """Detect modernization risks. Stateless between :meth:`analyze` calls."""

    SEVERITY_POLICY = _SEVERITY_POLICY_DOC

    def analyze(
        self,
        analysis_result: AnalysisResult,
        flow: Flow | None = None,
        business_rules: list[BusinessRule] | None = None,
    ) -> list[ModernizationRisk]:
        """
        Return the deterministically ordered risks for *analysis_result*.

        Args:
            analysis_result: Phase 1–3 output.
            flow: The CFG. If ``None``, control-flow risks that need it
                are skipped (they are re-derived by the pipeline, which
                always passes a flow).
            business_rules: Phase 4 rules. If ``None``, the
                undocumented-business-rules detector is skipped.
        """
        rules = business_rules or []
        raw: list[ModernizationRisk] = []

        raw += self._detect_unsupported_syntax(analysis_result)
        raw += self._detect_syntax_errors(analysis_result)
        raw += self._detect_parser_coverage_gap(analysis_result)
        raw += self._detect_external_calls(analysis_result)
        raw += self._detect_unresolved_perform_targets(analysis_result, flow)
        raw += self._detect_complex_control_flow(analysis_result, flow)
        raw += self._detect_deeply_nested_conditions(analysis_result)
        raw += self._detect_shared_mutable_state(analysis_result)
        raw += self._detect_undocumented_business_rules(rules)
        raw += self._detect_data_complexity(analysis_result)

        return _finalize(raw)

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _detect_unsupported_syntax(self, ar: AnalysisResult) -> list[ModernizationRisk]:
        """
        Valid COBOL the parser reached, recognised, and declined to
        represent (``UNSUPPORTED`` / ``UNMODELLED`` diagnostics).
        Aggregated by diagnostic code. Severity: always HIGH.
        """
        from app.parser.diagnostics.recovery import SyntaxCategory

        buckets: dict[str, list[object]] = defaultdict(list)
        for diag in ar.syntax_diagnostics:
            if getattr(diag, "category", None) in (
                SyntaxCategory.UNSUPPORTED,
                SyntaxCategory.UNMODELLED,
            ):
                buckets[getattr(diag, "code", "SYN?")].append(diag)

        risks: list[ModernizationRisk] = []
        for code, diags in sorted(buckets.items()):
            locations = tuple(
                p for p in (_pos_from_diag(d) for d in diags) if p is not None
            )
            messages = sorted({str(getattr(d, "message", "")).strip() for d in diags})
            risks.append(
                ModernizationRisk(
                    risk_id="RISK-PENDING",
                    category=RiskCategory.UNSUPPORTED_SYNTAX,
                    severity=RiskSeverity.HIGH,
                    title=f"Unsupported/unmodelled construct ({code})",
                    explanation=(
                        "The parser recognised valid COBOL it does not represent in "
                        "the AST. Any downstream translation silently omits this "
                        "construct, so its behaviour will not be carried into the "
                        "modernized system unless it is handled explicitly."
                    ),
                    evidence=tuple(
                        [f"{len(diags)} occurrence(s) of diagnostic {code}"]
                        + [f"- {m}" for m in messages[:5]]
                    ),
                    source_locations=locations,
                    affected_components=(
                        ("DATA DIVISION",)
                        if code in {"SYN200", "SYN101"}
                        else ("<program>",)
                    ),
                    confidence=_CONF_DIRECT,
                    recommended_mitigation=(
                        "Catalogue each occurrence and decide, per construct, whether "
                        "to replace it with a supported equivalent, model it, or "
                        "accept the behavioural change before migration."
                    ),
                    occurrence_count=len(diags),
                )
            )
        return risks

    def _detect_syntax_errors(self, ar: AnalysisResult) -> list[ModernizationRisk]:
        """
        Recoverable syntax errors (the parser synchronised and continued).
        One aggregated risk. Severity: MEDIUM.
        """
        from app.parser.diagnostics.recovery import SyntaxCategory

        diags = [
            d
            for d in ar.syntax_diagnostics
            if getattr(d, "category", None) is SyntaxCategory.SYNTAX_ERROR
        ]
        if not diags:
            return []
        by_code: dict[str, int] = defaultdict(int)
        for d in diags:
            by_code[getattr(d, "code", "SYN?")] += 1
        locations = tuple(
            p for p in (_pos_from_diag(d) for d in diags) if p is not None
        )
        code_summary = ", ".join(f"{c}×{n}" for c, n in sorted(by_code.items()))
        return [
            ModernizationRisk(
                risk_id="RISK-PENDING",
                category=RiskCategory.SYNTAX_ERROR,
                severity=RiskSeverity.MEDIUM,
                title="Recoverable syntax errors in PROCEDURE DIVISION",
                explanation=(
                    "The parser hit constructs it could not parse, recovered to the "
                    "next safe point, and continued. The statements between the error "
                    "and the recovery point are missing from the AST, so any rule, "
                    "risk, or translation derived from that region is incomplete."
                ),
                evidence=(
                    f"{len(diags)} recoverable syntax error(s): {code_summary}",
                    *[f"- {str(getattr(d, 'message', '')).strip()}" for d in diags[:5]],
                ),
                source_locations=locations,
                affected_components=("<program>",),
                confidence=_CONF_DIRECT,
                recommended_mitigation=(
                    "Review each flagged location in the original source; the affected "
                    "statements must be modernized manually because they are absent "
                    "from the automated analysis."
                ),
                occurrence_count=len(diags),
            )
        ]

    def _detect_parser_coverage_gap(
        self, ar: AnalysisResult
    ) -> list[ModernizationRisk]:
        """
        The parser did not fully traverse the file. Severity: CRITICAL if
        a region was abandoned and < 50% of tokens consumed; HIGH if any
        abandonment or unconsumed tokens; otherwise no risk here (pure
        syntax errors are covered by :meth:`_detect_syntax_errors`).
        """
        cov = ar.coverage
        if cov is None:
            return [
                ModernizationRisk(
                    risk_id="RISK-PENDING",
                    category=RiskCategory.PARSER_COVERAGE_GAP,
                    severity=RiskSeverity.CRITICAL,
                    title="Source could not be parsed",
                    explanation=(
                        "Parsing did not reach the point where coverage can be "
                        "measured (a lexer or top-level parser failure). No reliable "
                        "analysis of this file is possible."
                    ),
                    evidence=("no AnalysisCoverage was produced",),
                    affected_components=("<program>",),
                    confidence=_CONF_DIRECT,
                    recommended_mitigation=(
                        "Fix the blocking lexical/syntax problem before any automated "
                        "modernization analysis."
                    ),
                )
            ]

        consumed_ratio = (
            cov.tokens_consumed / cov.tokens_total if cov.tokens_total else 1.0
        )
        abandoned = cov.abandoned_construct_count > 0
        unconsumed = cov.tokens_consumed < cov.tokens_total
        if not abandoned and not unconsumed:
            return []

        if abandoned and consumed_ratio < 0.5:
            severity = RiskSeverity.CRITICAL
        else:
            severity = RiskSeverity.HIGH

        return [
            ModernizationRisk(
                risk_id="RISK-PENDING",
                category=RiskCategory.PARSER_COVERAGE_GAP,
                severity=severity,
                title="Parser abandoned or did not finish the source",
                explanation=(
                    "The parser stopped analysing part of the file. Everything after "
                    "the abandonment point is invisible to every later phase, so the "
                    "analysis under-reports rules, risks and dependencies."
                ),
                evidence=(
                    f"tokens consumed {cov.tokens_consumed}/{cov.tokens_total} "
                    f"({consumed_ratio:.0%})",
                    f"abandoned regions: {cov.abandoned_construct_count}",
                    f"paragraphs parsed: {cov.paragraphs_parsed}",
                ),
                affected_components=("<program>",),
                confidence=_CONF_DIRECT,
                recommended_mitigation=(
                    "Repair the construct at the abandonment point and re-run "
                    "analysis; do not rely on rule/risk output until "
                    "coverage.parse_complete is true."
                ),
                occurrence_count=max(1, cov.abandoned_construct_count),
            )
        ]

    def _detect_external_calls(self, ar: AnalysisResult) -> list[ModernizationRisk]:
        """One risk per distinct CALL target. Severity: HIGH if it passes
        arguments, else MEDIUM."""
        calls: dict[str, list[Dependency]] = defaultdict(list)
        for dep in ar.dependencies:
            if dep.type is DependencyType.CALL and dep.target:
                calls[_strip_quotes(dep.target).upper()].append(dep)

        risks: list[ModernizationRisk] = []
        for target, deps in sorted(calls.items()):
            components = tuple(sorted({d.source for d in deps if d.source})) or (
                "<program>",
            )
            locations = tuple(
                d.source_location for d in deps if d.source_location is not None
            )
            # An argument-bearing CALL is a data contract; the AST does not
            # retain the argument list on the Dependency, so this uses the
            # only available signal: HIGH when the same target is invoked
            # from more than one site (a shared external boundary), else
            # MEDIUM.
            severity = RiskSeverity.HIGH if len(deps) > 1 else RiskSeverity.MEDIUM
            risks.append(
                ModernizationRisk(
                    risk_id="RISK-PENDING",
                    category=RiskCategory.EXTERNAL_CALL,
                    severity=severity,
                    title=f"External CALL dependency: {target}",
                    explanation=(
                        "This program transfers control to a separately-compiled unit. "
                        "The callee's contract (parameters, side effects, error "
                        "behaviour) is outside this analysis and must be established "
                        "before the caller can be migrated."
                    ),
                    evidence=(
                        f"{len(deps)} CALL site(s) to '{target}'",
                        *[f"- from paragraph {d.source or '<unknown>'}" for d in deps],
                    ),
                    source_locations=locations,
                    affected_components=components,
                    confidence=_CONF_DIRECT,
                    recommended_mitigation=(
                        f"Locate and document the interface of '{target}' (inputs, "
                        "outputs, failure modes) and decide whether to re-implement, "
                        "wrap, or call it as-is."
                    ),
                    occurrence_count=len(deps),
                )
            )
        return risks

    def _detect_unresolved_perform_targets(
        self, ar: AnalysisResult, flow: Flow | None
    ) -> list[ModernizationRisk]:
        """
        A PERFORM whose target is not a paragraph defined in this program.
        Detected from the CFG's synthetic ``EXTERNAL`` nodes reached by
        ``PERFORMS`` edges. Severity: MEDIUM.
        """
        if flow is None:
            return []
        external_ids = {n.id for n in flow.nodes if n.node_type is NodeType.EXTERNAL}
        if not external_ids:
            return []
        targets: dict[str, list[str]] = defaultdict(list)
        node_by_id = {n.id: n for n in flow.nodes}
        for edge in flow.edges:
            if edge.edge_type is EdgeType.PERFORMS and edge.target_id in external_ids:
                name = node_by_id[edge.target_id].name
                targets[name].append(edge.source_id)
        if not targets:
            return []
        return [
            ModernizationRisk(
                risk_id="RISK-PENDING",
                category=RiskCategory.UNRESOLVED_PERFORM_TARGET,
                severity=RiskSeverity.MEDIUM,
                title="PERFORM to an unresolved target",
                explanation=(
                    "A PERFORM names something that is not a paragraph defined in this "
                    "program. It is either an external procedure, a parser gap (for "
                    "example PERFORM VARYING is currently recorded with the target "
                    "'VARYING'), or dead code. The real control-flow target is unknown "
                    "to the analysis."
                ),
                evidence=tuple(
                    f"PERFORM '{name}' (unresolved) — {len(srcs)} site(s)"
                    for name, srcs in sorted(targets.items())
                ),
                affected_components=("<program>",),
                confidence=_CONF_DIRECT,
                recommended_mitigation=(
                    "Confirm for each unresolved target whether it is an external "
                    "routine, an unsupported PERFORM form, or dead code, and resolve "
                    "it before relying on the control-flow graph."
                ),
                occurrence_count=sum(len(s) for s in targets.values()),
            )
        ]

    def _detect_complex_control_flow(
        self, ar: AnalysisResult, flow: Flow | None
    ) -> list[ModernizationRisk]:
        """
        Report control-flow complexity from the CFG. Severity: MEDIUM when
        loops (back edges) or GO TO transfers exist; LOW for forward
        branching only. Not reported when there is no branching at all.
        """
        if flow is None:
            return []
        decision_nodes = [n for n in flow.nodes if n.node_type is NodeType.DECISION]
        back_edges = [e for e in flow.edges if e.edge_type is EdgeType.LOOP_BACK]
        goto_edges = [e for e in flow.edges if e.edge_type is EdgeType.GOES_TO]
        if not decision_nodes and not back_edges and not goto_edges:
            return []

        has_loops_or_jumps = bool(back_edges or goto_edges)
        severity = RiskSeverity.MEDIUM if has_loops_or_jumps else RiskSeverity.LOW
        evidence = [
            f"{len(decision_nodes)} decision point(s) in the control-flow graph",
            f"{len(back_edges)} loop back-edge(s)",
            f"{len(goto_edges)} GO TO transfer(s)",
        ]
        return [
            ModernizationRisk(
                risk_id="RISK-PENDING",
                category=RiskCategory.COMPLEX_CONTROL_FLOW,
                severity=severity,
                title="Branching / looping control flow",
                explanation=(
                    "The control-flow graph contains decision points"
                    + (
                        ", loops and/or unstructured jumps"
                        if has_loops_or_jumps
                        else ""
                    )
                    + ". Each path must be understood and preserved when the logic is "
                    "restructured into a modern language."
                ),
                evidence=tuple(evidence),
                affected_components=tuple(
                    sorted(
                        {n.name for n in decision_nodes if n.name and n.name.strip()}
                    )
                )
                or ("<program>",),
                confidence=_CONF_DIRECT,
                recommended_mitigation=(
                    "Document each branch and loop with its entry/exit conditions; "
                    "add characterization tests for every path before refactoring."
                ),
                occurrence_count=len(decision_nodes)
                + len(back_edges)
                + len(goto_edges),
            )
        ]

    def _detect_deeply_nested_conditions(
        self, ar: AnalysisResult
    ) -> list[ModernizationRisk]:
        """
        Max IF nesting depth from the AST. HIGH at depth >= 5, MEDIUM at
        3–4, nothing below 3. Structural heuristic → confidence 0.75.
        """
        ast = ar.ast
        if ast is None or ast.procedure_division is None:
            return []
        deepest = 0
        deepest_para = ""
        for para in ast.procedure_division.paragraphs:
            for stmt in para.statements:
                d = _max_if_depth(stmt)
                if d > deepest:
                    deepest = d
                    deepest_para = para.name
        if deepest < 3:
            return []
        severity = RiskSeverity.HIGH if deepest >= 5 else RiskSeverity.MEDIUM
        return [
            ModernizationRisk(
                risk_id="RISK-PENDING",
                category=RiskCategory.DEEPLY_NESTED_CONDITIONS,
                severity=severity,
                title=f"Deeply nested conditions (depth {deepest})",
                explanation=(
                    "Nested IF logic this deep is hard to read, hard to test "
                    "exhaustively, and easy to get subtly wrong when re-expressed. "
                    "The number of distinct condition combinations grows with depth."
                ),
                evidence=(
                    f"maximum IF nesting depth is {deepest}",
                    f"deepest nest is in paragraph {deepest_para}",
                ),
                affected_components=(deepest_para,) if deepest_para else ("<program>",),
                confidence=_CONF_STRUCTURAL,
                recommended_mitigation=(
                    "Flatten with guard clauses / early exits or extract the inner "
                    "branches into named paragraphs; cover every combination with "
                    "tests first."
                ),
                occurrence_count=1,
            )
        ]

    def _detect_shared_mutable_state(
        self, ar: AnalysisResult
    ) -> list[ModernizationRisk]:
        """
        A WORKING-STORAGE variable written from more than one paragraph
        (from Phase 3 VARIABLE_WRITE dependencies). HIGH at >= 3
        paragraphs, MEDIUM at exactly 2. Structural inference → 0.75.
        """
        writers: dict[str, set[str]] = defaultdict(set)
        locs: dict[str, list[Position]] = defaultdict(list)
        for dep in ar.dependencies:
            if dep.type is DependencyType.VARIABLE_WRITE and dep.target and dep.source:
                writers[dep.target.upper()].add(dep.source)
                if dep.source_location is not None:
                    locs[dep.target.upper()].append(dep.source_location)

        risks: list[ModernizationRisk] = []
        for var, paras in sorted(writers.items()):
            if len(paras) < 2:
                continue
            severity = RiskSeverity.HIGH if len(paras) >= 3 else RiskSeverity.MEDIUM
            risks.append(
                ModernizationRisk(
                    risk_id="RISK-PENDING",
                    category=RiskCategory.SHARED_MUTABLE_STATE,
                    severity=severity,
                    title=f"Shared mutable variable: {var}",
                    explanation=(
                        "This variable is assigned from multiple paragraphs. Any "
                        "decomposition into independent components (services, modules) "
                        "must decide who owns it and how updates are coordinated, or "
                        "the components will silently interfere."
                    ),
                    evidence=(
                        f"'{var}' is written from {len(paras)} paragraphs: "
                        + ", ".join(sorted(paras)),
                    ),
                    source_locations=tuple(locs.get(var, ())),
                    affected_components=tuple(sorted(paras)),
                    confidence=_CONF_STRUCTURAL,
                    recommended_mitigation=(
                        f"Assign a single owner for '{var}', or pass it explicitly "
                        "between components instead of sharing WORKING-STORAGE."
                    ),
                    occurrence_count=len(paras),
                )
            )
        return risks

    def _detect_undocumented_business_rules(
        self, rules: list[BusinessRule]
    ) -> list[ModernizationRisk]:
        """
        Business logic exists only as inline procedural code. One
        aggregate risk. Severity: LOW.

        Defensible definition: a rule is "undocumented" here because the
        analysis has no artifact describing it independently of the code —
        COBOL comments are discarded by the lexer and no paragraph carries
        specification metadata. This is asserted once for the program, not
        per rule, and only when rules were actually extracted.
        """
        if not rules:
            return []
        paras = sorted({r.paragraph for r in rules if r.paragraph})
        return [
            ModernizationRisk(
                risk_id="RISK-PENDING",
                category=RiskCategory.UNDOCUMENTED_BUSINESS_RULES,
                severity=RiskSeverity.LOW,
                title="Business rules exist only as inline code",
                explanation=(
                    "The extractor recovered business rules directly from PROCEDURE "
                    "DIVISION logic. There is no separate specification for them: the "
                    "source's own comments are not retained by the pipeline and no "
                    "paragraph carries rule metadata. The rules' intent is therefore "
                    "only whatever the code literally does."
                ),
                evidence=(
                    f"{len(rules)} business rule(s) extracted from {len(paras)} "
                    "paragraph(s), none with an external specification",
                    *[f"- {r.rule_id}: {r.condition}" for r in rules[:8]],
                ),
                affected_components=tuple(paras) or ("<program>",),
                confidence=_CONF_DIRECT,
                recommended_mitigation=(
                    "Review each extracted rule with a domain owner, confirm intent, "
                    "and record the confirmed rules as the modernization spec."
                ),
                occurrence_count=len(rules),
            )
        ]

    def _detect_data_complexity(self, ar: AnalysisResult) -> list[ModernizationRisk]:
        """
        DATA DIVISION constructs the parser could not fully model
        (``UNMODELLED``/``UNSUPPORTED`` diagnostics originating in data
        definitions — COMP-3, edited pictures, FILE/LINKAGE sections).
        Aggregated. Severity: MEDIUM. Pure data-item *counts* are not used
        — they are not a reliable complexity signal on their own.
        """
        from app.parser.diagnostics.recovery import SyntaxCategory

        data_codes = {"SYN200", "SYN201", "SYN101", "SYN102"}
        diags = [
            d
            for d in ar.syntax_diagnostics
            if getattr(d, "code", "") in data_codes
            and getattr(d, "category", None)
            in (SyntaxCategory.UNSUPPORTED, SyntaxCategory.UNMODELLED)
        ]
        if not diags:
            return []
        by_code: dict[str, int] = defaultdict(int)
        for d in diags:
            by_code[getattr(d, "code", "SYN?")] += 1
        messages = sorted({str(getattr(d, "message", "")).strip() for d in diags})
        return [
            ModernizationRisk(
                risk_id="RISK-PENDING",
                category=RiskCategory.DATA_COMPLEXITY,
                severity=RiskSeverity.MEDIUM,
                title="Data definitions the parser cannot fully model",
                explanation=(
                    "The DATA DIVISION uses features (packed-decimal COMP-3, edited "
                    "pictures, FILE/LINKAGE sections) that are not represented in the "
                    "AST. Field layout, precision and I/O semantics for these items "
                    "must be reconstructed by hand during migration."
                ),
                evidence=(
                    "; ".join(f"{c}×{n}" for c, n in sorted(by_code.items())),
                    *[f"- {m}" for m in messages[:6]],
                ),
                source_locations=tuple(
                    p for p in (_pos_from_diag(d) for d in diags) if p is not None
                ),
                affected_components=("DATA DIVISION",),
                confidence=_CONF_DIRECT,
                recommended_mitigation=(
                    "Produce an explicit field map (name, type, precision, storage) "
                    "for every flagged item and validate it against sample data."
                ),
                occurrence_count=len(diags),
            )
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _max_if_depth(node: object, current: int = 0) -> int:
    """Deepest chain of nested ``IfStatementNode`` reachable from *node*."""
    if isinstance(node, IfStatementNode):
        depth = current + 1
        best = depth
        for child in list(node.then_statements) + list(node.else_statements):
            best = max(best, _max_if_depth(child, depth))
        return best
    if isinstance(node, PerformUntilStatementNode):
        best = current
        for child in node.statements:
            best = max(best, _max_if_depth(child, current))
        return best
    return current


def _strip_quotes(text: str) -> str:
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in {"'", '"'}:
        return t[1:-1]
    return t


def _category_slug(category: RiskCategory) -> str:
    return category.value.lower().replace("_", "-")


def _finalize(risks: list[ModernizationRisk]) -> list[ModernizationRisk]:
    # Deduplicate on structural key (keep first).
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    unique: list[ModernizationRisk] = []
    for risk in risks:
        key = risk.dedup_key()
        if key in seen:
            continue
        seen.add(key)
        unique.append(risk)

    def sort_key(r: ModernizationRisk) -> tuple:
        loc = r.source_locations[0] if r.source_locations else None
        return (
            SEVERITY_ORDER[r.severity],
            r.category.value,
            loc.filename if loc else "",
            loc.line if loc else 0,
            loc.column if loc else 0,
            r.title,
        )

    unique.sort(key=sort_key)

    # Assign IDs: per-category running ordinal in final order.
    counters: dict[RiskCategory, int] = defaultdict(int)
    result: list[ModernizationRisk] = []
    for risk in unique:
        counters[risk.category] += 1
        rid = f"RISK-{_category_slug(risk.category)}-{counters[risk.category]:03d}"
        result.append(replace(risk, risk_id=rid))
    return result
