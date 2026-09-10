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
    generate_boundary_values,
    parse_condition,
)
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

    parsed: list[tuple[dict[str, Any], str | None, Comparison]] = []
    for rule in bundle.business_rules or []:
        cmp = parse_condition(str(rule.get("condition", "")))
        para = _owning_paragraph(rule, spans)
        if cmp is not None:
            parsed.append((rule, para, cmp))

    # group by (paragraph, variable) — an IF/ELSE pair shares both
    groups: dict[tuple[str | None, str], list[tuple[dict[str, Any], Comparison]]] = {}
    for rule, para, cmp in parsed:
        groups.setdefault((para, cmp.variable), []).append((rule, cmp))

    tests: list[BehavioralTestCase] = []
    for (para, variable), members in sorted(
        groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1])
    ):
        values: dict[str, None] = {}
        for _rule, cmp in members:
            for v, _taken in generate_boundary_values(cmp):
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
                taken = _evaluate(cmp, value)
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

    tests.sort(key=lambda t: t.test_id)
    return BehavioralSuite(
        source_id=sid,
        extraction_version=EXTRACTION_VERSION,
        analysis_version=ANALYSIS_CONTRACT_VERSION,
        tests=tuple(tests),
    )


def _evaluate(cmp: Comparison, value: str) -> bool:
    op = cmp.effective_operator
    if cmp.is_numeric:
        v, n = int(value), int(cmp.literal)
        return {
            ">=": v >= n,
            "<=": v <= n,
            ">": v > n,
            "<": v < n,
            "=": v == n,
            "<>": v != n,
        }[op]
    if op == "=":
        return value == cmp.literal
    if op == "<>":
        return value != cmp.literal
    return False
