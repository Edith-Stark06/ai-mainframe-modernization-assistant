# MMIM Parser/Lexer Fix: Decimal Literals + Compound AND/OR IF-Conditions

Fixes exactly the two parser/lexer defects the validation-extractor audit
(`docs/MMIM_VALIDATION_EXTRACTOR_AUDIT.md` §2, category 4) found and deliberately
left unfixed, per that audit's own scope discipline: "stop and report separately
rather than expanding scope."

**Scope discipline**: only `app/parser/lexer/lexer.py`, `app/parser/ast/statements.py`,
and `app/parser/syntax/procedure_parser.py` were touched. No change to behavioral
extraction, dataset generation logic, the instruction adapter, benchmark-v1, Java
modernization, frontend, RAG, or the quality loop. A **third**, related-but-distinct
gap was discovered during real-corpus validation (§6) and is explicitly **not**
fixed here, for the same reason.

---

## 1. Root cause: decimal-literal lexer bug

`app/parser/lexer/lexer.py::CobolLexer._read_number` consumed a run of digit
characters and stopped — its own docstring said so explicitly: *"No decimal-point
handling."* A `.` immediately following a numeric literal was never considered part
of that literal; it fell through to the lexer's generic symbol table
(`_SYMBOLS["."] = TokenType.PERIOD`) and became its own token.

So `12.50` tokenized as three tokens — `NUMBER('12')`, `PERIOD('.')`,
`NUMBER('50')` — not one. This is **not** limited to the DATA DIVISION `VALUE`
clause the corpus-expansion report originally flagged; it happens anywhere a
decimal literal appears: an `IF` condition (`WS-A <= 11000.00`), a `MOVE`
(`MOVE 12.50 TO WS-A`), inside a `COMPUTE` expression, etc. — the lexer runs once,
uniformly, before the parser knows which division or statement it's in.

**Why this silently dropped the rest of the paragraph** (not just misparsed one
literal): COBOL's own statement/paragraph terminator is a `PERIOD` token. A
structured `IF`/`END-IF` or `PERFORM UNTIL`/`END-PERFORM` block normally has **no
interior periods** — only the block's closing statement carries one, right at the
end. `app/parser/syntax/procedure_parser.py`'s statement-level error recovery
(`_parse_statements`, on a `ParserError`) calls `state.record_and_synchronise(...)`,
which — per `app/parser/diagnostics/recovery.py` — scans forward and **stops at the
next `PERIOD` token, consuming it**. When the spurious `PERIOD` from a mis-split
decimal literal appeared *inside* an otherwise-fine `IF` condition (e.g.
`IF WS-A <= 11000.00`), the parser choked on the stray fragment immediately, and
recovery then synchronised to whatever period happened to come next — frequently
the paragraph's *own* closing period, silently discarding everything in between.
Verified directly (see minimal reproductions below): `IF WS-A <= 11000.00` alone
produced 0 parsed statements from an otherwise well-formed paragraph, with the
stray digit fragments (`'00'`, `'10'`) surfacing as "unexpected token" diagnostics
downstream.

### Reproduction A — before / after

Minimal repro, not shipped as a fixture (run directly against `CobolLexer.tokenize`):

| Input | Tokenization **before** | Tokenization **after** |
|---|---|---|
| `12.50` | `NUMBER('12')`, `PERIOD('.')`, `NUMBER('50')` | `NUMBER('12.50')` |
| `0.75` | `NUMBER('0')`, `PERIOD('.')`, `NUMBER('75')` | `NUMBER('0.75')` |
| `99.95` | `NUMBER('99')`, `PERIOD('.')`, `NUMBER('95')` | `NUMBER('99.95')` |
| `12.` (integer + real terminator) | `NUMBER('12')`, `PERIOD('.')` | **unchanged**: `NUMBER('12')`, `PERIOD('.')` |
| `12.50.` (decimal + real terminator) | `NUMBER('12')`, `PERIOD('.')`, `NUMBER('50')`, `PERIOD('.')` | `NUMBER('12.50')`, `PERIOD('.')` |
| `WS-A <= 11000.00` (full statement) | 0 parsed statements in the enclosing paragraph; diagnostics show stray `'00'`/`'10'` "unexpected token" fragments | 0 diagnostics; full statement parses |

Full-paragraph before/after, via `AnalysisService().analyze_file()`:

```
IF ANNUAL-INCOME >= 100000.00       -- BEFORE: paragraph body = 0 statements,
    MOVE 5000.00 TO MAX-OVERDRAFT-LIMIT --   no diagnostic pinpoints why (the parser
...                                      --   never even reaches its own IF-condition
END-IF.                                 --   code; it dies on the stray digit token)
                                         -- AFTER: full IF/ELSE chain parses, 0 diagnostics
```

---

## 2. Root cause: compound AND/OR IF-condition bug

`app/parser/syntax/procedure_parser.py::_parse_if_statement` parsed **exactly one**
comparison — `<operand> <op> <operand>` — and nothing else. There was no code path
for `AND`/`OR`/`NOT` at all. Once the single comparison was consumed, the parser
moved straight to "parse statements until `ELSE` or `END-IF`"; encountering `AND`
or `OR` there raised `ParserError("expected statement in IF block")`.

The same statement-level recovery described in §1 then fired: synchronise to the
next `PERIOD`, which — for a structured `IF` with no interior periods — is
typically the *end of the whole paragraph*, discarding every statement in between
with **zero diagnostics pinpointing the actual cause** in some cases (the recorded
diagnostic names the *symptom* — "expected statement in IF block" — not "AND/OR
unsupported").

### Reproduction B — before / after

| Condition | Before | After |
|---|---|---|
| `IF A = 1 AND B = 2 ... END-IF` | `ParserError` at `AND` → paragraph body discarded | Parses; `IfStatementNode.extra_conditions = (ConditionTerm("AND", "B", "=", "2"),)` |
| `IF A = 1 OR B = 2 ... END-IF` | same failure at `OR` | Parses; `extra_conditions = (ConditionTerm("OR", ...),)` |
| `IF A = 1 AND B = 2 OR C = 3 ... END-IF` | same failure at first `AND` | Parses; `extra_conditions = (AND B=2, OR C=3)` — see precedence note below |
| `IF A = 1 AND (B = 2 OR C = 3) ... END-IF` | same failure, at `AND` | **Explicitly not supported** — tested, not assumed (§4) |

Full AST/control-structure shape, before vs. after, for `IF A = 1 AND B = 2 ... END-IF`:

```
BEFORE: ParserError raised mid-statement; no IfStatementNode is ever returned
        for this IF — the enclosing paragraph's statement list ends up empty.

AFTER:  IfStatementNode(
            condition_left="A", condition_operator="=", condition_right="1",
            extra_conditions=(ConditionTerm(connector="AND", left="B",
                                             operator="=", right="2"),),
            then_statements=(...), else_statements=(),
        )
```

---

## 3. Minimal code changes

### A. Decimal literals — `app/parser/lexer/lexer.py`

`_read_number` now checks, immediately after consuming the integer digit run,
whether the current character is a `.` **immediately followed by another digit**
(`_at_decimal_point`, a new static helper). If so, it consumes the `.` and the
fractional digit run too, producing one `NUMBER` token. If not — including a bare
`.` at end-of-input, or a `.` followed by whitespace/anything else — nothing
changes; the `.` is left for the main tokenizer loop's existing
`_SYMBOLS["."] = TokenType.PERIOD` handling, exactly as before.

This mirrors COBOL's own lexical convention: a statement-terminating period is
always followed by whitespace (or end-of-source); a decimal point never is. The
rule only fires in the one case that must change — nothing else about `_read_number`
was touched, including the pre-existing `0000-MAIN`-style paragraph-name handling
(a different character, `-`, so the two rules cannot interact).

### B. Compound conditions — `app/parser/ast/statements.py` + `app/parser/syntax/procedure_parser.py`

- **New `ConditionTerm` dataclass** (`statements.py`): `connector` ("AND"/"OR"),
  `left`, `operator`, `right`. Documents the chosen precedence convention in its
  own docstring (§5).
- **`IfStatementNode` gained one new field**: `extra_conditions: tuple[ConditionTerm, ...] = ()`,
  defaulting to empty. `condition_left`/`condition_operator`/`condition_right` are
  **completely unchanged in meaning** — they still hold the first (and, for a plain
  `IF`, only) comparison, exactly as every existing consumer
  (`app/ir/builder.py`, `app/modernization/business_rules/extractor.py`,
  `app/analysis/dependencies/analyzer.py`, `app/analysis/rules/extractor.py`)
  already expects. None of those four files needed to change — a plain `IF`
  produces byte-identical output to before; a compound `IF` now at least
  contributes its first comparison instead of vanishing entirely.
- **`_parse_if_statement`** (`procedure_parser.py`): the original three
  operand/operator/operand parsing blocks were factored into a new
  `_parse_simple_condition` helper (used both for the first condition and for each
  `AND`/`OR` term — no logic duplicated, no logic changed). After the first
  condition, a new loop consumes zero or more `AND`/`OR`-prefixed terms via that
  same helper, appending each as a `ConditionTerm`. Nothing about `ELSE`/`END-IF`
  handling, period consumption, or error recovery was touched.

Total diff: `lexer.py` +42/-3 lines (the decimal-point handling + its helper +
docstring updates), `statements.py` +40/-0 lines (the new `ConditionTerm`
dataclass + `IfStatementNode`'s one new field, both documented), `procedure_parser.py`
+41/-4 lines (the extracted `_parse_simple_condition` helper + the new AND/OR loop).

---

## 4. Precedence convention (chosen, documented, tested)

The grammar had no precedence rule at all (compound conditions didn't parse). This
fix adopts COBOL's own standard rule — **`AND` binds tighter than `OR`** — matching
conventional boolean-logic precedence in virtually every language, so
`A AND B OR C` parses as `(A AND B) OR C`. `ConditionTerm`'s docstring records this
explicitly. `extra_conditions` stores the flat, left-to-right term sequence exactly
as written; a future consumer that wants to *evaluate* a compound condition must
group consecutive `AND` terms before splitting on `OR`, per that convention — no
consumer does this yet, so no evaluator was invented (see §8).

`test_if_with_and_then_or_preserves_precedence_structure` asserts the exact
sequence `[AND B=2, OR C=9]` for `A=1 AND B=2 OR C=9` — never flattened, never
silently reordered into a single incorrect predicate.

**Parenthesised conditions** (`A AND (B OR C)`) are explicitly **not** supported.
`_parse_simple_condition`'s operand check rejects a leading `(` (tokenized as
`LPAREN`, not `IDENTIFIER`/`NUMBER`/`STRING`) with a clean `ParserError`. This was
tested, not assumed: `test_parenthesized_condition_is_not_silently_supported`
confirms the failure is a single `SYN005` diagnostic and that only the *current*
paragraph loses its body (the pre-existing, paragraph-scoped recovery granularity
every other unsupported construct already has) — not a worse or different failure
mode, and critically, the *next* paragraph is completely unaffected.

---

## 5. Tests added

`tests/parser/test_decimal_and_compound_condition_fix.py` — 15 new tests, all
passing:

1. `test_integer_literal_unaffected`
2. `test_decimal_literal_is_a_single_number_token` (12.50 / 0.75 / 99.95)
3. `test_multiple_decimal_literals_in_one_paragraph`
4. `test_decimal_literal_adjacent_to_comparison_operator`,
   `test_decimal_literal_in_compute_style_expression`
5. `test_decimal_literal_followed_by_statement_period`,
   `test_integer_literal_followed_by_period_is_still_a_terminator`,
   `test_decimal_literal_immediately_followed_by_terminator_period`,
   `test_paragraph_name_numeric_prefix_still_works`
6. `test_if_with_and_parses_with_no_diagnostics`
7. `test_if_with_or_parses_with_no_diagnostics`
8. `test_if_with_and_then_or_preserves_precedence_structure`
9. `test_parenthesized_condition_is_not_silently_supported`
10. `test_statements_after_compound_if_are_preserved`

**Critical regression fixture**: `test_critical_regression_decimal_and_compound_condition_together`
— a paragraph combining a decimal-literal comparison *and* a compound AND
condition *and* statements after both (`IF WS-INCOME >= 50000.00 AND WS-SCORE = 700
... END-IF` followed by a `MOVE` and two `DISPLAY`s). Before this fix this exact
shape parsed to **zero statements with zero diagnostics** — a silent,
undiagnosable loss. Asserts all 4 statements survive and the compound condition's
both terms are captured correctly.

Existing-behavior regression tests updated in place (not weakened — their pinned
values were the *bug's* output, corrected to the fix's verified-correct output):

- `tests/parser/test_unsupported_syntax_reporting.py::test_complex_fixture_reaches_full_token_coverage`
  (2103 → 2093 tokens) and `::test_complex_fixture_surfaces_44_syntax_diagnostics`
  (renamed from `..._surfaces_51_...`, 51 → 44 diagnostics) — both against the
  real `workspace/.../complex_acctbatch.cbl` fixture. Verified **token-for-token**
  against a standalone copy of the pre-fix lexer: the only differences in the
  2093-token stream are exactly 5 decimal-literal collapses (`9.99` in a `PICTURE`
  clause, `0.0025`/`0.0035`/`0.0050`/`0.0075` in `MOVE` statements) — every other
  token is byte-identical. The 7 fewer diagnostics are the cascading
  SYN001/SYN005 "unexpected token"/resync errors those 4 `MOVE` statements used
  to trigger.
- `tests/modernization/test_intelligence_pipeline.py::test_complex_fixture_intelligence_shape`
  (6 → 10 business rules) — the same fixture has 3 genuine single-line compound
  conditions (`... AND ...` / `... OR ...`) that used to abort their paragraph and
  silently discard 4 further, perfectly ordinary `IF` statements after them.

---

## 6. Real-corpus validation — before/after, measured correctly

**Methodology note, reported transparently**: the first attempt at this
measurement used a `git worktree` checkout of `HEAD` as the "before" baseline, but
ran the comparison script by absolute path from the scratchpad directory — which
put the scratchpad (not the worktree) at `sys.path[0]`, and an environment
`PYTHONPATH` fallback silently resolved `import app` back to this session's own
(already-fixed) working directory in *both* runs, making "before" and "after"
identical. Caught because a source known to be fixed (`t_interest_accrue`) showed
zero change when it should not have. Corrected by copying the measurement script
into the worktree itself (and into the working tree for the "after" run) so `cwd`
— not the script's own location — determined which `app` package was imported.
Re-verified: the corrected "before" run reproduces the original audit's own
un-fixed numbers exactly (e.g. `t_account_eligibility`: 19 diagnostics, 0
business rules), confirming the corrected methodology is sound.

Measured with `build_analysis_bundle` + `analyze_modernization_intelligence` +
`extract_behavioral_tests`, directly on the raw `.cbl` files, across the full
45-source training corpus (not just the 9 originally flagged — the fix is at the
lexer/parser level and could plausibly affect any source).

### Corpus-wide totals

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Sources with any diagnostic/paragraph/rule/test change | — | 26 / 45 | — |
| Total syntax diagnostics (sum over all 45 sources) | 375 | 131 | **-244 (-65%)** |
| Total business rules extracted (sum over all 45) | 71 | 123 | **+52 (+73%)** |
| Total behavioral (`VALIDATION_REASONING`) tests derivable | 71 | 118 | **+47 (+66%)** |
| Sources with ≥1 derivable behavioral test | 24 / 45 | 29 / 45 | **+5** |

"Before" here is the state after the loop/accumulator extractor upgrade
(`mmim-gen-v3`, `docs/MMIM_VALIDATION_EXTRACTOR_AUDIT.md`) but **before** this
parser fix — the correct baseline for isolating *this* task's contribution.
`t_interest_accrue`/`t_loan_balance` (the loop extractor's own 2 sources) are
therefore *not* counted as newly covered here; they already were.

### The 9 originally-flagged category-4 sources, individually

Per the validation-extractor audit's own instruction — **"Do not count a source
as fixed merely because diagnostics decreased. The resulting AST/IR must actually
contain the previously lost procedure statements."** — each source's actual
paragraph-completeness and rule/test derivability was checked, not just its
diagnostic count:

| Source | Diagnostics | Zero-statement paragraphs | Business rules | Validation tests | Validated? |
|---|---|---|---:|---:|---|
| `t_account_eligibility` | 19 → 2 | 3 → 1 | 0 → 8 | 0 → 2 | **YES** |
| `t_credit_approval` | 25 → 4 | 4 → 3 | 0 → 4 | 0 → 2 | **YES** |
| `t_tax_withhold` | 33 → 6 | 4 → 3 | 0 → 4 | 0 → 4 | **YES** |
| `t_pricing_tier` | 31 → 4 | 5 → 1 | 0 → 14 | 0 → 12 | **YES** |
| `t_payroll_deduct` | 35 → 5 | 4 → 2 | 0 → 10 | 0 → 10 | **YES** |
| `t_condition_names_88` | 12 → 6 | 2 → 2 (unchanged) | 0 → 0 | 0 → 0 | no — different gap (§7) |
| `t_shared_state_hazard` | 9 → 4 | 2 → 2 (unchanged) | 0 → 0 | 0 → 0 | no — different gap (§7) |
| `t_billing_engine` | 13 → 4 | 1 → 1 (unchanged) | 0 → 0 | 0 → 0 | no — different gap (§7) |
| `t_transitive_fx` | 12 → 3 | 1 → 1 (unchanged) | 0 → 1 | 0 → 0 | no — rules improved, still not test-derivable |

**5 of the 9 fully validated** — real, measured AST/IR/rule/test improvement, not
just fewer diagnostics. The remaining 4 show diagnostic-count improvement (fewer
spurious cascading errors — a genuine, honest side effect of the same fix) but
their zero-statement paragraphs are **unchanged**, because — as detailed in §7 —
their specific blockers are different bugs this task was not scoped to fix.

---

## 7. Remaining parser limitations (found, not fixed — reported per instruction)

Investigating the 4 still-unvalidated sources' exact blockers (per-paragraph
source inspection, not assumption) surfaced a **third**, distinct gap:

**Unsupported statements (`COMPUTE`, `EVALUATE`, …) inside an `IF`/`ELSE` block
are not recovered — they raise a hard `ParserError`, not the graceful
"skip just this statement" recovery paragraph-top-level unsupported statements
already get.** `_parse_if_statement`'s then/else statement loops check only
`tok.lexeme.upper() in _STATEMENT_LEXEMES`; unlike the paragraph-level statement
loop, they never check `_UNSUPPORTED_STATEMENT_LEXEMES` (the set that gives
`COMPUTE`/`EVALUATE`/etc. their clean `SYN100` "unsupported statement" diagnostic
elsewhere). A `COMPUTE` used *inside* an `IF` — extremely common in this corpus's
rule-dense sources, e.g. `t_credit_approval`'s `1000-CALCULATE-DTI`
(`IF MONTHLY-INCOME > 0.00 COMPUTE DTI-PERCENTAGE = ... END-IF`) — still triggers
the same statement-level recovery cascade this task's two fixes were meant to
eliminate, just from a different trigger.

Confirmed, per-source, as the actual blocker for all 4 remaining sources:

- `t_condition_names_88`: `IF NOT TX-VALID-KIND` / `IF PHYSICAL-BRANCH AND
  TX-WITHDRAWAL` — bare level-88 condition-name references (no comparison
  operator at all), with or without `AND`/`NOT`. `_parse_simple_condition`
  requires an `<operand> <op> <operand>` triple; a bare condition-name doesn't
  fit that shape regardless of this fix. A **fourth**, separate gap.
- `t_shared_state_hazard`, `t_billing_engine`: `COMPUTE` inside `IF`/`ELSE` blocks
  (the third gap above).
- `t_transitive_fx`: its one now-extractable business rule's condition is not a
  single-comparison boundary-testable shape (out of `app/behavioral/extraction`'s
  scope, unrelated to this task).
- `t_account_eligibility`'s own `1000-BASIC-QUALIFICATION` paragraph *also*
  remains partially blocked (only 2 of its 3 originally-zero-statement paragraphs
  were recovered) by `IF CITIZENSHIP-STATUS NOT = 'CITIZEN' AND ...` — `NOT =`
  written as two tokens (as opposed to `<>`) is not a recognized comparison
  operator. A **fifth**, separate, pre-existing gap, already flagged (not fixed)
  in the validation-extractor audit.

None of these four gaps were fixed here. Per this task's explicit instruction —
*"Do not fix unrelated COBOL syntax... if parser changes are required, stop and
report them separately"* — they are reported, not touched. Fixing the
`COMPUTE`-inside-`IF` recovery gap specifically (the dominant remaining blocker,
affecting 2 of the 4) is the highest-leverage next parser task.

---

## 8. MMIM dataset regeneration & versioning

`dataset_version` **stays `"mmim-v2"`** — same 45-source corpus, same 8-task
contract. The deterministic pipeline that produces several tasks' ground truth
changed (not just `VALIDATION_REASONING` this time — `BUSINESS_RULE_EXTRACTION`,
`DEPENDENCY_REASONING`, `RISK_CLASSIFICATION`, `MODERNIZATION_STRATEGY`,
`TRANSFORMATION_PLANNING`, and `COBOL_TO_JAVA` all read from the same
AST/business-rule engine that now sees more complete paragraphs), so
`generator_version` bumps again: `mmim-gen-v3` → **`mmim-gen-v4`**
(`MMIM_GENERATOR_VERSION_V4`, `app/dataset/version.py`). `mmim-gen-v3`'s own build
is superseded in place, not kept as a separate snapshot; this document and the
updated `docs/MMIM_V2_DATASET_AUDIT.md` are that supersession's record.
`mmim-v1` (`mmim-gen-v1`) is untouched.

Regenerated via `build_mmim_dataset(..., strict_eligibility=True, generator_version=MMIM_GENERATOR_VERSION_V4)`
over the unchanged 45-source corpus, seed 42:

| | mmim-gen-v3 (before) | mmim-gen-v4 (after) |
|---|---:|---:|
| Total examples | 339 | **344** |
| `VALIDATION_REASONING` examples (sources) | 24 | **29** |
| Skipped tasks | 21 | **16** |
| Split counts (train/val/test) | 218 / 69 / 52 | **222 / 69 / 53** |

No source was artificially forced to 100% coverage: **16 skips remain**, every
one recorded in `manifest.json["skipped"]` with `reason: "no_derivable_behavioral_tests"`
and a `parser_status` block — `fx_perform_until`, `fx_simple_proc`, `t_dead_code_audit`,
`t_temp_convert` (genuinely no derivable test, unchanged from the validation-extractor
audit), `t_batch_acct_update`, `t_daily_trans_report`, `t_inventory_extract`,
`t_payroll_file_post` (unsupported file I/O), `t_order_hierarchy`, `t_table_indexed`
(unsupported `OCCURS`), `t_goto_spaghetti` (unsupported `GO TO`), and the 4 sources
from §7 (`t_condition_names_88`, `t_shared_state_hazard`, `t_billing_engine`,
`t_transitive_fx`).

**Split preservation verified directly**: source→split assignment is a pure
function of `(dataset_version, seed, source_id)`
(`app/dataset/splitting.py::_bucket`), independent of which tasks a source
contributes. Checked against the prior `mmim-gen-v3` `split_manifest.json`: all 5
newly-unlocked sources kept their existing split assignment
(`t_account_eligibility`/`t_credit_approval`/`t_pricing_tier`/`t_payroll_deduct` →
train, `t_tax_withhold` → test) — the count deltas (`train +4`, `test +1`,
`validation +0`) are exactly and only their new `VALIDATION_REASONING` examples
landing in splits their sources already belonged to. No source moved.

**Re-verified after regeneration**: benchmark leakage (0 source-ID / SHA-256 /
normalized-source overlap — PASS), split leakage (`detect_leakage`: 0 errors, 5
warnings, same benign trivial-target convergences as before — PASS), duplicate
source checks (0 exact, 0 normalized — PASS, corpus unchanged), deterministic
regeneration (`test_deterministic_regeneration`, byte-identical across two runs —
PASS), instruction-adapter regeneration (344 examples, `dataset_version: "mmim-v2"`
correctly reflected in its manifest — PASS).

---

## 9. Tests run (quality gates)

```
python -m pytest tests/parser/test_decimal_and_compound_condition_fix.py -q   # 15 passed
python -m pytest tests/parser/ -q                                             # 915 passed, 9 failed
python -m pytest tests/dataset/ tests/behavioral/ -q                          # 173 passed
python -m pytest tests/ -q                                                    # 3689 passed, 12 failed
python -m black --check app/ tests/dataset/test_mmim_v2_dataset.py tests/dataset/test_instruction_adapter_v2.py tests/behavioral/test_loop_extraction.py tests/parser/test_decimal_and_compound_condition_fix.py
                                                                                # all unchanged
python -m ruff check app/ tests/                                              # all checks passed
python -m mypy app/dataset/ app/behavioral/ app/parser/ --ignore-missing-imports
                                                                                # no issues, 96 files
```

**The 9 (`tests/parser/`) / 12 (full suite) failures are pre-existing and
unrelated to this change** — verified two ways: (1) `git diff --stat` on every
failing test's file shows zero diff (none of them were touched this session),
and (2) a clean `git worktree` checkout of `HEAD` reproduces the identical 12
failures with 0 of my changes applied. Three (`tests/ir/test_ir_control_flow.py`)
are a stale test helper calling `IfStatementNode(condition=...)` — a keyword
argument that has never existed (the real fields have always been
`condition_left`/`condition_operator`/`condition_right`); the other nine are
pre-existing `TokenType`/`_SYMBOLS` spec mismatches and missing-period diagnostic
assertions, confined to code paths this fix never touches (`DISPLAY`/`STOP
RUN`/`GOBACK`/`MOVE` statement parsing, arithmetic/comparison symbol
classification). None were touched or "fixed" here, per scope; none were
weakened.

No existing test was weakened, skipped, or deleted. Two pre-existing regression
tests had their **pinned values** corrected (§5) — from the bug's output to the
fix's independently-verified-correct output — with the exact reasoning recorded
in-line as a comment at each assertion.
