# STEP 10 — Decimal-Literal Condition Extraction Fix

## 1. Read before editing

- `docs/MMIM_PARSER_VALIDATION_FIX.md` — the earlier decimal-literal *tokenization*
  fix (PROCEDURE DIVISION lexing) and compound AND/OR IF-condition parsing.
  A different layer: that fix made the parser/AST see the decimal literal
  correctly. This fix is about a *separate*, downstream module —
  `app/behavioral/extraction/conditions.py` — re-parsing the AST-derived
  `condition` string a business rule already carries, for boundary-test
  generation. The AST/parser was never the problem here.
- `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §7-§8 — where this gap was first
  identified: `t_billing_engine`'s two IF-guarded decimal conditions parse
  completely (confirmed via `SYN100` diagnostics, statement counts, and a
  direct AST dump) but still produced zero behavioral validation tests.
- `docs/MMIM_V2_DATASET_AUDIT.md` — current dataset state before this fix:
  345 examples, 30/45 (66.7%) VALIDATION_REASONING coverage, `mmim-gen-v5`.
- `app/behavioral/extraction/conditions.py` — `parse_condition`,
  `generate_boundary_values`, the `_NUMERIC`/`_COND_RE` regexes.
- `app/behavioral/extraction/extractor.py` — the caller: `extract_behavioral_tests`
  feeds each business rule's `condition` string into `parse_condition`, and
  `_evaluate` independently re-implements the same numeric comparison for
  each generated boundary value.
- `tests/behavioral/test_extraction.py` — the only pre-existing direct tests
  of `parse_condition`/`generate_boundary_values` (integer-only).

## 2. Reproduction — before this fix

```python
>>> from app.behavioral.extraction.conditions import parse_condition
>>> parse_condition("RATE = 0")
Comparison(variable='RATE', operator='=', literal='0', is_numeric=True, ...)
>>> parse_condition("RATE = 0.00")
None
>>> parse_condition("RATE = 12.50")
None
>>> parse_condition("RATE = -1.25")
None
```

Integer conditions parse; every decimal condition returns `None`.

## 3. Root cause

Two independent problems, both in `conditions.py`, both required for the fix:

**A. `_COND_RE`'s literal alternation, not just `_NUMERIC`.** The obvious
suspect is `_NUMERIC = re.compile(r"^-?\d+$")`, which indeed rejects
decimals. But that regex only runs *after* the outer `_COND_RE` has already
matched. `_COND_RE`'s literal group was
`(?P<lit>'[^']*'|"[^"]*"|-?\d+)` — no decimal-point alternative at all. For
`"RATE = 0.00"`, the `-?\d+` branch greedily matches `"0"`, leaving `.00`
unconsumed before the required trailing `\s*$` anchor; the match fails
entirely (no backtrack rescues it — `\d+` cannot match fewer than one
digit and still leave `.00` unaccounted for). So `parse_condition` returns
`None` for the *whole condition*, not merely with `is_numeric=False`. Fixing
only `_NUMERIC` would have done nothing.

**B. `generate_boundary_values` assumed integer literals.** `n = int(cmp.literal)`
and a fixed step of `1` are baked into the boundary-partition logic; a
decimal literal would raise `ValueError` even if `_COND_RE` were fixed
without an accompanying change here.

**C. (downstream, not in `conditions.py`) `extractor.py::_evaluate` had the
same `int()` assumption** for scoring which boundary value satisfies which
comparison, independently of `generate_boundary_values`. Left unfixed, a
decimal condition would parse correctly and even produce boundary value
strings, but `_evaluate` would raise `ValueError` the moment it tried to
score `"0.01" ` against `"0.00"` — the whole `extract_behavioral_tests` call
would crash, not just silently under-cover. Verified by reproduction
(patched A+B only, called `extract_behavioral_tests` on `t_billing_engine`,
observed the traceback).

Not tokenization, not IF-block/EVALUATE-scope, not COMPUTE operand parsing —
this is purely the `condition`-string mini-grammar in one behavioral-test
extraction module and its numeric-comparison helper in its one caller. The
parser and AST were never involved; `bundle.business_rules[...]["condition"]`
already contained the correct decimal text (`"TAX-OUT-TAX-RATE = 0.00"`)
before this fix — `parse_condition` just couldn't read it.

## 4. The fix — narrowest additive change

**`app/behavioral/extraction/conditions.py`**

```python
_NUMERIC = re.compile(r"^-?\d+(?:\.\d+)?$")
_COND_RE = re.compile(
    r"^\s*(?P<not>NOT\s*\(\s*)?"
    r"(?P<var>[A-Z0-9][A-Z0-9-]*)\s*"
    r"(?P<op>>=|<=|<>|=|>|<)\s*"
    r"(?P<lit>'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?)"
    r"(?(not)\s*\))\s*$",
    re.IGNORECASE,
)
```

An ordinary decimal literal: optional sign, digits, optional `.` + digits.
No exponent/scientific-notation form — nothing in the repository's parser
or business-rule engine ever emits one (confirmed by grepping every
`IF`/`WHEN ... <op> <literal>` decimal condition in the 45-source corpus:
all are plain `digits.digits`, e.g. `0.00`, `12.50`, `0.0000`).

```python
def _numeric_step(literal: str) -> Decimal:
    if "." in literal:
        frac_len = len(literal.split(".", 1)[1])
        return Decimal(1).scaleb(-frac_len)
    return Decimal(1)


def generate_boundary_values(cmp: Comparison) -> list[tuple[str, bool]]:
    op = cmp.effective_operator
    if cmp.is_numeric:
        n = Decimal(cmp.literal)
        step = _numeric_step(cmp.literal)
        candidates = [n - step, n, n + step]
        ...  # unchanged: same non-negative filter, same seen-set dedup
```

`Decimal` (not `float`) avoids introducing binary floating-point rounding
into what is fundamentally COBOL fixed-point arithmetic. The step is
derived from the literal's own precision (`0.00` → step `0.01`; `0.0000` →
step `0.0001`) rather than a hardcoded assumption — this generalizes
correctly to any `PIC 9(n)V9(m)` precision without a general-purpose
numeric-expression parser (still no operators, no expressions — one
literal, its own precision, done).

**`app/behavioral/extraction/extractor.py`**

```python
def _evaluate(cmp: Comparison, value: str) -> bool:
    op = cmp.effective_operator
    if cmp.is_numeric:
        v, n = Decimal(value), Decimal(cmp.literal)
        ...  # unchanged comparison table
```

The only other site with the same integer assumption. `_apply_action`'s
ARITH-op branch (`ADD`/`SUBTRACT`/`MULTIPLY`/`DIVIDE`) was checked and left
untouched: it already guards with `lit.lstrip("-").isdigit()`, which is
`False` for a decimal literal like `"7.25"`, so it safely falls through to
"leave the result implicit" — exactly its documented behavior for any
non-integer literal, not a new gap. Widening that guard to compute decimal
arithmetic results would be a business-rule/calculation semantics change,
out of this task's explicit scope.

### What was preserved

- **Integer behavior**: `_numeric_step` returns `Decimal(1)` for any
  literal without a `.`, and `str(Decimal(1))`/`str(Decimal(0))` etc. print
  identically to the old `str(int)` output — every existing integer
  boundary-value string is byte-identical to before.
- **Negative values**: parsing negative literals (`-1`, `-1.25`) already
  worked/now works identically; `generate_boundary_values`' pre-existing
  `if v in seen or v < 0: continue` filter is untouched, so negative
  decimals are dropped from boundary candidates by exactly the same policy
  negative integers already were (verified: `RATE = -1` still yields
  `[('0', False)]`, `RATE = -1.25` now yields `[]`, the qualitatively
  identical "everything candidate is negative" shape).
- **Existing comparison operators**: the operator table (`_holds`,
  `_holds_str`, `effective_operator`) is untouched; only the operand type
  changed from `int` to `Decimal`, and `Decimal` supports the same
  comparison operators with the same semantics.
- **Condition AST/data structures**: `Comparison` dataclass is unchanged —
  no new fields, no signature change.
- **Deterministic extraction**: `Decimal` arithmetic is exact for the
  base-10 literals COBOL fixed-point fields use (no `float` rounding);
  same input always produces the same output string.
- **Source provenance**: untouched — `conditions.py` never touched source
  locations; `extractor.py`'s `_rule_source_refs`/`SourceRef` wiring is
  unchanged.
- **Malformed-literal rejection**: `"RATE = 0."`, `"RATE = .5"`,
  `"RATE = 12.5X"`, `"RATE = 12..5"`, `"RATE = 12,50"`, `"RATE = 1.2.3"` all
  still return `None` — the regex requires at least one digit before and
  after the `.`, and no more than one `.`.
- **Not a general-purpose numeric-expression parser**: still exactly one
  `<var> <op> <literal>` (optionally `NOT (...)`-wrapped); no arithmetic
  expressions, no multi-term conditions, no new COBOL-specific literal
  forms (no `ZERO`/`SPACES` figurative constants, no signed-trailing
  notation) were added — none appear in any condition string the
  business-rule engine actually emits (confirmed by corpus grep, §3).

## 5. Tests added

`tests/behavioral/test_decimal_condition_extraction_fix.py` — 25 tests:

- `test_integer_literal_condition_still_parses`,
  `test_integer_boundary_values_unchanged`,
  `test_negative_integer_condition_still_parses_and_filters_as_before` —
  integer-behavior regression pins.
- `test_zero_decimal_literal_condition_parses`,
  `test_zero_decimal_boundary_values_step_by_one_hundredth` — the `0.00`
  case directly from `t_billing_engine`.
- `test_positive_decimal_literal_condition_parses` — `12.50`.
- `test_negative_decimal_literal_condition_parses` — `-1.25`, mirroring the
  pre-existing negative-integer boundary policy.
- `test_decimal_literal_with_every_supported_comparison_operator` —
  parametrized over `>=`, `<=`, `<>`, `=`, `>`, `<`.
- `test_decimal_literal_four_fractional_digits_steps_precisely` — proves
  the step is precision-derived, not hardcoded to two decimal places.
- `test_not_wrapped_decimal_condition_parses` — `NOT (RATE = 0.00)`.
- `test_malformed_decimal_syntax_still_rejected` — parametrized over 6
  malformed forms; each still returns `None`.
- `test_unparseable_compound_condition_still_rejected` — `"A AND B"` still
  `None` (proves the fix did not broaden into a general expression parser).
- `test_billing_engine_conditions_are_now_parseable` — every business-rule
  condition extracted from the real `t_billing_engine.cbl` source now
  parses.
- **`test_critical_regression_billing_engine_produces_real_validation_tests`**
  — the most important regression: asserts `extract_behavioral_tests` on
  the real `t_billing_engine` bundle produces ≥1 test with (a) the real
  condition text `"TAX-OUT-TAX-RATE = 0.00"`, (b) a real expected output
  (`TAX-OUT-TAX-RATE = "7.25"`) on the branch where the condition holds,
  (c) valid source provenance (a real line range in the real file), and
  (d) the firing rule ID recorded — not a placeholder, not fabricated.
- `test_billing_engine_false_branch_is_also_a_legitimate_branch_test` —
  the condition-does-not-hold branch is still a legitimate branch-coverage
  test with correctly *empty* outputs (nothing fires — not fabricated).

## 6. Real-corpus validation

Methodology: same in-place precise-revert-and-restore technique used for
the STEP 9 (COMPUTE/EVALUATE-in-IF) fix — reverted only the exact two
hunks this fix introduced (`conditions.py`, `extractor.py::_evaluate`),
verified the revert reproduces the known `mmim-gen-v5` baseline
(`parse_condition("RATE = 0.00") is None`; VALIDATION_REASONING coverage
== 30/45, matching the documented v5 figure exactly), ran the "before"
measurement, restored the fix (`parse_condition("RATE = 0.00")` returns
the correct `Comparison` again), ran the "after" measurement. Both
measurements ran a full 45-source corpus scan via
`build_analysis_bundle` + `extract_behavioral_tests` +
`build_mmim_dataset(strict_eligibility=True)`, executed from a copy of the
measurement script placed at the repository root (avoiding the
`sys.path[0]` resolution pitfall documented in the STEP 9 audit).

VALIDATION_REASONING coverage: **30/45 (66.7%) → 34/45 (75.6%)**. Zero
sources lost coverage (strictly additive).

| source | rule_count (business_rules, unchanged) | conditions parseable before → after | suite tests before → after | tests with real evidence before → after |
|---|---:|---:|---:|---:|
| `t_billing_engine` | 1 | 0 → 1 | 0 → 2 | 0 → 1 |
| `t_daily_trans_report` | 2 | 0 → 2 | 0 → 3 | 0 → 3 |
| `t_payroll_file_post` | 1 | 0 → 1 | 0 → 3 | 0 → 1 |
| `t_transitive_fx` | 1 | 0 → 1 | 0 → 2 | 0 → 1 |
| `t_credit_approval` | 11 | 4 → 5 | 6 → 8 | 4 → 5 |
| `t_mortgage_service` | 4 | 3 → 4 | 4 → 6 | 3 → 4 |
| `t_pricing_tier` | 14 | 6 → 7 | 12 → 15 | 5 → 6 |

The first four sources are newly eligible for VALIDATION_REASONING (had
zero derivable tests before); the last three already had ≥1 real test and
gained more from their previously-unparseable decimal conditions. In every
row, `rule_count` (BUSINESS_RULE_EXTRACTION's ground truth) is identical
before and after — confirming the fix changed *only* which already-correct
business rules can be turned into a behavioral test, never the rules
themselves. No other source in the 45-source corpus changed at all.

Spot-verified (not merely counted) for `t_billing_engine`:
`extract_behavioral_tests` on the real bundle now produces 2 tests. The
true-branch test carries condition `"TAX-OUT-TAX-RATE = 0.00"`, expected
output `TAX-OUT-TAX-RATE = "7.25"` (the source's own `MOVE 7.25 TO
TAX-OUT-TAX-RATE`), and `SourceRef(source_id='t_billing_engine',
line_start=37, line_end=38)` — a real line range pointing at the real
`IF TAX-OUT-TAX-RATE = 0.00` / `MOVE 7.25 TO TAX-OUT-TAX-RATE` in
`data/sources/phase6-v2/billing_engine.cbl`. The false-branch test carries
the same real condition and correctly empty outputs (nothing fires).
Similarly spot-checked `t_daily_trans_report`, `t_transitive_fx`, and
`t_payroll_file_post` — every test's `expected_branches[].condition` and
`source_refs` trace to real IF conditions and real line ranges in the
real corpus source, never a placeholder.

Note on the `t_billing_engine` true-branch test: it is `executable=False`
(reason: `"paragraph 1000-INVOKE-TAX-ENGINE has no representation in the
generated Java (never PERFORMed from the entry paragraph)"`) — a separate,
pre-existing, correctly-detected limitation in a different part of the
pipeline (the Java architecture builder's paragraph-reachability
analysis), not a defect in this fix. `strict_eligibility` in
`MMIMDatasetBuilder` only requires `suite.tests` to be non-empty for
VALIDATION_REASONING eligibility (`app/dataset/mmim_builder.py`, "do not
teach zero tests as normal, but a non-empty suite with an honestly
recorded `executable=False`/`inconclusive_reason` is not that") — so
`t_billing_engine` is correctly now eligible, with its non-executability
honestly recorded in the example rather than hidden.

## 7. MMIM dataset regeneration & versioning

`generator_version` incremented deliberately: `mmim-gen-v5` → `mmim-gen-v6`
(`app/dataset/version.py::MMIM_GENERATOR_VERSION_V6`), documented as
touching *only* VALIDATION_REASONING ground truth — no parser, lexer, CFG,
IR, or business-rule-extraction change, so BUSINESS_RULE_EXTRACTION,
DEPENDENCY_REASONING, RISK_CLASSIFICATION, MODERNIZATION_STRATEGY,
TRANSFORMATION_PLANNING, and COBOL_TO_JAVA ground truth are provably
unaffected (confirmed directly: every affected source's `rule_count` is
identical before/after, §6 table). `dataset_version` stays `"mmim-v2"`
(same 45-source corpus, same task taxonomy).

| Metric | mmim-gen-v5 | mmim-gen-v6 (this fix) |
|---|---:|---:|
| Total examples | 345 | 349 |
| Sources | 45/45 | 45/45 |
| VALIDATION_REASONING coverage | 30/45 (66.7%) | 34/45 (75.6%) |
| Train / Validation / Test | 222 / 69 / 54 | 226 / 69 / 54 |
| Benchmark leakage (source/hash/normalized) | 0 | 0 |
| Split leakage errors | 0 | 0 |
| Split leakage warnings | 5 (pre-existing, unrelated) | 5 (same, unchanged) |

Source-grouped split assignment preserved: all 4 newly-eligible sources
(`t_billing_engine`, `t_daily_trans_report`, `t_payroll_file_post`,
`t_transitive_fx`) were already assigned to `train` under `mmim-gen-v5`
(split assignment is a pure function of `(dataset_version, seed,
source_id)`, independent of task eligibility) — confirmed directly against
`data/dataset/mmim-v2/train.jsonl`. `validation`/`test` counts are
unchanged (69/54); the entire `+4` example delta landed in `train`. No
source moved between splits.

`data/dataset/mmim-v2/**` regenerated in place via
`build_mmim_dataset(..., generator_version=MMIM_GENERATOR_VERSION_V6,
strict_eligibility=True)` and `build_instruction_dataset`. `benchmark-v1`
and `data/dataset/mmim-v1/**` untouched (not read or written by this task).

## 8. Tests run

```
python -m pytest tests/behavioral/test_decimal_condition_extraction_fix.py -q   # 25 passed
python -m pytest tests/behavioral/ -q                                           # 82 passed
python -m pytest tests/behavioral/ tests/modernization/ -q                      # 286 passed
python -m pytest tests/dataset/test_mmim_v2_dataset.py tests/dataset/test_instruction_adapter_v2.py -q
                                                                                  # 44 passed
python -m pytest tests/dataset/ tests/behavioral/ tests/modernization/ -q       # 410 passed
python -m pytest tests/ -q   # full-tree baseline: 3730 passed, 12 pre-existing
                              # unrelated failures (tests/ir/test_ir_control_flow.py
                              # x3, tests/parser/test_lexer.py x2,
                              # tests/parser/test_lexer_regression.py x1,
                              # tests/parser/test_procedure_parser.py x4,
                              # tests/parser/test_token_types.py x2 — all
                              # pre-date this task, none touch conditions.py,
                              # extractor.py, or any decimal/numeric-literal
                              # path; unaffected by this fix, out of scope)
python -m black --check app/behavioral/extraction/conditions.py app/behavioral/extraction/extractor.py \
    tests/behavioral/test_decimal_condition_extraction_fix.py app/dataset/version.py \
    tests/dataset/test_mmim_v2_dataset.py tests/dataset/test_instruction_adapter_v2.py
                                                                                  # unchanged
python -m ruff check app/behavioral/extraction/conditions.py app/behavioral/extraction/extractor.py \
    tests/behavioral/test_decimal_condition_extraction_fix.py app/dataset/version.py \
    tests/dataset/test_mmim_v2_dataset.py tests/dataset/test_instruction_adapter_v2.py
                                                                                  # all checks passed
python -m mypy app/behavioral/extraction/conditions.py app/behavioral/extraction/extractor.py \
    app/dataset/version.py --ignore-missing-imports
                                                                                  # no issues, 3 files
```

## 9. Exact files changed

- `app/behavioral/extraction/conditions.py` — the fix (`_NUMERIC`,
  `_COND_RE`, `_numeric_step`, `generate_boundary_values`, `_holds` type
  hints).
- `app/behavioral/extraction/extractor.py` — `_evaluate`'s numeric operand
  conversion (`int` → `Decimal`).
- `app/dataset/version.py` — `MMIM_GENERATOR_VERSION_V6` added.
- `tests/behavioral/test_decimal_condition_extraction_fix.py` — new, 25
  tests.
- `tests/dataset/test_mmim_v2_dataset.py` — version bump (V5→V6), coverage
  count 30→34, new §3e regression tests (`test_decimal_condition_fix_*`,
  3 tests).
- `tests/dataset/test_instruction_adapter_v2.py` — version bump (V5→V6),
  example count 345→349.
- `docs/MMIM_DECIMAL_CONDITION_FIX.md` — this document.
- `docs/MMIM_V2_DATASET_AUDIT.md` — updated separately for the v6
  regeneration (coverage, gates, test counts, final report block).
- `data/dataset/mmim-v2/**` — regenerated in place (`manifest.json`,
  `split_manifest.json`, `leakage_report.json`, `validation_report.json`,
  `all.jsonl`/`train.jsonl`/`validation.jsonl`/`test.jsonl`,
  `instruction/**`).

## 10. New independent gaps (not fixed, out of scope)

- The `_apply_action` ARITH-op branch in `extractor.py` still only computes
  a concrete result when both the accumulator target's literal and the
  input value are integer (`lit.lstrip("-").isdigit()`); a decimal
  accumulator step (e.g. `ADD 0.5 TO WS-TOTAL`) still leaves the result
  implicit rather than computing it. Not touched — this is calculation
  semantics for ADD/SUBTRACT/MULTIPLY/DIVIDE actions, not condition
  extraction, and was explicitly out of scope ("do not modify... business
  rule extraction").
- The PERFORM UNTIL body-loop unsupported-statement-in-scope defect
  identified in `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §8 remains unfixed
  (out of scope for both that task and this one).
