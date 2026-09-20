"""
#129 — deterministic behavioral test extraction from Phase 1-5 analysis.

Only business rules with a single parseable comparison condition
(``[NOT] <var> <op> <literal>``) are turned into boundary-partitioned
:class:`BehavioralTestCase` objects. Rules sharing a paragraph + the same
condition variable (the common ``IF ... ELSE`` pair) are grouped so one
boundary value produces one test that records whichever rule actually
fires — never a fabricated "nothing happens" expectation.

Nothing here re-implements COBOL semantics: the condition, the action
kind/target/literal and the source locations all come straight from the
existing business-rule engine (Phase 4) and the existing Java generator's
stub markers (Phase 9) decide executability.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.dataset.analysis_bundle import AnalysisBundle
from app.behavioral.extraction.conditions import (
    Comparison,
    CompoundComparison,
    evaluate_term,
    generate_boundary_values,
    generate_compound_boundary_values,
    parse_compound_condition,
    parse_condition,
    strip_string_literal,
)
from app.behavioral.extraction.loops import extract_loop_tests
from app.behavioral.extraction.models import (
    BehavioralSuite,
    BehavioralTestCase,
    ExpectedBranch,
    ExpectedCalculation,
    ExpectedError,
    ExpectedOutput,
    ExpectedStateChange,
    InputSource,
    InputValue,
)
from app.behavioral.version import ANALYSIS_CONTRACT_VERSION, EXTRACTION_VERSION
from app.java_modernization.architecture.models import SourceRef

__all__ = ["extract_behavioral_tests"]

_ERROR_CATEGORIES = frozenset({"ERROR_CONDITION", "CONDITIONAL_VALIDATION"})
_ARITH_OPS = {
    "ADD": lambda a, b: a + b,
    "SUBTRACT": lambda a, b: a - b,
    "MULTIPLY": lambda a, b: a * b,
    "DIVIDE": lambda a, b: a // b if b else None,
}
_TODO_RE = re.compile(
    r"//\s*TODO:\s*implement\s+(?:CALL/PERFORM|[A-Z/]+)\s+target\s+'([^']+)'\s*\(([A-Z0-9]+)\)"
)
_METHOD_RE = re.compile(
    r"^[ \t]{2,}(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ]+?\s+(\w+)\s*\("
    r"[^;{]*\)\s*\{",
    re.MULTILINE,
)


def _decamel(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).upper()


def _collect_condition_name_values(
    ast: dict[str, Any] | None,
) -> dict[str, tuple[str, ...]]:
    """``{CONDITION-NAME: (declared value, ...)}`` straight off the real
    DATA DIVISION AST — the only source of truth for what a level-88
    condition-name's ``VALUE``/``VALUES`` clause actually declared (see
    ``app/parser/ast/data_items.py::ConditionNameNode.values``,
    ``docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md``). Never guessed or
    hard-coded: a condition-name absent here (no DATA DIVISION, no
    WORKING-STORAGE SECTION, or genuinely no such declaration) simply
    yields no boundary values downstream — see
    :func:`app.behavioral.extraction.conditions.generate_boundary_values`.

    Only WORKING-STORAGE is walked, matching the parser's own scope (the
    only DATA DIVISION section it represents in the AST); the section's
    ``items`` is already a flat list (no subordinate-item nesting in this
    parser), so no recursive walk is needed.
    """
    if not ast:
        return {}
    ws = ((ast.get("data_division") or {}).get("working_storage")) or {}
    out: dict[str, tuple[str, ...]] = {}
    for item in ws.get("items", []) or []:
        if not isinstance(item, dict) or item.get("level") != 88:
            continue
        name = str(item.get("name", "")).strip().upper()
        raw_values = item.get("values") or []
        if name and raw_values:
            out[name] = tuple(strip_string_literal(str(v)) for v in raw_values)
    return out


def _collect_condition_name_parents(ast: dict[str, Any] | None) -> dict[str, str]:
    """``{CONDITION-NAME: parent data item}`` off the real DATA DIVISION AST.

    A level-88 entry is subordinate to the nearest preceding non-88 item in
    the (flat) WORKING-STORAGE item list. Several condition-names can share
    one parent -- they are all conditions on that single storage location --
    so compound-condition evidence must assign the *parent*, not each
    condition-name independently (see
    :func:`~app.behavioral.extraction.conditions.generate_compound_boundary_values`).
    """
    if not ast:
        return {}
    ws = ((ast.get("data_division") or {}).get("working_storage")) or {}
    parents: dict[str, str] = {}
    current: str | None = None
    for item in ws.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().upper()
        if item.get("level") == 88:
            if name and current:
                parents[name] = current
        elif name:
            current = name
    return parents


def _paragraph_spans(source: str, names: list[str]) -> dict[str, tuple[int, int]]:
    lines = source.splitlines()
    want = {n.upper() for n in names}
    headers = [
        (raw.strip().rstrip(".").upper(), i)
        for i, raw in enumerate(lines, start=1)
        if raw.strip().rstrip(".").upper() in want
    ]
    spans: dict[str, tuple[int, int]] = {}
    for idx, (name, start) in enumerate(headers):
        end = headers[idx + 1][1] - 1 if idx + 1 < len(headers) else len(lines)
        spans[name] = (start, end)
    return spans


def _owning_paragraph(
    rule: dict[str, Any], spans: dict[str, tuple[int, int]]
) -> str | None:
    lines = sorted(
        loc["line"]
        for loc in rule.get("source_locations", [])
        if isinstance(loc.get("line"), int)
    )
    if not lines:
        return None
    ln = lines[0]
    for name, (s, e) in spans.items():
        if s <= ln <= e:
            return name
    return None


def _rule_source_refs(
    rule: dict[str, Any], source_id: str, path: str, paragraph: str | None
) -> tuple[SourceRef, ...]:
    lines = sorted(
        loc["line"]
        for loc in rule.get("source_locations", [])
        if isinstance(loc.get("line"), int)
    )
    if not lines:
        return ()
    return (
        SourceRef(
            source_id=source_id,
            source_path=path,
            line_start=lines[0],
            line_end=lines[-1],
            paragraph=paragraph,
        ),
    )


def _stub_paragraphs(java_source: str) -> dict[str, str]:
    """``{PARAGRAPH: diagnostic_code}`` for generator ``// TODO`` stubs."""
    out: dict[str, str] = {}
    for m in _TODO_RE.finditer(java_source or ""):
        out[m.group(1).upper()] = m.group(2)
    return out


def _represented_paragraphs(java_source: str, entry_paragraph: str | None) -> set[str]:
    """Paragraph names that have *some* representation (real or stub) in
    the generated Java — i.e. are reachable from the entry point. A
    paragraph never PERFORMed has neither a method nor a stub and is
    simply absent, which is a distinct (and equally non-executable) gap.
    """
    out: set[str] = set()
    if entry_paragraph:
        out.add(entry_paragraph.upper())
    for m in _METHOD_RE.finditer(java_source or ""):
        name = m.group(1)
        if name != "main":
            out.add(_decamel(name))
    return out


def _test_id(source_id: str, paragraph: str, variable: str, value: str) -> str:
    h = hashlib.sha256(
        f"{source_id}\x1f{paragraph}\x1f{variable}\x1f{value}".encode("utf-8")
    ).hexdigest()
    return f"BT-{h[:8]}"


def _apply_action(
    action: dict[str, Any], input_value: str, comparison_var: str
) -> tuple[
    ExpectedStateChange | None, ExpectedOutput | None, ExpectedCalculation | None
]:
    kind = str(action.get("kind", "")).upper()
    target = str(action.get("target", "")).strip()
    literals = action.get("literals") or []
    lit = str(literals[0]).strip("'\"") if literals else ""

    if kind == "DISPLAY":
        value = lit if literals and str(literals[0]).startswith(('"', "'")) else lit
        return (
            None,
            ExpectedOutput(name="stdout", kind="display", expected_value=value),
            None,
        )

    if kind == "ASSIGN" and target:
        out = ExpectedOutput(name=target, kind="field", expected_value=lit)
        state = ExpectedStateChange(field=target, from_value=None, to_value=lit)
        return state, out, None

    if kind in _ARITH_OPS and target:
        op_symbol = {"ADD": "+", "SUBTRACT": "-", "MULTIPLY": "*", "DIVIDE": "/"}[kind]
        calc = ExpectedCalculation(
            target=target,
            operator=op_symbol,
            operands=(target, lit),
            raw=str(action.get("raw", "")),
        )
        # only computable when the action target IS the boundary variable
        # (the common case for a self-referencing accumulator) and both
        # sides are integer literals — otherwise leave the result implicit.
        if target.upper() == comparison_var.upper() and lit.lstrip("-").isdigit():
            try:
                start = int(input_value)
                result = _ARITH_OPS[kind](start, int(lit))
            except (ValueError, TypeError):
                result = None
            if result is not None:
                calc = ExpectedCalculation(
                    target=target,
                    operator=op_symbol,
                    operands=(input_value, lit),
                    raw=str(action.get("raw", "")),
                )
                out = ExpectedOutput(
                    name=target, kind="field", expected_value=str(result)
                )
                state = ExpectedStateChange(
                    field=target, from_value=input_value, to_value=str(result)
                )
                return state, out, calc
        return None, None, calc

    return None, None, None


def _build_compound_tests(
    *,
    rule: dict[str, Any],
    para: str | None,
    compound: CompoundComparison,
    condition_name_values: dict[str, tuple[str, ...]],
    condition_name_parents: dict[str, str],
    stub_code: str | None,
    represented: set[str],
    unsupported_codes: list[str],
    sid: str,
    path: str,
) -> list[BehavioralTestCase]:
    """One :class:`BehavioralTestCase` per boundary case
    :func:`~app.behavioral.extraction.conditions.generate_compound_boundary_values`
    derives for *rule*'s compound condition. Mirrors the single-term loop
    in :func:`extract_behavioral_tests` exactly (same executability
    checks, same action application, same error/category handling) --
    the only structural difference is *inputs* holding one
    :class:`InputValue` per distinct variable in the compound instead of
    always exactly one.
    """
    known_values_map = {
        t.variable: condition_name_values.get(t.variable, ()) for t in compound.terms
    }
    cases = generate_compound_boundary_values(
        compound, known_values_map, condition_name_parents
    )
    rid = str(rule.get("rule_id", ""))

    tests: list[BehavioralTestCase] = []
    for values_by_variable, holds in cases:
        variables_in_order = sorted(values_by_variable)
        outputs: list[ExpectedOutput] = []
        states: list[ExpectedStateChange] = []
        calcs: list[ExpectedCalculation] = []
        errors: list[ExpectedError] = []
        rule_ids: list[str] = []
        source_refs: list[SourceRef] = []

        branch = ExpectedBranch(
            branch_id=f"{para or sid}.{rid}.IF.{str(holds).lower()}",
            paragraph=para or sid,
            condition=compound.raw,
            taken=holds,
        )

        if holds:
            rule_ids.append(rid)
            source_refs.extend(_rule_source_refs(rule, sid, path, para))
            for action in rule.get("actions", []):
                # No single variable is "the" comparison variable for a
                # multi-variable compound condition -- passing "" means
                # _apply_action's self-referencing-accumulator special
                # case (which requires target == comparison_var) can
                # never spuriously match, so an ambiguous case is left
                # implicit rather than guessed at.
                state, out, calc = _apply_action(action, "", "")
                if state:
                    states.append(state)
                if out:
                    outputs.append(out)
                if calc:
                    calcs.append(calc)
            if str(rule.get("category", "")).upper() in _ERROR_CATEGORIES:
                errors.append(
                    ExpectedError(
                        category=str(rule.get("category")),
                        description=str(rule.get("description", "")),
                        observable=bool(outputs or states),
                    )
                )

        executable = True
        reason = None
        if para and para.upper() not in represented:
            executable = False
            reason = (
                f"paragraph {para} has no representation in the generated "
                f"Java (never PERFORMed from the entry paragraph)"
            )
        elif stub_code:
            executable = False
            reason = (
                f"generated Java does not implement paragraph {para} "
                f"(generator diagnostic {stub_code})"
            )
        elif unsupported_codes:
            executable = False
            reason = "source contains unsupported/unmodelled syntax: " + ", ".join(
                sorted(set(unsupported_codes))
            )

        composite_variable = "+".join(variables_in_order)
        composite_value = "|".join(
            f"{var}={values_by_variable[var]}" for var in variables_in_order
        )
        tid = _test_id(sid, para or sid, composite_variable, composite_value)
        description_values = ", ".join(
            f"{var}={values_by_variable[var]}" for var in variables_in_order
        )
        tests.append(
            BehavioralTestCase(
                test_id=tid,
                name=f"{sid}:{para or sid}:{composite_variable}={composite_value}",
                description=(
                    f"{description_values} in paragraph {para or sid}"
                    + (f" (fires {rid})" if rule_ids else " (no rule fires)")
                ),
                inputs=tuple(
                    InputValue(
                        name=var,
                        value=values_by_variable[var],
                        source=InputSource.BOUNDARY_GENERATED,
                        partition_of=compound.raw,
                    )
                    for var in variables_in_order
                ),
                expected_branches=(branch,),
                expected_calculations=tuple(calcs),
                expected_outputs=tuple(outputs),
                expected_errors=tuple(errors),
                expected_state_changes=tuple(states),
                source_refs=tuple(source_refs),
                business_rule_ids=tuple(sorted(set(rule_ids))),
                confidence="high" if (outputs or states or errors) else "low",
                executable=executable,
                inconclusive_reason=reason,
                extraction_version=EXTRACTION_VERSION,
                source_id=sid,
            )
        )
    return tests


def extract_behavioral_tests(bundle: AnalysisBundle) -> BehavioralSuite:
    sid = bundle.source_id
    path = f"{sid}.cbl"
    spans = _paragraph_spans(bundle.source, list(bundle.paragraphs))
    stubs = _stub_paragraphs(bundle.java_backend_output)
    entry_paragraph = bundle.paragraphs[0] if bundle.paragraphs else None
    represented = _represented_paragraphs(bundle.java_backend_output, entry_paragraph)
    unsupported_codes = list(
        ((bundle.coverage or {}).get("unsupported_syntax") or {}).get("codes", [])
    )
    condition_name_values = _collect_condition_name_values(bundle.ast)
    condition_name_parents = _collect_condition_name_parents(bundle.ast)

    parsed: list[tuple[dict[str, Any], str | None, Comparison]] = []
    handled_rule_ids: set[str] = set()
    for rule in bundle.business_rules or []:
        cmp = parse_condition(str(rule.get("condition", "")))
        para = _owning_paragraph(rule, spans)
        if cmp is not None:
            parsed.append((rule, para, cmp))
            handled_rule_ids.add(str(rule.get("rule_id", "")))

    # group by (paragraph, variable) — an IF/ELSE pair shares both
    groups: dict[tuple[str | None, str], list[tuple[dict[str, Any], Comparison]]] = {}
    for rule, para, cmp in parsed:
        groups.setdefault((para, cmp.variable), []).append((rule, cmp))

    tests: list[BehavioralTestCase] = []
    for (para, variable), members in sorted(
        groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])
    ):
        known_values = condition_name_values.get(variable, ())
        values: dict[str, None] = {}
        for _rule, cmp in members:
            for v, _taken in generate_boundary_values(cmp, known_values):
                values[v] = None

        stub_code = stubs.get(para or "", None)
        for value in sorted(values, key=lambda v: (len(v), v)):
            branches: list[ExpectedBranch] = []
            outputs: list[ExpectedOutput] = []
            states: list[ExpectedStateChange] = []
            calcs: list[ExpectedCalculation] = []
            errors: list[ExpectedError] = []
            rule_ids: list[str] = []
            source_refs: list[SourceRef] = []

            for rule, cmp in members:
                taken = _evaluate(cmp, value, known_values)
                rid = str(rule.get("rule_id", ""))
                branches.append(
                    ExpectedBranch(
                        branch_id=f"{para or sid}.{rid}.IF.{str(taken).lower()}",
                        paragraph=para or sid,
                        condition=cmp.raw,
                        taken=taken,
                    )
                )
                if not taken:
                    continue
                rule_ids.append(rid)
                source_refs.extend(_rule_source_refs(rule, sid, path, para))
                for action in rule.get("actions", []):
                    state, out, calc = _apply_action(action, value, variable)
                    if state:
                        states.append(state)
                    if out:
                        outputs.append(out)
                    if calc:
                        calcs.append(calc)
                if str(rule.get("category", "")).upper() in _ERROR_CATEGORIES:
                    errors.append(
                        ExpectedError(
                            category=str(rule.get("category")),
                            description=str(rule.get("description", "")),
                            observable=bool(outputs or states),
                        )
                    )

            executable = True
            reason = None
            if para and para.upper() not in represented:
                executable = False
                reason = (
                    f"paragraph {para} has no representation in the generated "
                    f"Java (never PERFORMed from the entry paragraph)"
                )
            elif stub_code:
                executable = False
                reason = (
                    f"generated Java does not implement paragraph {para} "
                    f"(generator diagnostic {stub_code})"
                )
            elif unsupported_codes:
                executable = False
                reason = "source contains unsupported/unmodelled syntax: " + ", ".join(
                    sorted(set(unsupported_codes))
                )
            elif not (outputs or states) and not errors:
                # a boundary where no rule fired and nothing is asserted —
                # still a legitimate branch-coverage case, just weaker evidence
                pass

            tid = _test_id(sid, para or sid, variable, value)
            fired = [rid for rid in rule_ids]
            tests.append(
                BehavioralTestCase(
                    test_id=tid,
                    name=f"{sid}:{para or sid}:{variable}={value}",
                    description=(
                        f"{variable} = {value} in paragraph {para or sid}"
                        + (
                            f" (fires {', '.join(fired)})"
                            if fired
                            else " (no rule fires)"
                        )
                    ),
                    inputs=(
                        InputValue(
                            name=variable,
                            value=value,
                            source=InputSource.BOUNDARY_GENERATED,
                            partition_of=members[0][1].raw,
                        ),
                    ),
                    expected_branches=tuple(branches),
                    expected_calculations=tuple(calcs),
                    expected_outputs=tuple(outputs),
                    expected_errors=tuple(errors),
                    expected_state_changes=tuple(states),
                    source_refs=tuple(source_refs),
                    business_rule_ids=tuple(sorted(set(rule_ids))),
                    confidence="high" if (outputs or states or errors) else "low",
                    executable=executable,
                    inconclusive_reason=reason,
                    extraction_version=EXTRACTION_VERSION,
                    source_id=sid,
                )
            )

    # STEP 14: compound AND/OR conditions -- a business rule whose
    # condition parse_condition alone cannot represent (it was excluded
    # from `parsed` above) but parse_compound_condition can, additive to
    # the single-term tests above, never replacing them. Only rules not
    # already handled by the single-term path are considered (a rule is
    # never double-counted).
    for rule in bundle.business_rules or []:
        rid = str(rule.get("rule_id", ""))
        if rid in handled_rule_ids:
            continue
        compound = parse_compound_condition(str(rule.get("condition", "")))
        if compound is None:
            continue  # genuinely unparseable -- excluded, same as today
        para = _owning_paragraph(rule, spans)
        tests.extend(
            _build_compound_tests(
                rule=rule,
                para=para,
                compound=compound,
                condition_name_values=condition_name_values,
                condition_name_parents=condition_name_parents,
                stub_code=stubs.get(para or "", None),
                represented=represented,
                unsupported_codes=unsupported_codes,
                sid=sid,
                path=path,
            )
        )

    # MMIM v2 extractor upgrade: deterministic PERFORM UNTIL loop/
    # accumulator tests, additive to the #129 IF/ELSE boundary tests
    # above — never replacing them (see app.behavioral.extraction.loops).
    loop_tests, skipped_loops = extract_loop_tests(bundle)
    tests.extend(loop_tests)

    tests.sort(key=lambda t: t.test_id)
    return BehavioralSuite(
        source_id=sid,
        extraction_version=EXTRACTION_VERSION,
        analysis_version=ANALYSIS_CONTRACT_VERSION,
        tests=tuple(tests),
        skipped_loops=tuple(skipped_loops),
    )


def _evaluate(cmp: Comparison, value: str, known_values: tuple[str, ...] = ()) -> bool:
    # Delegates to conditions.evaluate_term, the single canonical
    # implementation compound-condition evaluation (evaluate_compound)
    # also uses, so a term's truth value is never derived two different
    # ways depending on whether it appears alone or inside a compound.
    return evaluate_term(cmp, value, known_values)
