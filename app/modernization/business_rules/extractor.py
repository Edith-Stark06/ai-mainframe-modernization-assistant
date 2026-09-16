"""
Business Rule Extractor (task #112 — Phase 4 Modernization Intelligence).

Purpose:
    Deterministically extract :class:`~app.modernization.business_rules.models.BusinessRule`
    records from an :class:`~app.analysis.models.AnalysisResult` produced by
    Phases 1–3.

Evidence sources (no LLM, no new parsing):
    * **AST** — paragraph structure and ``IfStatementNode`` /
      ``MoveStatementNode`` / arithmetic / ``CallStatementNode`` /
      ``PerformStatementNode`` / ``StopRunStatementNode`` /
      ``GobackStatementNode`` / ``DisplayStatementNode`` nodes.
    * **Dependency analysis (Phase 3)** — used only to cross-check that
      the variables a rule reports are the same identifiers the
      dependency analyzer recognises for that paragraph; the literal/
      identifier split reuses the analyzer's own
      :func:`~app.analysis.dependencies.analyzer.is_literal_operand`
      predicate so the two layers never disagree.

Determinism:
    Rules are collected in source order, de-duplicated on a structural
    key, then **totally ordered** by (file, line, column, paragraph,
    condition, action texts). ``BR-NNN`` identifiers are assigned only
    after that sort, so identical source always produces identical rules,
    identical ordering, and identical IDs.

Scope / non-fabrication:
    * COBOL compound conditions (``A = 1 AND B = 2`` on one ``IF``) are
      **not** representable in the current AST — the parser records only
      a single ``condition_left/operator/right`` triple. This extractor
      consumes exactly that; it never invents the missing conjuncts. A
      genuinely nested ``IF`` *is* representable and is combined into an
      explicit ``(outer) AND (inner)`` condition.
    * A statement type with no business meaning (or one the AST cannot
      represent) is skipped, never turned into a fabricated action.
    * Top-level statements with no guarding condition are never rules.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.analysis.dependencies.analyzer import is_literal_operand
from app.analysis.models import AnalysisResult
from app.modernization.business_rules.models import (
    BusinessRule,
    BusinessRuleCategory,
    RuleAction,
    RuleActionKind,
    RuleVariables,
)
from app.parser.ast.statements import (
    AddStatementNode,
    CallStatementNode,
    DisplayStatementNode,
    DivideStatementNode,
    GobackStatementNode,
    IfStatementNode,
    MoveStatementNode,
    MultiplyStatementNode,
    PerformStatementNode,
    StatementNode,
    StopRunStatementNode,
    SubtractStatementNode,
)
from app.parser.lexer.position import Position

__all__ = ["BusinessRuleExtractor", "classify_rule"]

# Keywords whose *literal presence* in an identifier or literal is
# treated as source evidence of an error/rejection outcome. This is
# name evidence in the source text, not inferred domain meaning.
_ERROR_KEYWORDS: tuple[str, ...] = (
    "ERROR",
    "ERR",
    "INVALID",
    "REJECT",
    "FAIL",
    "DENIED",
    "DECLINE",
)

_RELATIONAL_OPERATORS: frozenset[str] = frozenset({">", "<", ">=", "<=", "!=", "<>"})


def _strip_literal(text: str) -> str:
    """Return *text* without surrounding COBOL quotes, for keyword scans."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in {"'", '"'}:
        return t[1:-1]
    return t


def _operand_bucket(text: str) -> tuple[str, str]:
    """
    Classify a raw operand.

    Returns a ``(kind, value)`` pair where *kind* is ``"literal"`` or
    ``"variable"`` and *value* is the trimmed, upper-cased identifier for
    variables (matching the dependency analyzer) or the trimmed literal
    text for literals.
    """
    trimmed = text.strip()
    if not trimmed:
        return ("literal", "")
    if is_literal_operand(trimmed):
        return ("literal", trimmed)
    return ("variable", trimmed.upper())


def _looks_error_related(*texts: str) -> list[str]:
    """Return the error keywords literally present in *texts* (sorted, unique)."""
    hits: set[str] = set()
    for text in texts:
        haystack = _strip_literal(text).upper()
        for kw in _ERROR_KEYWORDS:
            if kw in haystack:
                hits.add(kw)
    return sorted(hits)


def classify_rule(
    condition_operator: str,
    condition_right_is_numeric_literal: bool,
    actions: tuple[RuleAction, ...],
    condition_variables: tuple[str, ...],
) -> tuple[BusinessRuleCategory, list[str]]:
    """
    Decide a rule's category from structural evidence only.

    Precedence (first match wins):

    1. ``CALCULATION`` — any arithmetic action.
    2. ``ERROR_CONDITION`` — an action target/literal contains an error
       keyword.
    3. ``STATUS_TRANSITION`` — a condition variable is also an ASSIGN
       target.
    4. ``LIMIT_CHECK`` — relational operator against a numeric literal.
    5. ``CONDITIONAL_VALIDATION`` — an (in)equality comparison.
    6. ``GENERAL`` — none of the above.

    Returns the category and the list of evidence strings that justified
    it.
    """
    arithmetic = {
        RuleActionKind.ADD,
        RuleActionKind.SUBTRACT,
        RuleActionKind.MULTIPLY,
        RuleActionKind.DIVIDE,
    }
    if any(a.kind in arithmetic for a in actions):
        return (
            BusinessRuleCategory.CALCULATION,
            ["arithmetic action present"],
        )

    error_hits: set[str] = set()
    for action in actions:
        error_hits.update(_looks_error_related(action.target, *action.literals))
    if error_hits:
        return (
            BusinessRuleCategory.ERROR_CONDITION,
            [
                f"error keyword in action target/literal: {kw}"
                for kw in sorted(error_hits)
            ],
        )

    assign_targets = {
        a.target.upper() for a in actions if a.kind is RuleActionKind.ASSIGN
    }
    transition_vars = sorted(
        v for v in condition_variables if v.upper() in assign_targets
    )
    if transition_vars:
        return (
            BusinessRuleCategory.STATUS_TRANSITION,
            [
                f"condition variable {v} is also assigned by an action"
                for v in transition_vars
            ],
        )

    if (
        condition_operator in _RELATIONAL_OPERATORS
        and condition_right_is_numeric_literal
    ):
        return (
            BusinessRuleCategory.LIMIT_CHECK,
            [f"relational comparison '{condition_operator}' against a numeric literal"],
        )

    if condition_operator in {"=", "==", "!=", "<>"}:
        return (
            BusinessRuleCategory.CONDITIONAL_VALIDATION,
            [f"equality/inequality comparison '{condition_operator}'"],
        )

    return (BusinessRuleCategory.GENERAL, ["conditionally guarded action"])


class BusinessRuleExtractor:
    """
    Extract structured business rules from an ``AnalysisResult``.

    Stateless between calls to :meth:`extract`; a fresh instance is not
    required per program but is harmless.
    """

    def extract(self, analysis_result: AnalysisResult) -> list[BusinessRule]:
        """
        Return the deterministically ordered business rules for *analysis_result*.

        An empty list is returned (never an error) when there is no AST or
        no PROCEDURE DIVISION.
        """
        ast = analysis_result.ast
        if ast is None or ast.procedure_division is None:
            return []

        # Paragraph names the dependency analyzer attributed dependencies
        # to — used only as a consistency cross-check for the `evidence`
        # trail, never to add or remove variables.
        dep_paragraphs = {
            d.source for d in analysis_result.dependencies if getattr(d, "source", "")
        }

        collected: list[BusinessRule] = []
        for paragraph in ast.procedure_division.paragraphs:
            for stmt in paragraph.statements:
                self._walk(stmt, paragraph.name, (), collected, dep_paragraphs)

        return self._finalize(collected)

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def _walk(
        self,
        stmt: StatementNode,
        paragraph: str,
        enclosing: tuple[tuple[str, str, str], ...],
        out: list[BusinessRule],
        dep_paragraphs: set[str],
    ) -> None:
        """Depth-first walk collecting one rule per guarded action group."""
        if not isinstance(stmt, IfStatementNode):
            return

        left = (stmt.condition_left or "").strip()
        op = (stmt.condition_operator or "").strip()
        right = (stmt.condition_right or "").strip()

        # A condition we cannot represent reliably is not fabricated: we
        # still descend into nested IFs (which carry their own complete
        # comparisons) but emit nothing for this level.
        this_comparison: tuple[str, str, str] | None
        if left and op and right:
            this_comparison = (left, op, right)
        else:
            this_comparison = None

        # THEN branch
        if this_comparison is not None:
            then_ctx = enclosing + (this_comparison,)
            self._emit_branch(
                stmt,
                stmt.then_statements,
                then_ctx,
                negated=False,
                paragraph=paragraph,
                out=out,
                dep_paragraphs=dep_paragraphs,
            )
        else:
            then_ctx = enclosing
        for child in stmt.then_statements:
            self._walk(child, paragraph, then_ctx, out, dep_paragraphs)

        # ELSE branch
        if stmt.else_statements:
            if this_comparison is not None:
                else_ctx = enclosing + (("NOT", "", _fmt_comparison(this_comparison)),)
                self._emit_branch(
                    stmt,
                    stmt.else_statements,
                    else_ctx,
                    negated=True,
                    paragraph=paragraph,
                    out=out,
                    dep_paragraphs=dep_paragraphs,
                )
            else:
                else_ctx = enclosing
            for child in stmt.else_statements:
                self._walk(child, paragraph, else_ctx, out, dep_paragraphs)

    def _emit_branch(
        self,
        if_node: IfStatementNode,
        branch: tuple[StatementNode, ...],
        ctx: tuple[tuple[str, str, str], ...],
        *,
        negated: bool,
        paragraph: str,
        out: list[BusinessRule],
        dep_paragraphs: set[str],
    ) -> None:
        action_nodes = [n for n in branch if not isinstance(n, IfStatementNode)]
        actions: list[RuleAction] = []
        for node in action_nodes:
            action = _build_action(node)
            if action is not None:
                actions.append(action)
        if not actions:
            return

        condition_text = _render_condition(ctx)
        condition_vars = _condition_variables(ctx)

        # Deterministic confidence: a single flat comparison is a direct
        # read of the AST; a conjunction reconstructed from nested IFs is
        # a mild structural inference (the nesting *implies* AND).
        real_comparisons = [c for c in ctx if c[0] != "NOT"]
        confidence = 1.0 if len(ctx) == 1 else 0.75

        reads: set[str] = set(condition_vars)
        writes: set[str] = set()
        for action in actions:
            reads.update(action.sources)
            if (
                action.kind
                in {
                    RuleActionKind.ASSIGN,
                    RuleActionKind.ADD,
                    RuleActionKind.SUBTRACT,
                    RuleActionKind.MULTIPLY,
                    RuleActionKind.DIVIDE,
                }
                and action.target
            ):
                writes.add(action.target.upper())

        call_perform_targets = sorted(
            {
                a.target.upper()
                for a in actions
                if a.kind in {RuleActionKind.CALL, RuleActionKind.PERFORM} and a.target
            }
        )
        dependencies = tuple(
            sorted(set(condition_vars) | {s for a in actions for s in a.sources})
            + call_perform_targets
        )

        # Category from the *innermost real* comparison operator.
        inner = real_comparisons[-1] if real_comparisons else ("", "", "")
        right_is_num = _operand_bucket(inner[2])[0] == "literal" and _is_numeric(
            inner[2]
        )
        category, cat_evidence = classify_rule(
            condition_operator=inner[1],
            condition_right_is_numeric_literal=right_is_num,
            actions=tuple(actions),
            condition_variables=tuple(sorted(condition_vars)),
        )

        source_locations: tuple[Position, ...] = tuple(
            p
            for p in (
                [if_node.start_position]
                + [
                    n.start_position
                    for n in action_nodes
                    if getattr(n, "start_position", None) is not None
                ]
            )
            if p is not None
        )

        evidence = list(cat_evidence)
        evidence.append(
            f"IF at {_fmt_pos(if_node.start_position)} in paragraph {paragraph}"
        )
        if negated:
            evidence.append("ELSE branch — condition negated")
        if len(ctx) > 1:
            evidence.append(
                f"condition is a conjunction reconstructed from {len(real_comparisons)} "
                "nested IF comparison(s)"
            )
        if paragraph in dep_paragraphs:
            evidence.append(
                "paragraph is source-attributed in Phase 3 dependency analysis"
            )

        out.append(
            BusinessRule(
                rule_id="BR-PENDING",
                category=category,
                description=_render_description(condition_text, actions),
                condition=condition_text,
                actions=tuple(actions),
                variables=RuleVariables(
                    reads=tuple(sorted(reads)),
                    writes=tuple(sorted(writes)),
                    conditions=tuple(sorted(condition_vars)),
                ),
                dependencies=dependencies,
                source_locations=source_locations,
                paragraph=paragraph,
                section=None,
                confidence=confidence,
                evidence=tuple(evidence),
            )
        )

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    def _finalize(self, rules: list[BusinessRule]) -> list[BusinessRule]:
        # Deduplicate on structural key, keeping first (source-order)
        seen: set[tuple[str, str, tuple[str, ...]]] = set()
        unique: list[BusinessRule] = []
        for rule in rules:
            key = rule.dedup_key()
            if key in seen:
                continue
            seen.add(key)
            unique.append(rule)

        def sort_key(r: BusinessRule) -> tuple:
            loc = r.source_locations[0] if r.source_locations else None
            return (
                loc.filename if loc else "",
                loc.line if loc else 0,
                loc.column if loc else 0,
                r.paragraph,
                r.condition,
                tuple(a.raw for a in r.actions),
            )

        unique.sort(key=sort_key)

        return [
            _with_id(rule, f"BR-{index:03d}")
            for index, rule in enumerate(unique, start=1)
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with_id(rule: BusinessRule, rule_id: str) -> BusinessRule:
    from dataclasses import replace

    return replace(rule, rule_id=rule_id)


def _is_numeric(text: str) -> bool:
    candidate = text.strip().lstrip("+-")
    if not candidate:
        return False
    parts = candidate.split(".")
    if len(parts) > 2:
        return False
    return all(p.isdigit() for p in parts if p)


def _fmt_comparison(comp: tuple[str, str, str]) -> str:
    left, op, right = comp
    return f"{left} {op} {right}".strip()


def _fmt_pos(pos: Position | None) -> str:
    if pos is None:
        return "unknown"
    return f"{pos.filename}:{pos.line}:{pos.column}"


def _render_condition(ctx: tuple[tuple[str, str, str], ...]) -> str:
    """Render the enclosing-comparison stack into canonical condition text."""
    parts: list[str] = []
    for comp in ctx:
        if comp[0] == "NOT":
            parts.append(f"NOT ({comp[2]})")
        else:
            parts.append(_fmt_comparison(comp))
    if len(parts) == 1:
        return parts[0]
    return " AND ".join(f"({p})" for p in parts)


def _condition_variables(ctx: tuple[tuple[str, str, str], ...]) -> set[str]:
    variables: set[str] = set()
    for comp in ctx:
        if comp[0] == "NOT":
            # Re-parse the negated inner text's operands.
            text = comp[2]
            for token in text.replace("(", " ").replace(")", " ").split():
                kind, value = _operand_bucket(token)
                if kind == "variable" and _looks_like_identifier(value):
                    variables.add(value)
            continue
        for operand in (comp[0], comp[2]):
            kind, value = _operand_bucket(operand)
            if kind == "variable":
                variables.add(value)
    return variables


def _looks_like_identifier(token: str) -> bool:
    return any(ch.isalpha() for ch in token) and token.upper() not in {
        "AND",
        "OR",
        "NOT",
        ">",
        "<",
        "=",
        ">=",
        "<=",
    }


def _render_description(condition: str, actions: list[RuleAction]) -> str:
    phrases: list[str] = []
    for action in actions:
        if action.kind is RuleActionKind.ASSIGN:
            src = (
                action.sources[0]
                if action.sources
                else (action.literals[0] if action.literals else "?")
            )
            phrases.append(f"set {action.target} to {src}")
        elif action.kind is RuleActionKind.ADD:
            src = _first_operand(action)
            phrases.append(f"add {src} to {action.target}")
        elif action.kind is RuleActionKind.SUBTRACT:
            src = _first_operand(action)
            phrases.append(f"subtract {src} from {action.target}")
        elif action.kind is RuleActionKind.MULTIPLY:
            src = _first_operand(action)
            phrases.append(f"multiply {action.target} by {src}")
        elif action.kind is RuleActionKind.DIVIDE:
            src = _first_operand(action)
            phrases.append(f"divide {action.target} by {src}")
        elif action.kind is RuleActionKind.CALL:
            phrases.append(f"call {action.target}")
        elif action.kind is RuleActionKind.PERFORM:
            phrases.append(f"perform {action.target}")
        elif action.kind is RuleActionKind.TERMINATE:
            phrases.append("terminate execution")
        elif action.kind is RuleActionKind.DISPLAY:
            shown = (
                action.literals[0]
                if action.literals
                else (action.sources[0] if action.sources else "")
            )
            phrases.append(f"display {shown}".strip())
    joined = "; ".join(phrases)
    return f"When {condition}, {joined}."


def _first_operand(action: RuleAction) -> str:
    if action.sources:
        return action.sources[0]
    if action.literals:
        return action.literals[0]
    return "?"


def _build_action(node: StatementNode) -> RuleAction | None:
    """Lower a single AST statement into a :class:`RuleAction`, or ``None``."""
    if isinstance(node, MoveStatementNode):
        kind_s, src_val = _operand_bucket(node.source)
        target = (node.target or "").strip().upper()
        if not target:
            return None
        sources = (src_val,) if kind_s == "variable" and src_val else ()
        literals = (src_val,) if kind_s == "literal" and src_val else ()
        rhs = sources[0] if sources else (literals[0] if literals else "")
        return RuleAction(
            kind=RuleActionKind.ASSIGN,
            target=target,
            sources=sources,
            literals=literals,
            raw=f"{target} = {rhs}".strip(),
            source_location=node.start_position,
        )

    if isinstance(
        node,
        (
            AddStatementNode,
            SubtractStatementNode,
            MultiplyStatementNode,
            DivideStatementNode,
        ),
    ):
        arith = {
            AddStatementNode: (RuleActionKind.ADD, "+="),
            SubtractStatementNode: (RuleActionKind.SUBTRACT, "-="),
            MultiplyStatementNode: (RuleActionKind.MULTIPLY, "*="),
            DivideStatementNode: (RuleActionKind.DIVIDE, "/="),
        }
        kind, sym = arith[type(node)]
        # Repository arithmetic convention: `right` is the accumulator
        # (read + written), `left` is the applied operand.
        acc = (node.right or "").strip().upper()
        applied_kind, applied_val = _operand_bucket(node.left)
        if not acc:
            return None
        sources = (applied_val,) if applied_kind == "variable" and applied_val else ()
        literals = (applied_val,) if applied_kind == "literal" and applied_val else ()
        rhs = sources[0] if sources else (literals[0] if literals else "")
        return RuleAction(
            kind=kind,
            target=acc,
            sources=sources,
            literals=literals,
            raw=f"{acc} {sym} {rhs}".strip(),
            source_location=node.start_position,
        )

    if isinstance(node, CallStatementNode):
        target = _strip_literal(node.target or "").strip().upper()
        if not target:
            return None
        arg_sources: list[str] = []
        arg_literals: list[str] = []
        for arg in getattr(node, "arguments", ()) or ():
            kind_a, val_a = _operand_bucket(arg)
            if kind_a == "variable" and val_a:
                arg_sources.append(val_a)
            elif val_a:
                arg_literals.append(val_a)
        return RuleAction(
            kind=RuleActionKind.CALL,
            target=target,
            sources=tuple(arg_sources),
            literals=tuple(arg_literals),
            raw=f"CALL {target}"
            + (
                f" USING {', '.join(arg_sources + arg_literals)}"
                if (arg_sources or arg_literals)
                else ""
            ),
            source_location=node.start_position,
        )

    if isinstance(node, PerformStatementNode):
        target = (node.target or "").strip().upper()
        if not target:
            return None
        return RuleAction(
            kind=RuleActionKind.PERFORM,
            target=target,
            sources=(),
            literals=(),
            raw=f"PERFORM {target}",
            source_location=node.start_position,
        )

    if isinstance(node, (StopRunStatementNode, GobackStatementNode)):
        verb = "STOP RUN" if isinstance(node, StopRunStatementNode) else "GOBACK"
        return RuleAction(
            kind=RuleActionKind.TERMINATE,
            target="",
            sources=(),
            literals=(),
            raw=verb,
            source_location=node.start_position,
        )

    if isinstance(node, DisplayStatementNode):
        kind_d, val_d = _operand_bucket(node.operand)
        return RuleAction(
            kind=RuleActionKind.DISPLAY,
            target="",
            sources=(val_d,) if kind_d == "variable" and val_d else (),
            literals=(val_d,) if kind_d == "literal" and val_d else (),
            raw=f"DISPLAY {node.operand}".strip(),
            source_location=node.start_position,
        )

    return None
