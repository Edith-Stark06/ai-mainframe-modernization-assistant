# MMIM — unsupported-statement recovery in `PERFORM UNTIL` bodies (Stage 28, no version bump)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v24` (unchanged — see §4)

`docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §8 named this exactly, and explicitly left it unfixed: "The
identical `COMPUTE`/`EVALUATE`-unsupported-statement-loop defect in `PERFORM UNTIL` bodies... the fix
would be structurally identical (one `elif` branch) if a future task requests it." This document is that
task.

## 1. Scope, established from the docs

`docs/MMIM_PARSER_VALIDATION_FIX.md` §7 first fixed this defect class for the paragraph-level statement
loop. `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` then fixed the identical defect for `IF`/`ELSE` then/else
blocks — and, in its own §8, found and precisely named a *third* occurrence in `PERFORM UNTIL` bodies,
deliberately out of that task's scope. No stage since (25, 26, 27) touched it; it remained on the audit
doc's `NEXT STEP` line throughout. Nothing else in the `NEXT STEP` list had both a proven, ready-to-copy
fix pattern and a concretely named, already-reproduced defect — every other candidate (`PERFORM VARYING`,
`OCCURS`/array modelling, `COMPUTE` semantics, the behavioral compound parser) is a genuinely new feature,
not a recovery-path extension of an already-shipped fix.

## 2. Reproduction and root cause (measured before editing)

`ProcedureDivisionParser._parse_perform_statement`'s `PERFORM UNTIL`/`END-PERFORM` body loop checked only
`tok.lexeme.upper() in _STATEMENT_LEXEMES` — unlike the paragraph-level loop and the `IF`/`ELSE` then/else
loops, it never checked `_UNSUPPORTED_STATEMENT_LEXEMES` (the set that gives `READ`/`COMPUTE`/`EVALUATE`/
etc. their clean `SYN100` "unsupported statement" diagnostic and graceful skip everywhere else). An
unsupported verb used inside a `PERFORM UNTIL` body raised a hard `ParserError` instead:

```
PERFORM UNTIL WS-A >= 3
    COMPUTE WS-B = WS-B + 1
    ADD 1 TO WS-A
END-PERFORM
DISPLAY WS-B.
```

produced `SYN005 "expected statement in PERFORM block"`, and the caller's statement-level recovery
resolves that by synchronising to the next `PERIOD` — a structured `PERFORM UNTIL`/`END-PERFORM` has no
interior periods of its own guaranteed, so recovery ran straight through to the paragraph's own closing
period, silently discarding everything in between. Confirmed directly on the isolated pre-fix tree: the
minimal example above produced **zero** paragraph statements — not just the loop, the entire paragraph
including `DISPLAY WS-B` after it.

## 3. The fix (`app/parser/syntax/procedure_parser.py` only, one `elif` branch)

Exactly as `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §8 predicted: one `elif tok.lexeme.upper() in
_UNSUPPORTED_STATEMENT_LEXEMES: self._skip_unsupported_statement(state)` branch added to the `PERFORM
UNTIL` body loop, mirroring the `IF`/`ELSE` then/else loops' own shape exactly — no new recovery behavior
invented. `_skip_unsupported_statement` already:

* dispatches `READ` to the dedicated `_skip_read_statement` (established since
  `docs/MMIM_READ_AT_END_PARSING_FIX.md`), which correctly consumes an entire `READ ... AT END ... NOT AT
  END ... END-READ` block, nested `IF`s and all, as one unit;
* matches a scope-opening verb's own closing word (`EVALUATE` → `END-EVALUATE`) rather than scanning for
  an unrelated period, so an `EVALUATE` written as the *last* statement in the loop body (idiomatic COBOL,
  no period of its own) does not run past `END-PERFORM` into whatever follows;
* already treats `END-PERFORM` as a statement-boundary word (`_at_operand_boundary`, confirmed directly —
  it was already in the boundary set for other reasons), so the skip correctly stops there regardless.

No other file needed a change: the fix is purely in the parser's own recovery path, before any AST/IR/
symbol/backend consumer ever sees the result.

## 4. Corpus exposure (measured before editing) — zero, no dataset regeneration

Searched every source in the 45-source training corpus (regex over every `PERFORM UNTIL ... END-PERFORM`
span, every verb in `_UNSUPPORTED_STATEMENT_LEXEMES`): **zero occurrences**. The only real occurrence found
anywhere in the repository is in the shared, non-corpus
`workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl` fixture — 3 `PERFORM UNTIL` loops
(lines 190, 228, 255), each containing a `READ`. Directly confirmed: full 45-source fingerprint (AST/IR
hash, CFG summary, dependencies, business-rule count, risk count/categories, strategy hash,
syntax-diagnostic codes, Java hash, `javac`; isolated pre-fix baseline vs current tree, via
`build_analysis_bundle`) — **0 of 45 sources differ on any dimension**. Because no corpus source is
observably affected, `MMIM_GENERATOR_VERSION` is **not bumped** and `data/dataset/mmim-v2` is **not
regenerated** — the same outcome, for the same reason, as task #stage22 and task #stage26.

On the shared fixture: each of the 3 `SYN005 "expected statement in PERFORM block"` diagnostics (lines
191, 229, 256) is replaced 1-for-1 by `SYN100 "unsupported statement 'READ'"` at the same line — the same
vague-to-precise upgrade every other unsupported-statement location already has. Total diagnostic count is
unchanged at 49 (a coincidence: -3 `SYN005` + 3 `SYN100` nets zero). `statements_parsed` rises 60 → 63 (one
newly-real `PerformUntilStatementNode` per fixed loop); `2000-LOAD-CUSTOMERS`, `3000-LOAD-ACCOUNTS`, and
`4000-PROCESS-TRANSACTIONS` each gain exactly one statement (the loop itself — its own body is empty,
since the `READ` occupies the loop's entire body and is skipped whole, exactly matching how `READ` is
already skipped everywhere else in this codebase). `4000-PROCESS-TRANSACTIONS`'s `IF WS-CURRENT-ACCOUNT
NOT = SPACES` (line 263, inside the `READ`'s own `NOT AT END` clause) remains unreached — it is consumed
as part of the skipped `READ` block, not a new gap this fix leaves open.

## 5. Verification

**Isolated pre-fix proof.** A fresh byte-copy of the post-Stage-27 tree was made *before any edit*
(`.venv`/caches excluded; `app.__file__` confirmed to resolve inside the copy). All **10** new tests
(`tests/parser/test_perform_until_unsupported_statement_fix.py`) were then copied onto that tree: **9 of
10 fail** (the 10th, a pure corpus-survey test, correctly passes on both trees — it proves a fact about the
corpus, not about the fix). All 10 pass on the fixed tree.

**Test suites**, compared against the documented baseline (4730 passed / 12 pre-existing failures at the
start of this cycle):

* `tests/parser` — 9 failed (exactly the 9 documented pre-existing parser-area baseline failures) once
  `tests/parser/test_figurative_constant_operands.py
  ::test_fixture_diagnostic_total_is_unchanged_by_this_fix` (Stage 26's own test) was updated: its pinned
  code at line 256 moved `SYN005` → `SYN100` for this stage's own, unrelated reason; the total (49) and the
  "nothing at 263" claim it exists to prove are both still true and re-verified directly.
* `tests/backend`, `tests/ir`, `tests/dataset`, `tests/modernization`, `tests/analysis`,
  `tests/java_modernization`, `tests/behavioral`, `tests/api`, `tests/integration` — see the final report
  for the exact combined totals; zero corpus impact (§4) means no cascading dataset-content test updates
  were expected or needed.
* Full suite — see the final report.

`black`, `ruff check`, and `mypy` are clean on both changed files. No conflict markers anywhere in the
repo.

## 6. Remaining gaps (reproduced or previously documented, NOT fixed)

1. `SEARCH` (the other scope-opening verb besides `EVALUATE`) keeps its original, unbounded
   scan-to-next-period behavior inside a `PERFORM UNTIL` body, same as everywhere else — no corpus source
   or fixture exercises it there.
2. `PERFORM`/`PERFORM THRU` still lower to an empty stub call with the paragraph body inlined — a
   behaviorally-correct Java translation remains its own, larger cycle (`docs/MMIM_PERFORM_THRU_FIX.md`
   §7).
3. `PERFORM VARYING` entirely unsupported (`docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md` §8) — unrelated
   to this stage's fix.
4. The Java figurative-constant-value-translation gap
   (`docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md` §6) — unrelated, still unfixed.
5. Leading `NOT` before an entire condition, subscripted comparison operands
   (`docs/MMIM_NEGATED_COMPARISON_FIX.md` §8 items 1-2) — unchanged.
6. `MOVE 09`, `DataModelElement.initial_value`, `GO TO … DEPENDING ON`, `COMPUTE` (semantics — this stage
   only fixed *recovery* around an unimplemented `COMPUTE`, not `COMPUTE` itself), `COMP`/`COMP-3` — as
   recorded before.

## 7. Files

`app/parser/syntax/procedure_parser.py`, `tests/parser/test_perform_until_unsupported_statement_fix.py`
(new, 10 tests), `tests/parser/test_figurative_constant_operands.py`,
`docs/MMIM_PERFORM_UNTIL_UNSUPPORTED_STATEMENT_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`. No
dataset file and no other existing test changed (§4).
