"""
MMIM v2 extractor upgrade — deterministic loop/accumulator behavioral
test derivation for ``PERFORM UNTIL`` blocks.

This is an *additive* companion to :mod:`app.behavioral.extraction.extractor`
(the original #129 single-comparison IF/ELSE boundary extractor, left
completely unmodified). It only emits a test for a loop when every
instruction in the loop body is one of a small, explicitly whitelisted
set (``MOVE``/``ADD``/``SUBTRACT``/``MULTIPLY``/``DIVIDE`` against a
statically-known integer, plus one level of ``IF``/``ELSE``), every
variable the loop touches has a statically-known integer initial value
(from a ``WORKING-STORAGE`` ``VALUE`` clause), and the loop's exit
boundary is a plain integer literal.

Given that, the loop is a closed, finite state machine over integers —
deriving its terminal state is a **bounded, deterministic simulation of
the already-parsed IR**, not an execution of arbitrary COBOL. A hard
iteration cap (``_MAX_ITERATIONS``) guarantees the simulation itself
always terminates even if the analyzed program's loop would not.

Anything outside that narrow shape (a CALL inside the loop, a nested
PERFORM UNTIL, an unresolvable operand, a non-literal exit boundary, a
decimal literal — which hits a separate, pre-existing lexer limitation,
see ``docs/MMIM_VALIDATION_EXTRACTOR_AUDIT.md``) is recorded as a
:class:`~app.behavioral.extraction.models.LoopSkipRecord` with the exact
reason, never guessed at.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.behavioral.extraction.conditions import Comparison, generate_boundary_values
from app.behavioral.extraction.models import (
    BehavioralTestCase,
    ExpectedOutput,
    ExpectedStateChange,
    InputSource,
    InputValue,
    LoopSkipRecord,
)
from app.behavioral.version import EXTRACTION_VERSION
from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.architecture.models import SourceRef

__all__ = ["extract_loop_tests"]

#: instruction types a loop body may contain and still be simulated
#: deterministically. IRDisplay is side-effect-free w.r.t. program state
#: and is simply skipped over.
_MUTATING_TYPES = frozenset({"IRMove", "IRAdd", "IRSubtract", "IRMultiply", "IRDivide"})
_WHITELISTED_BODY_TYPES = _MUTATING_TYPES | {"IRIf", "IRElse", "IREndIf", "IRDisplay"}

#: existing_value, amount -> new_value, matching each statement's COBOL
#: semantics ("ADD amount TO existing", "SUBTRACT amount FROM existing",
#: "MULTIPLY existing BY amount", "DIVIDE amount INTO existing") — IR
#: stores ``left`` = amount, ``right`` = the pre-existing target value.
_ARITH: dict[str, Any] = {
    "IRAdd": lambda existing, amount: existing + amount,
    "IRSubtract": lambda existing, amount: existing - amount,
    "IRMultiply": lambda existing, amount: existing * amount,
    "IRDivide": lambda existing, amount: existing // amount if amount else None,
}

_INT_RE = re.compile(r"^-?\d+$")
_MAX_ITERATIONS = 10_000


def _flat_instructions(ir: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for mod in (ir or {}).get("modules", []):
        for fn in mod.get("functions", []):
            for blk in fn.get("blocks", []):
                out.extend(blk.get("instructions", []))
    return out


def _ws_initial_values(ast: dict[str, Any] | None) -> dict[str, int]:
    """``{WORKING-STORAGE item name: its VALUE clause}`` for items whose
    value is a plain (non-decimal) integer literal — the only shape this
    simulator trusts. Group items are walked recursively."""
    out: dict[str, int] = {}

    def walk(items: list[dict[str, Any]] | None) -> None:
        for item in items or []:
            name = item.get("name")
            value = item.get("value")
            if name and isinstance(value, str) and _INT_RE.match(value):
                out[str(name).upper()] = int(value)
            walk(item.get("items"))

    dd = (ast or {}).get("data_division") or {}
    ws = dd.get("working_storage") or {}
    walk(ws.get("items"))
    return out


def _resolve(operand: str | None, state: dict[str, int]) -> int | None:
    if not operand:
        return None
    if _INT_RE.match(operand):
        return int(operand)
    return state.get(operand.upper())


def _cmp(left: int, op: str, right: int) -> bool:
    return {
        ">=": left >= right,
        "<=": left <= right,
        ">": left > right,
        "<": left < right,
        "=": left == right,
        "<>": left != right,
    }[op]


def _match_if_block(
    body: list[dict[str, Any]], i: int
) -> tuple[int | None, int] | None:
    """For an ``IRIf`` at index ``i``, return ``(else_idx_or_None,
    end_if_idx)`` — or ``None`` if the block is malformed or contains a
    nested ``IRIf`` (deliberately unsupported; a single level of
    IF/ELSE is all this simulator trusts itself to interpret)."""
    else_idx: int | None = None
    for j in range(i + 1, len(body)):
        t = body[j].get("type")
        if t == "IRIf":
            return None
        if t == "IRElse":
            if else_idx is not None:
                return None
            else_idx = j
        if t == "IREndIf":
            return else_idx, j
    return None


def _run_body(
    body: list[dict[str, Any]], state: dict[str, int]
) -> dict[str, int] | None:
    """Execute one pass over a (flat, ≤1-level-nested if/else) loop body.
    Returns the updated state, or ``None`` the moment anything can't be
    resolved deterministically — the caller treats that as "not
    derivable", never as "assume zero"."""
    state = dict(state)
    i = 0
    n = len(body)
    while i < n:
        instr = body[i]
        t = instr.get("type")
        if t == "IRMove":
            val = _resolve(instr.get("source"), state)
            result = instr.get("result")
            if val is None or not result:
                return None
            state[str(result).upper()] = val
            i += 1
        elif t in _ARITH:
            existing = _resolve(instr.get("right"), state)
            amount = _resolve(instr.get("left"), state)
            result = instr.get("result")
            if existing is None or amount is None or not result:
                return None
            new_value = _ARITH[t](existing, amount)
            if new_value is None:
                return None
            state[str(result).upper()] = new_value
            i += 1
        elif t == "IRDisplay":
            i += 1
        elif t == "IRIf":
            if instr.get("extra_terms"):
                # A compound IF (AND/OR terms) is not interpreted by this
                # simulator; evaluating only its first term would be wrong,
                # so the body is "not derivable" -- never guessed.
                return None
            left = _resolve(instr.get("left"), state)
            right = _resolve(instr.get("right"), state)
            if left is None or right is None:
                return None
            match = _match_if_block(body, i)
            if match is None:
                return None
            else_idx, end_idx = match
            taken = _cmp(left, str(instr.get("operator", "")), right)
            if taken:
                branch = body[i + 1 : else_idx if else_idx is not None else end_idx]
            else:
                branch = body[else_idx + 1 : end_idx] if else_idx is not None else []
            sub_state = _run_body(branch, state) if branch else state
            if sub_state is None:
                return None
            state = sub_state
            i = end_idx + 1
        else:
            return None
    return state


def _simulate(
    body: list[dict[str, Any]],
    initial_values: dict[str, int],
    cond_var: str,
    override: int,
    cond_op: str,
    cond_literal: int,
) -> tuple[dict[str, int], int] | None:
    """Run the loop from ``initial_values`` with ``cond_var`` overridden
    to ``override`` until the ``PERFORM UNTIL`` exit condition holds, or
    the iteration cap is hit (-> not derivable)."""
    state = dict(initial_values)
    state[cond_var] = override
    iterations = 0
    while not _cmp(state[cond_var], cond_op, cond_literal):
        if iterations >= _MAX_ITERATIONS:
            return None
        new_state = _run_body(body, state)
        if new_state is None:
            return None
        state = new_state
        iterations += 1
    return state, iterations


def _find_top_level_loops(
    instructions: list[dict[str, Any]],
) -> tuple[list[tuple[int, int]], list[LoopSkipRecord]]:
    """``(loops, skips)`` — ``loops`` are ``(perform_until_idx,
    end_perform_idx)`` pairs for loops with no nested ``PERFORM UNTIL``;
    a nested loop is recorded as skipped rather than guessed at."""
    loops: list[tuple[int, int]] = []
    skips: list[LoopSkipRecord] = []
    i = 0
    n = len(instructions)
    while i < n:
        if instructions[i].get("type") != "IRPerformUntil":
            i += 1
            continue
        start = i
        paragraph = str(instructions[start].get("paragraph", "") or "")
        depth = 0
        end = None
        j = i + 1
        while j < n:
            t = instructions[j].get("type")
            if t == "IRPerformUntil":
                depth += 1
            elif t == "IREndPerform":
                if depth == 0:
                    end = j
                    break
                depth -= 1
            j += 1
        if end is None:
            skips.append(
                LoopSkipRecord(paragraph=paragraph, reason="unterminated_perform_until")
            )
            i = j + 1
            continue
        if depth != 0:
            skips.append(
                LoopSkipRecord(paragraph=paragraph, reason="nested_loop_not_supported")
            )
            i = end + 1
            continue
        loops.append((start, end))
        i = end + 1
    return loops, skips


def _test_id(source_id: str, paragraph: str, variable: str, tag: str) -> str:
    h = hashlib.sha256(
        f"{source_id}\x1floop\x1f{paragraph}\x1f{variable}\x1f{tag}".encode("utf-8")
    ).hexdigest()
    return f"BT-{h[:8]}"


def extract_loop_tests(
    bundle: AnalysisBundle,
) -> tuple[list[BehavioralTestCase], list[LoopSkipRecord]]:
    """Deterministically derive behavioral tests for simple ``PERFORM
    UNTIL`` accumulator/loop patterns. Returns ``(tests, skips)`` — every
    loop this function finds ends up in exactly one of the two lists."""
    sid = bundle.source_id
    path = f"{sid}.cbl"
    instructions = _flat_instructions(bundle.ir)
    initial_values = _ws_initial_values(bundle.ast)
    loop_ranges, skips = _find_top_level_loops(instructions)

    tests: list[BehavioralTestCase] = []

    for start, end in loop_ranges:
        header = instructions[start]
        paragraph = str(header.get("paragraph", "") or sid)
        cond_var = str(header.get("left", "")).upper()
        cond_op = str(header.get("operator", ""))
        cond_rhs = str(header.get("right", ""))
        body = instructions[start + 1 : end]

        if not _INT_RE.match(cond_rhs):
            skips.append(
                LoopSkipRecord(
                    paragraph=paragraph,
                    reason=(
                        f"loop exit boundary '{cond_rhs}' is not a static integer "
                        "literal (variable-driven or decimal loop bounds are not "
                        "yet supported)"
                    ),
                )
            )
            continue
        if cond_var not in initial_values:
            skips.append(
                LoopSkipRecord(
                    paragraph=paragraph,
                    reason=(
                        f"loop variable {cond_var} has no statically known "
                        "integer WORKING-STORAGE initial value"
                    ),
                )
            )
            continue

        unsupported = next(
            (i for i in body if i.get("type") not in _WHITELISTED_BODY_TYPES), None
        )
        if unsupported is not None:
            skips.append(
                LoopSkipRecord(
                    paragraph=paragraph,
                    reason=(
                        f"loop body contains unsupported instruction "
                        f"'{unsupported.get('type')}' for deterministic simulation"
                    ),
                )
            )
            continue

        referenced: set[str] = set()
        for instr in body:
            for key in ("left", "right", "source"):
                v = instr.get(key)
                if v and not _INT_RE.match(str(v)):
                    referenced.add(str(v).upper())
        unresolved = sorted(v for v in referenced if v not in initial_values)
        if unresolved:
            skips.append(
                LoopSkipRecord(
                    paragraph=paragraph,
                    reason=(
                        "loop body references variable(s) with no statically "
                        f"known initial value: {', '.join(unresolved)}"
                    ),
                )
            )
            continue

        cmp = Comparison(
            variable=cond_var,
            operator=cond_op,
            literal=cond_rhs,
            is_numeric=True,
            negated=False,
            raw=f"{cond_var} {cond_op} {cond_rhs}",
        )
        accumulators = sorted(
            {
                str(instr["result"]).upper()
                for instr in body
                if instr.get("type") in (_MUTATING_TYPES) and instr.get("result")
            }
        )

        loop_tests: list[BehavioralTestCase] = []
        not_derivable_reason: str | None = None
        for value_str, _holds in generate_boundary_values(cmp):
            override = int(value_str)
            sim = _simulate(
                body, initial_values, cond_var, override, cond_op, int(cond_rhs)
            )
            if sim is None:
                not_derivable_reason = (
                    f"simulation from {cond_var}={override} did not reach the exit "
                    f"condition within {_MAX_ITERATIONS} iterations"
                )
                break
            terminal_state, iterations = sim
            state_changes = tuple(
                ExpectedStateChange(
                    field=acc,
                    from_value=(
                        str(override) if acc == cond_var else str(initial_values[acc])
                    ),
                    to_value=str(terminal_state[acc]),
                )
                for acc in accumulators
            )
            outputs = tuple(
                ExpectedOutput(
                    name=acc, kind="field", expected_value=str(terminal_state[acc])
                )
                for acc in accumulators
            )
            src_pos = header.get("source_position") or {}
            end_pos = instructions[end].get("source_position") or {}
            source_refs = (
                (
                    SourceRef(
                        source_id=sid,
                        source_path=path,
                        line_start=src_pos.get("line"),
                        line_end=end_pos.get("line") or src_pos.get("line"),
                        paragraph=paragraph,
                    ),
                )
                if src_pos.get("line")
                else ()
            )
            loop_tests.append(
                BehavioralTestCase(
                    test_id=_test_id(sid, paragraph, cond_var, f"loop={override}"),
                    name=f"{sid}:{paragraph}:LOOP:{cond_var}={override}",
                    description=(
                        f"PERFORM UNTIL {cmp.raw} in paragraph {paragraph}, starting "
                        f"{cond_var}={override} ({iterations} iteration"
                        f"{'s' if iterations != 1 else ''})"
                    ),
                    inputs=(
                        InputValue(
                            name=cond_var,
                            value=str(override),
                            source=InputSource.BOUNDARY_GENERATED,
                            partition_of=cmp.raw,
                        ),
                    ),
                    expected_state_changes=state_changes,
                    expected_outputs=outputs,
                    source_refs=source_refs,
                    confidence="high",
                    executable=True,
                    inconclusive_reason=None,
                    test_type="loop_accumulator",
                    iteration_count=iterations,
                    extraction_version=EXTRACTION_VERSION,
                    source_id=sid,
                )
            )

        if not_derivable_reason is not None:
            skips.append(
                LoopSkipRecord(paragraph=paragraph, reason=not_derivable_reason)
            )
            continue
        tests.extend(loop_tests)

    return tests, skips
