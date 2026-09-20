# COMPUTE/EVALUATE-Inside-IF-Block Parser Recovery Fix

Fixes the parser-recovery defect identified in `docs/MMIM_PARSER_VALIDATION_FIX.md` §7 —
an unsupported statement (`COMPUTE`, `EVALUATE`, …) used *inside* an `IF`/`ELSE` block
raised a hard `ParserError` and lost every statement after it in the paragraph, instead
of the graceful per-statement recovery unsupported statements already get at the
paragraph top level.

**Scope discipline**: only `app/parser/syntax/procedure_parser.py` was touched. No change
to behavioral extraction, dataset generation logic, the instruction adapter, benchmark-v1,
Java modernization, frontend, RAG, or the quality loop.

---

## 1. Read before editing

Reviewed, per the task instruction, before writing any code:

- `docs/MMIM_PARSER_VALIDATION_FIX.md` §7 (the defect's original identification).
- `docs/MMIM_V2_DATASET_AUDIT.md` (current dataset state, `mmim-gen-v4`).
- `app/parser/syntax/procedure_parser.py` — `_parse_if_statement`'s then/else statement
  loops, `_skip_unsupported_statement`, `_parse_statements` (paragraph-level statement
  loop, for comparison), `_SCOPE_OPENING_LEXEMES`, `_SCOPE_TERMINATOR_LEXEMES`,
  `_UNSUPPORTED_STATEMENT_LEXEMES`.
- `app/parser/diagnostics/recovery.py` — `RecoveryManager.record_and_synchronise`'s
  scan-to-next-`PERIOD` behavior (the mechanism that turns a `ParserError` into
  paragraph loss).
- `tests/parser/test_statement_boundaries.py::test_scope_delimited_construct_still_skipped_whole`
  — the one existing test that exercises `EVALUATE` skip-to-period behavior (at
  paragraph level, with `EVALUATE` carrying its own trailing period).

## 2. Reproduction — before this fix

Minimal, isolated (via `AnalysisService().analyze_file()`):

```
IF WS-A > 0
    COMPUTE WS-B = WS-A + 1
END-IF
DISPLAY WS-B
DISPLAY WS-A.
```

Before: `MAIN-PARA` → **0 statements**, one diagnostic:
`SYN005 "expected statement in IF block"` — which does not even name `COMPUTE` as the
cause. The `IF`, both `DISPLAY`s, everything, is gone.

```
IF WS-A > 0
    EVALUATE WS-A
        WHEN 1
            DISPLAY 1
    END-EVALUATE
END-IF
DISPLAY WS-A.
```

Before: identical failure — `MAIN-PARA` → **0 statements**, same
`SYN005 "expected statement in IF block"`.

## 3. Root cause — precisely identified, not assumed

The task asked to determine whether the defect was tokenization, statement-boundary
detection, `IF`-block termination, `EVALUATE` scope/recovery, `COMPUTE` operand parsing,
or an interaction. Traced directly against the code (not inferred):

**Primary cause — `IF`-block statement-dispatch, not tokenization or operand parsing.**
`_parse_if_statement`'s then/else loops contain:

```python
if tok.lexeme.upper() in _STATEMENT_LEXEMES:
    then_statements.append(self._parse_statement(state))
else:
    raise ParserError("expected statement in IF block", ...)
```

Unlike the paragraph-level statement loop (`_parse_statements`), this never checked
`_UNSUPPORTED_STATEMENT_LEXEMES` — the set that gives `COMPUTE`/`EVALUATE`/`OPEN`/etc.
their clean `SYN100` diagnostic and graceful skip everywhere else. Any unsupported verb
inside an `IF`/`ELSE` block fell straight to the `raise`.

That `ParserError` propagates to the paragraph-level statement loop's own recovery
(`state.record_and_synchronise`, per `recovery.py`), which scans forward and **stops at
the next `PERIOD`, consuming it**. A structured `IF`/`END-IF` has no interior periods —
only the paragraph's own closing statement carries one — so recovery ran straight through
`END-IF` and every statement after it, all the way to the paragraph's final period.
Tokenization, `COMPUTE`'s (non-existent) operand grammar, and `IF`-condition parsing were
all already correct and uninvolved; the defect was purely in what the `IF`-block's own
statement loop was willing to dispatch.

**Secondary cause, found while fixing the first — a sharper `EVALUATE` scope/recovery
defect.** The natural fix is to route unsupported verbs inside the `IF`-block loops
through the existing `_skip_unsupported_statement` (exactly as the paragraph-level loop
already does). Doing so naively exposed a second bug: `_skip_unsupported_statement`
skips a scope-opening verb (`EVALUATE`, `SEARCH`) by scanning for *the next period* —
correct when `EVALUATE` carries its own trailing period (the one existing test's shape),
**wrong** when `EVALUATE` is the *last* statement inside an `IF` block, which is idiomatic
COBOL: no period until the enclosing `END-IF` supplies it. The naive skip ran straight
past `END-IF` and consumed the real statement after it — reproduced directly:

```
IF WS-A > 0
    EVALUATE WS-A
        WHEN 1
            DISPLAY 1
    END-EVALUATE
END-IF
DISPLAY WS-A.
```

Naive fix (route to `_skip_unsupported_statement` unchanged): `MAIN-PARA` → **0
statements**, `SYN005 "missing END-IF"` — a *different*, equally wrong failure. This is
not a new-to-this-fix defect — it already existed at plain paragraph level for a
period-less `EVALUATE`, confirmed independently of any `IF`:

```
EVALUATE WS-A
    WHEN 1
        DISPLAY 1
END-EVALUATE
STOP RUN.
```

Before any change this session: `MAIN-PARA` → **0 statements** (`STOP RUN` lost too) —
this reproduces on the `mmim-gen-v4` code, before today's edit. The `IF`-block fix simply
makes this pre-existing gap far more visible, since `EVALUATE` nested in an `IF` almost
never carries its own period.

## 4. The fix — narrowest additive change

### A. Route unsupported verbs inside `IF`/`ELSE` blocks through the existing skip mechanism

`_parse_if_statement`'s then and else loops each gained one `elif` branch:

```python
if tok.lexeme.upper() in _STATEMENT_LEXEMES:
    then_statements.append(self._parse_statement(state))
elif tok.lexeme.upper() in _UNSUPPORTED_STATEMENT_LEXEMES:
    self._skip_unsupported_statement(state)
else:
    raise ParserError("expected statement in IF block", ...)
```

No new recovery behavior invented — this reuses the exact mechanism the paragraph-level
loop already uses and that is already tested
(`test_scope_delimited_construct_still_skipped_whole`).

### B. Precisely bound scope-opening verbs by their closing word, not by scanning for an unrelated period

`_skip_unsupported_statement` gained a `_SCOPE_CLOSE_WORDS` lookup (`{"EVALUATE":
"END-EVALUATE"}`). When the verb being skipped has a known closing word, a new
`_skip_to_matching_close_word` static method consumes tokens up to and including that
closing word — **honoring same-verb nesting** (an `EVALUATE` seen again before the
matching `END-EVALUATE` increments a depth counter) — then consumes one
immediately-following period if present, and stops there unconditionally. It never
continues hunting for a later, unrelated period.

`SEARCH` (the other scope-opening verb) has no entry in `_SCOPE_CLOSE_WORDS` and keeps
its original, unbounded scan-to-next-period behavior completely unchanged — no test in
this corpus or task exercises `SEARCH` inside an `IF`/`ELSE` block, and adding
`END-SEARCH` matching without a concrete case to verify against would be exactly the kind
of opportunistic, unrequested fix this task's stop conditions ask to avoid.

### What was preserved, verified explicitly

- **Existing `COMPUTE`/`EVALUATE` behavior**: both remain entirely unimplemented verbs;
  only *recovery around* them changed. A paragraph consisting solely of one `COMPUTE`
  (no enclosing `IF`) still produces 0 modeled statements for that paragraph — correct,
  unchanged, not a defect (confirmed directly against `t_billing_engine`'s
  `3000-COMPUTE-INVOICE-PAYABLE`, §6).
- **Existing `IF`/`ELSE`/`END-IF` behavior**: the condition-parsing, `ELSE`, and
  `END-IF` handling added by the previous parser task are completely untouched; only the
  then/else statement-dispatch loops gained the one new branch each.
- **Paragraph boundaries and period handling**: `_consume_optional_period`, the
  paragraph-label detection, and the division-boundary checks are untouched.
- **Diagnostics are not weakened**: every case that previously raised now still records a
  diagnostic (`SYN100`, naming the actual unsupported verb) — strictly more precise than
  the previous `SYN005 "expected statement in IF block"`, never fewer or vaguer (§6).
- **No heuristic statement swallowing introduced**: the fix reuses an existing, audited
  mechanism (`_skip_unsupported_statement`) rather than inventing new pattern-matching or
  lookahead heuristics.
- **Source locations preserved**: `_skip_unsupported_statement` already records the verb
  token's position on the diagnostic; unaffected by this change.
- **Backward-compatible with existing AST consumers**: no AST node shapes changed in this
  fix (only §"B" above changes control flow inside the existing parser, not any node's
  fields).
- **Malformed syntax still diagnosed, never silently parsed**: verified directly (§5,
  `test_malformed_if_condition_still_diagnosed_not_silently_parsed`) — an actually
  malformed `IF` condition (unrelated to `COMPUTE`/`EVALUATE`) still raises `SYN005`,
  exactly as before.

## 5. Tests added

`tests/parser/test_compute_evaluate_in_if_block_fix.py` — 14 new tests, all passing:

1. `test_if_compute_end_if_then_another_statement`,
   `test_if_compute_else_compute_end_if_then_another_statement` (then **and** else loops)
2. `test_compute_at_paragraph_level_unchanged` (pre-existing top-level behavior regression
   guard)
3. `test_if_evaluate_end_if_then_another_statement`,
   `test_paragraph_level_evaluate_with_own_period_unchanged` (existing tested shape,
   byte-for-byte unchanged), `test_paragraph_level_evaluate_without_own_period_recovers_next_statement`
   (the pre-existing, independent paragraph-level bug, now also fixed as a direct
   consequence of §4B)
4. `test_if_compute_integer_operands_then_statement`
5. `test_if_compute_decimal_literal_operands_then_statement` (combines both parser fixes)
6. `test_nested_if_with_compute_in_inner_branch`,
   `test_nested_evaluate_inside_evaluate_inside_if` (same-verb nesting depth tracking)
7. `test_paragraph_boundary_after_if_compute_is_intact` (the *next paragraph*, not just
   the next statement, is unaffected)
8. `test_evaluate_missing_end_evaluate_stops_safely_not_silently` (malformed/unterminated
   `EVALUATE` — no crash, no silent swallow of anything beyond EOF),
   `test_malformed_if_condition_still_diagnosed_not_silently_parsed` (a genuinely
   malformed condition, unrelated to this fix, still diagnosed)

**Critical regression**: `test_critical_regression_statement_after_if_compute_survives` —
a paragraph combining a decimal-literal `IF` condition, `COMPUTE` in the then-branch, a
`MOVE` in the else-branch, and two further statements after `END-IF`. Before this fix:
zero statements, one vague diagnostic. Asserts all 4 real statements survive and the one
`SYN100` diagnostic correctly names `COMPUTE`.

## 6. Real-corpus validation — before/after, measured correctly

**Methodology**: the previous parser task's real-corpus comparison was corrupted by a
`sys.path` resolution bug (running the measurement script by absolute path put the
scratchpad directory, not the working tree, at `sys.path[0]`). This task used a different,
verified-safe method: the specific hunks this session added to
`app/parser/syntax/procedure_parser.py` were reverted **in place** (confirmed by
re-checking `complex_acctbatch.cbl`'s diagnostic count returned to exactly 44, the known
`mmim-gen-v4` value), the "before" measurement was taken, the fix was restored (confirmed
diagnostic count returned to exactly 45), and the "after" measurement was taken — both
runs executed from the actual working tree, eliminating the path-resolution class of bug
entirely. Measured with `build_analysis_bundle` + `extract_behavioral_tests` directly on
the raw `.cbl` files, across the full 45-source training corpus.

### Corpus-wide totals

| Metric | Before (mmim-gen-v4) | After (this fix) | Change |
|---|---:|---:|---:|
| Sources with any change | — | 14 / 45 | — |
| Total zero-statement paragraphs (sum) | 32 | **17** | **-15** |
| Total statements parsed (sum) | 313 | **339** | **+26** |
| Total IR instructions (sum) | 642 | **768** | **+126 (+20%)** |
| Total business rules (sum) | 123 | **149** | **+26 (+21%)** |
| Total syntax diagnostics (sum) | 131 | 156 | +25 (see below — a strengthening) |
| Sources with ≥1 derivable behavioral test | 29 / 45 | **30 / 45** | **+1** |

**The diagnostic count increased, and that is not a regression.** Per the task's own
instruction not to claim improvement merely from diagnostics disappearing, and
symmetrically not to be alarmed when they *appear* without checking why: every one of the
25 new diagnostics corresponds to a construct that was previously invisible (zero
statements, zero diagnostics — a silent loss) and is now correctly recognized and
reported. Spot-verified on `complex_acctbatch.cbl` (§7): a vague `SYN005 "expected
statement in IF block"` was replaced by the precise `SYN100 "unsupported statement
'COMPUTE'"` at the same line, and a `COMPUTE` at a different line that previously
produced **zero diagnostics at all** (its entire containing content was silently
discarded) is now correctly surfaced. `statements_parsed` for that same fixture rose from
46 to 52 in the identical change — strictly more of the source is represented, not less.

### The two named sources, in detail

| Source | Diagnostics | Zero-stmt paragraphs | Statements | IR instrs | Business rules | Validation tests | Validated? |
|---|---|---|---|---|---|---:|---|
| `t_shared_state_hazard` | 4 → 4 (composition changed, not just count) | `['2000-SIDE-EFFECT-STEP-TWO', '3000-SIDE-EFFECT-STEP-THREE']` → `[]` | 7 → 9 | 7 → 16 | 0 → 3 | 0 → **4** | **YES — fully validated** |
| `t_billing_engine` | 4 → 4 | `['3000-COMPUTE-INVOICE-PAYABLE']` → **unchanged** (see below) | 10 → 14 | 10 → 17 | 0 → 1 | 0 → 0 | Partially — see §7 |

`t_shared_state_hazard` is fully validated: both previously-zero-statement paragraphs now
parse completely, with real business rules and — for the first time — a derivable
behavioral-test suite.

## 7. `t_billing_engine` — why it stayed at 0 validation tests (investigated, not assumed)

`3000-COMPUTE-INVOICE-PAYABLE` remained zero-statement. Directly inspected — it is a
single bare `COMPUTE` statement with **no enclosing `IF`**:

```
3000-COMPUTE-INVOICE-PAYABLE.
    COMPUTE INVOICE-TOTAL-DUE = BASE-ITEMS-TOTAL - NET-DISCOUNT-GIVEN + NET-TAX-ASSESSED.
```

This is expected, unchanged `COMPUTE` behavior (§4, "what was preserved") — a paragraph
whose only content is an unimplemented verb legitimately has 0 AST-represented
statements; this was never the defect this task fixes.

The file's other two paragraphs (`1000-INVOKE-TAX-ENGINE`, `2000-INVOKE-DISCOUNT-ENGINE`)
each contain exactly the fixed shape — `IF ... = 0.00 { MOVE/COMPUTE } END-IF` followed by
a `MOVE` — and both recovered correctly (`total_statements_parsed` 10 → 14, matching two
`IfStatementNode`s plus two trailing `MOVE`s recovered across the two paragraphs).
`business_rule_count` went 0 → 1: one new rule (`TAX-OUT-TAX-RATE = 0.00`) was extracted.

**Why `validation_test_count` stayed at 0, and why this is a separate, unfixed gap**:
directly checked — `app.behavioral.extraction.conditions.parse_condition("TAX-OUT-TAX-RATE
= 0.00")` returns `None`. That module's condition regex
(`_NUMERIC = re.compile(r"^-?\d+$")`) only recognizes plain integer literals; a
decimal-literal comparison (`= 0.00`) is neither integer nor a quoted string, so no
boundary-testable comparison is derived, and the deterministic behavioral extractor
correctly (honestly) derives no test for it rather than fabricating one. This is a
pre-existing, **independent** limitation of `app/behavioral/extraction/conditions.py` —
a different module entirely from the `app/parser/syntax/procedure_parser.py` recovery
mechanism this task fixes — reported per the stop conditions, not fixed here.

`t_credit_approval` (§6 of `docs/MMIM_PARSER_VALIDATION_FIX.md`, further improved this
session from 4 to 11 business rules) shows the same pattern directly: its
integer-literal-condition rules (`CREDIT-SCORE >= 740`, `CREDIT-SCORE >= 660`) do produce
tests; its decimal-literal-condition rules (`MONTHLY-INCOME > 0.00`,
`ASSIGNED-CREDIT-LMT > 25000.00`) do not — consistent, well-understood, and out of this
task's scope.

## 8. New independent gaps found (reported, not fixed, per the stop conditions)

1. **`app/behavioral/extraction/conditions.py`'s decimal-literal gap** (§7 above) — the
   behavioral-test condition parser only recognizes integer-literal comparisons; a
   decimal-literal condition (now often reachable, thanks to this task's and the previous
   task's parser fixes) silently yields no test rather than an incorrect one — honest, but
   a real coverage ceiling. Affects `t_billing_engine` directly; likely others with
   decimal-literal-only conditions.
2. **The identical `COMPUTE`/`EVALUATE`-unsupported-statement-loop defect in `PERFORM
   UNTIL` bodies** — `_parse_perform_statement`'s body loop has the exact same shape
   (`if ... in _STATEMENT_LEXEMES: ... else: raise ParserError(...)`) with no
   `_UNSUPPORTED_STATEMENT_LEXEMES` branch, confirmed by direct reproduction:

   ```
   PERFORM UNTIL WS-A >= 3
       COMPUTE WS-B = WS-B + 1
       ADD 1 TO WS-A
   END-PERFORM
   DISPLAY WS-B.
   ```

   produces 0 statements, `SYN005 "expected statement in PERFORM block"`. This is the
   same defect class as the one this task fixed, in a third location the task's own
   description scoped to "`IF` blocks" specifically and which the required test list did
   not ask for. Not fixed here, per the explicit scope; the fix would be structurally
   identical (one `elif` branch) if a future task requests it.

Neither of these is fixed in this change. No other independent parser, lexer, CFG/IR, or
determinism defect was found during this task; no fabricated or non-executable validation
evidence was introduced; no benchmark leakage occurred.

## 9. MMIM dataset regeneration & versioning

`dataset_version` **stays `"mmim-v2"`** — same 45-source corpus, same 8-task contract.
The deterministic pipeline changed again (any AST/business-rule-derived task can differ,
same profile as the previous parser fix), so `generator_version` bumps a fourth time:
`mmim-gen-v4` → **`mmim-gen-v5`** (`MMIM_GENERATOR_VERSION_V5`, `app/dataset/version.py`).
`mmim-gen-v4`'s build is superseded in place, not kept as a separate snapshot; this
document and the updated `docs/MMIM_V2_DATASET_AUDIT.md` are that supersession's record.
`mmim-v1` (`mmim-gen-v1`) is untouched.

Regenerated via `build_mmim_dataset(..., strict_eligibility=True,
generator_version=MMIM_GENERATOR_VERSION_V5)` over the unchanged 45-source corpus, seed 42:

| | mmim-gen-v4 (before) | mmim-gen-v5 (after) |
|---|---:|---:|
| Total examples | 344 | **345** |
| `VALIDATION_REASONING` examples (sources) | 29 | **30** |
| Skipped tasks | 16 | **15** |
| Split counts (train/val/test) | 222 / 69 / 53 | **222 / 69 / 54** |

No source was artificially forced to coverage: **15 skips remain**, every one recorded in
`manifest.json["skipped"]` with `reason: "no_derivable_behavioral_tests"` and a
`parser_status` block.

**Split preservation verified directly**: `t_shared_state_hazard` was assigned to `test`
in the prior `mmim-gen-v4` `split_manifest.json` and remains assigned to `test` — the
`test +1` delta is exactly and only its new `VALIDATION_REASONING` example landing in the
split it already belonged to. No source moved.

**Re-verified after regeneration**: benchmark leakage (0 overlap on source ID / SHA-256 /
normalized source — PASS), split leakage (`detect_leakage`: 0 errors, 5 warnings, same
benign trivial-target convergences as before — PASS), duplicate source checks (0 exact,
0 normalized — PASS, corpus unchanged), deterministic regeneration
(`test_deterministic_regeneration`, byte-identical across two runs — PASS),
instruction-adapter regeneration (345 examples, `dataset_version: "mmim-v2"` correctly
reflected in its manifest — PASS).

## 10. Tests run (quality gates)

```
python -m pytest tests/parser/test_compute_evaluate_in_if_block_fix.py -q   # 14 passed
python -m pytest tests/parser/ -q                                            # 938 passed, 9 pre-existing unrelated failures
python -m pytest tests/dataset/ tests/behavioral/ tests/parser/ tests/modernization/test_intelligence_pipeline.py -q
                                                                               # 1116 passed, 9 pre-existing unrelated failures
python -m pytest tests/ -q                                                   # 3705 passed, 12 pre-existing unrelated failures
python -m black --check app/parser/syntax/procedure_parser.py app/dataset/version.py tests/parser/test_compute_evaluate_in_if_block_fix.py tests/dataset/test_mmim_v2_dataset.py tests/dataset/test_instruction_adapter_v2.py tests/parser/test_unsupported_syntax_reporting.py tests/modernization/test_intelligence_pipeline.py
                                                                               # all unchanged
python -m ruff check app/ tests/                                             # all checks passed
python -m mypy app/dataset/ app/behavioral/ app/parser/ --ignore-missing-imports
                                                                               # no issues, 96 files
```

**The 9 (`tests/parser/`) / 12 (full suite) failures are pre-existing and unrelated** —
identical set to the previous parser task's report, re-verified: `git diff --stat` on
every failing test's file shows zero diff for this session too. Three
(`tests/ir/test_ir_control_flow.py`) are the stale `IfStatementNode(condition=...)`
keyword-argument test helper (a field that has never existed); the other nine are
pre-existing `TokenType`/`_SYMBOLS`/missing-period assertions confined to code paths this
fix never touches. None were touched or "fixed" here, per scope; none were weakened.

No existing test was weakened, skipped, or deleted. Two pre-existing regression tests had
their **pinned values** corrected — from the bug's output to this fix's
independently-verified-correct output, with the exact reasoning recorded in-line:
`tests/parser/test_unsupported_syntax_reporting.py::test_complex_fixture_surfaces_45_syntax_diagnostics`
(44 → 45, renamed; §6 above) and
`tests/modernization/test_intelligence_pipeline.py::test_complex_fixture_intelligence_shape`
(10 → 13 business rules).

## 11. Exact files changed

- `app/parser/syntax/procedure_parser.py` (140 insertions, 13 deletions) — the fix itself.
- `app/dataset/version.py` (66 insertions, 3 deletions) — `MMIM_GENERATOR_VERSION_V5`.
- `tests/parser/test_compute_evaluate_in_if_block_fix.py` (new) — 14 focused regression
  tests.
- `tests/parser/test_unsupported_syntax_reporting.py` — one pinned diagnostic count
  corrected (44 → 45) with reasoning.
- `tests/modernization/test_intelligence_pipeline.py` — one pinned business-rule count
  corrected (10 → 13) with reasoning.
- `tests/dataset/test_mmim_v2_dataset.py` — generator-version references updated to
  `MMIM_GENERATOR_VERSION_V5`; validation-coverage assertion updated 29 → 30; one
  business-rule-density expectation updated (`t_credit_approval` 4 → 11,
  `t_tax_withhold` 4 → 6, `t_payroll_deduct` 10 → 11); new tests added for this fix's
  specific gain and non-regression of the prior fix's gains.
- `tests/dataset/test_instruction_adapter_v2.py` — generator-version reference and
  example-count assertion (344 → 345) updated.
- `docs/MMIM_V2_DATASET_AUDIT.md` — updated (history preserved, not removed) for the
  `mmim-gen-v5` regeneration.
- `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` — this document (new).
- `data/dataset/mmim-v2/**` — regenerated in place (superseding `mmim-gen-v4`'s build).

No file outside this list was modified. `data/benchmark/**` and `data/dataset/mmim-v1/**`
were not written to at any point (verified via `git status --short data/benchmark/` —
clean — and re-reading `mmim-v1`'s own manifest, unchanged: `mmim-v1`, 144 examples,
18 sources).
