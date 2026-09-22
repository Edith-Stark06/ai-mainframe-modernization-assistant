# COBOL DISPLAY formatting for PICTURE fields (Stage 31, `mmim-gen-v26`)

## 1. Summary

`DISPLAY` of an elementary COBOL data item used to print whatever Java naturally prints for the field's
flat Java type (`int`/`double`/`String`) — not what COBOL DISPLAY actually prints, which is the item's
full declared storage, implicitly zero-padded (numeric) or space-padded (alphanumeric) to its PICTURE
width. `DISPLAY WS-COUNT` for `PIC 9(3)` value `5` printed `5`, not `005`.

The Java backend now reproduces this for the unsigned, unedited cases (**Category A**, this stage's only
scope):

* Unsigned `PIC 9(n)` → zero-padded to *n* digits.
* Unsigned `PIC 9(n)V9(m)` → zero-padded to *n+m* digits; the assumed decimal point (`V`) is never printed.
* `PIC X(n)` → space-padded (right-justified) to *n* characters.

Everything else — signed `PIC S9`, the `SIGN` clause, edited PICTUREs (`Z`, `$`, `,`, literal `.`), `DISPLAY`
of a whole group item, numeric overflow/truncation, multi-operand `DISPLAY`, `OCCURS`/subscripts — is
**out of scope** and deliberately unformatted, exactly as before.

## 2. Baseline (before any edit)

HEAD `64cb099` ("feat: translate figurative constants in Java conditions"). Full suite: **4897 passed**, 0
failed. 45/45 corpus sources compile with `javac`.

## 3. Root cause

The COBOL→Java pipeline is:

```
ElementaryItemNode.picture (raw string)
  → TypeBuilder (semantic pass 4)         parses "9(7)V99" into NumericType(digits=9, decimal_places=2)
  → VariableSymbol.cobol_type             the structured type -- digits/decimal_places/signed/length
  → map_cobol_type                        collapses to a flat Java type string: "int" / "double" / "String"
  → JavaField                             carried only the flat type string -- width/scale discarded HERE
  → IRDisplay.operand (a bare string)     no type information at all
  → emit_display / emit_statement         no context parameter -- nothing to format with even if it wanted to
  → System.out.println(x);
```

`map_cobol_type` is correct and unchanged: Java has no fixed-width numeric/string type, so a flat `int`/
`double`/`String` is the right field type. The gap was that nothing downstream of it kept the *width* the
mapping necessarily threw away, and `emit_display` had no parameter to receive it even if it existed.

## 4. Implementation design

No parser, AST, or IR change. Four files in `app/backend/java/`:

1. **`field_model.py`** — `JavaField` gained four optional attributes, populated once and never
   recomputed: `digits: int | None`, `decimal_places: int` (default `0`), `signed: bool` (default
   `False`), `length: int | None`. All default to "not a formattable elementary item" (a group, or a
   symbol with no resolved type), so every existing keyword-constructed `JavaField` in the codebase and
   its tests is unaffected.
2. **`generator.py`** (`build_fields_from_symbols`) — copies these straight from `VariableSymbol.cobol_type`
   (`NumericType.digits`/`.decimal_places`/`.signed`, `AlphanumericType.length`) at the one point that
   already has both the symbol and its type, via the same lazy `app.parser.semantic.types` import
   `type_mapper.map_cobol_type` already uses to keep the backend/parser layering. A `GroupType` symbol
   (also mapped to Java `String`) gets none of these — it has no PICTURE of its own.
3. **`condition_context.py`** — `ConditionContext` (the existing "what does the emitter know beyond the
   IR" carrier, already threaded through `_collect_statements` → `emit_if`/`emit_perform_until`) gained one
   new field, `fields: Mapping[str, JavaField]` (java name → the full field, alongside the pre-existing
   `field_types: Mapping[str, str]`), populated by `build_condition_context`. A second, parallel context
   type was considered and rejected: one "what do we know about this field" object threaded through the
   pipeline is simpler than two.
4. **`statement_emitter.py`** — `emit_display`/`emit_statement` gained a trailing
   `context: ConditionContext | None = None` parameter, mirroring the exact `context: ConditionContext |
   None = None` contract `emit_if`/`emit_perform_until`/`translate_comparison`/`translate_figurative_operand`
   already use elsewhere in this codebase: **no context → byte-identical pre-#stage31 behavior**. A new
   private helper, `_format_display_operand(operand, java_operand, context)`, does the actual work: it
   declines (returns `java_operand` unchanged) for a literal operand, a field `context` doesn't know
   about, a signed field, or a field with neither `digits` nor `length` set (a group); otherwise it wraps
   the operand in a `String.format(...)` call.
   `generator.py::_collect_statements`'s one regular-statement call site
   (`emit_statement(instr, diagnostics, context=context)`) now passes the context it already built for
   IF/PERFORM UNTIL, so DISPLAY formatting is live on the real production path
   (`generate`/`generate_with_diagnostics`) without needing a fifth call site anywhere.

### Why no `_cobolEquals`-style static helper

The existing `_cobolEquals` package-private helper (`condition_context.py`) exists because COBOL
alphanumeric equality has no one-line Java equivalent. Zero-padding an integer and space-padding a string
*do*: `java.lang.String.format`'s own `%0Nd`/`%-Ns` specifiers are exactly COBOL's own DISPLAY padding
rule, expressed in one expression, with no new Java source needed (`String.format` needs no import). Adding
a bespoke helper here would only add indirection with nothing to reuse it for.

### Generated Java

```java
// PIC 9(3), unsigned                       PIC 9(7)V99, unsigned                          PIC X(4)
System.out.println(String.format("%03d",    System.out.println(String.format("%09d",       System.out.println(String.format("%-4s",
    wsCount));                                  Math.round(wsAmount * 100)));                   wsText));
```

The scale factor (`100` for `decimal_places=2`) is a compile-time literal computed from the field's own
declared `decimal_places`, not a runtime `Math.pow` call — smaller, faster, and exact. `Math.round` returns
`long`; `%0Nd` accepts it directly. An integer format specifier is what guarantees the decimal point is
never printed — not a special case, a structural property of using `%d` instead of `%f`.

## 5. Tests added/changed

* **`tests/backend/test_display_formatting.py`** (new, 34 tests): numeric zero-padding (`PIC 9(3)`
  short/zero/full-width, `PIC 9(5)` width), numeric-with-implied-decimal zero-padding (`PIC 9(7)V99`
  small/zero/full-width, `PIC 9V99`, no-decimal-point-ever assertions), alphanumeric space-padding
  (`PIC X(4)` short/exact, `PIC X(6)` SPACES), regressions (signed field unformatted, group-item `DISPLAY`
  out of scope, string/COBOL-literal/numeric-literal operands unformatted, no-context byte-identical
  behavior, an operand `context` doesn't recognize, a field with no resolved type), `_format_display_operand`
  direct unit tests, `build_fields_from_symbols` PICTURE-metadata propagation (all four `CobolType`
  subtypes), and `generate_with_diagnostics` end-to-end integration (real `VariableSymbol` →
  `build_fields_from_symbols` → `generate_with_diagnostics`).
* **`tests/golden/move_display.java`**, **`tests/golden/combined_program.java`** — regenerated via
  `UPDATE_GOLDEN=1` (the test runner's own supported mechanism): `MSG` (`PIC X(20)`) and `COUNTER`
  (`PIC 9(2)`) are now displayed formatted.
* **`tests/integration/test_pipeline.py`** — `test_move_display_pipeline`/`test_combined_program_pipeline`:
  updated the hardcoded expected `System.out.println(...)` line for `WS-COUNT` (`PIC 9(3)`) and `WS-B`
  (`PIC 9(2)`) to their new formatted form.
* **`tests/regression/fixtures/arithmetic/add.json`** — `NUM-B` (`PIC 9(4)`) expected construct updated to
  its formatted form.
* **`tests/dataset/test_mmim_v2_dataset.py`** — `MMIM_GENERATOR_VERSION_V25` → `V26` (5 references; the
  historical Stage-30 comment mentioning `mmim-gen-v25` by name is left as the historical marker it is, not
  renamed).

No test was weakened; every changed assertion now encodes the new, genuinely-correct expected Java text
(verified independently against the pipeline's own output, not copied from the failure message).

## 6. Full pytest result

Before this stage's dataset regeneration (code change only): **5 failed, 4926 passed** — the 5 pre-existing
fixtures above that hardcode unformatted DISPLAY text for an unsigned field (a real, expected regression
surfaced by the new feature, not a bug in it). After updating those 5 fixtures/assertions and regenerating
the dataset: **all pass** (final count in the report below).

## 7. Corpus impact (byte-copy of the pre-fix `app/` vs the fixed tree, isolated subprocesses)

Methodology: a `git worktree` at HEAD `64cb099` as the untouched "before" tree, the working tree as
"after", each fingerprinted in its own subprocess (`app.__file__` verified to resolve inside the correct
tree) via `build_analysis_bundle` (AST, IR, CFG, CFG summary, dependencies, business rules, risks,
strategy, coverage, confidence, syntax diagnostics, paragraphs, generated Java) plus a `javac` compile,
for all 45 corpus sources.

**Result:** AST, IR, CFG, CFG summary, dependencies, business rules, risks, strategy, coverage,
confidence, and syntax diagnostics are byte-identical for all 45 sources. `javac` stays **45/45** before
and after. Only `java_backend_output` (generated Java text) changes, for exactly **13 of 45 sources**:
`fx_combined`, `t_credit_limit`, `t_discount_tier`, `t_grade_letter`, `t_interest_accrue`, `t_late_fee`,
`t_loan_balance`, `t_loan_underwrite`, `t_overdraft_fee`, `t_shipping_zone`, `t_stock_alert`,
`t_temp_convert`, `t_vacation_accrual` — each source's `System.out.println(x)` of an unsigned elementary
numeric or alphanumeric field becomes `System.out.println(String.format("<spec>", x))`; `t_loan_underwrite`
has two such DISPLAYs (one `PIC X(12)`, one `PIC 9(2)V99`).

19 sources contain a `DISPLAY` of a variable; 6 of them (`fx_perform_until`, `fx_simple_proc`,
`t_account_validate`, `t_bonus_calc`, `t_payroll_net_pay`, `t_reorder_point`) are unaffected because that
`DISPLAY` sits in a paragraph whose body never reaches generated Java at all — a pre-existing, unrelated
backend gap (confirmed: identical, `println`-free Java before and after this change; the paragraph is
emitted as an empty stub method). Not investigated further — out of this stage's scope.

## 8. `javac` result

**45/45** before and after (identical set of sources compiles both times).

## 9. Manual end-to-end execution

A COBOL program outside the repo (`PIC 9(3)`, `PIC 9(5)`, `PIC 9(7)V99`, `PIC 9V99`, `PIC S9(5)` (regression),
`PIC X(n)` at several widths, `SPACES`, a group item and its individual elementary children, `DISPLAY` of a
whole group item (regression), arithmetic overflow (regression), `ADD`) compiled with `javac` (exit 0) and
ran with `java` (exit 0). Output (excerpted; full program is the `format_repro.cbl` this doc's author used,
not committed):

```
005                 <- PIC 9(3) value 5
000                 <- PIC 9(3) value 0 (ZERO)
999                 <- PIC 9(3) value 999
00007               <- PIC 9(5) value 7
000050000           <- PIC 9(7)V99 value 500.00 (no '.')
000000500           <- PIC 9(7)V99 value 5.00 (no '.')
000000000           <- PIC 9(7)V99 value ZERO (no '.')
005                 <- PIC 9V99 value 0.05
-42                 <- PIC S9(5) value -42 (unchanged -- signed, out of scope)
42                  <- PIC S9(5) value 42 (unchanged)
HIGH VALUE          <- PIC X(12) 'HIGH VALUE' (already 10 chars, +2 trailing spaces)
OK                  <- PIC X(4) 'OK' (+2 trailing spaces)
FULL                <- PIC X(4) 'FULL' (exact width, unchanged)
                    <- PIC X(6) SPACES (6 spaces)
ABCD                <- WS-GROUP-A, PIC X(4), a group's individual elementary child
007                 <- WS-GROUP-B, PIC 9(3), a group's individual elementary child
null                <- DISPLAY of the whole group item (unchanged, pre-existing limitation, out of scope)
1800                <- PIC 9(3) after two ADDs overflow its declared width (unchanged, out of scope)
```

Every Category-A case matches the exact examples in this stage's brief (`005`, `000`, `999`,
`000050000`, `000000500`, `000000000`, `"OK  "`, six-space `SPACES`); every excluded case (signed, group
`DISPLAY`, overflow) is confirmed unchanged.

## 10. Dataset impact and regeneration

Content genuinely changes (13 sources' `COBOL_TO_JAVA` expected Java text), so `MMIM_GENERATOR_VERSION_V26`
was added and `data/dataset/mmim-v2` regenerated (`seed=42`, `dataset_version="mmim-v2"`,
`strict_eligibility=True`; two independent runs byte-identical — see below):

* Genuine content changes (`metadata.generator_version`'s mechanical stamp excluded): exactly **13 of 351**
  examples change — one `COBOL_TO_JAVA` example per affected source, matching §7 exactly. Every other task
  type (`PROGRAM_UNDERSTANDING`, `DEPENDENCY_REASONING`, `BUSINESS_RULE_EXTRACTION`, `RISK_CLASSIFICATION`,
  `MODERNIZATION_STRATEGY`, `TRANSFORMATION_PLANNING`, `VALIDATION_REASONING`) is unaffected — none of them
  embed generated Java text.
* Every one of the 351 examples' `metadata.generator_version` stamp moves `mmim-gen-v25` → `mmim-gen-v26`
  (expected, mechanical — every example carries this field regardless of task type).
* Unchanged: 351 examples, the 226/71/54 split assignment (`split_manifest.json` byte-identical),
  `leakage_report.json` byte-identical, official `validate_dataset` exits clean (`ok: true, error_count: 0`
  for all 351).
* The derived `data/dataset/mmim-v2/instruction/` export (`build_instruction_dataset`) was regenerated too;
  its 26 changed lines (`manifest.json`, `test.jsonl`, `train.jsonl`, `validation.jsonl`) are the same
  mechanical version-stamp/content changes carried through the derived format.
* `data/dataset/mmim-v1` untouched (verified: `test_mmim_v1_directory_untouched` passes unmodified).

### Determinism

Two independent builds (`build_mmim_dataset` called twice into separate output directories with identical
arguments) produce **byte-identical** `all.jsonl`, `train.jsonl`, `instruction/*`, and `validation_report.json`
(the only difference across the two temp runs was the output directory's own path, echoed inside
`validation_report.json`'s `path` field — not dataset content).

### Leakage

`leakage_report.json`: unchanged, `ok: true`, `error_count: 0`. Benchmark-source, benchmark-hash, and
benchmark-normalized-hash overlap tests (`test_zero_benchmark_*`) pass unmodified — this stage touches no
source text, only generated-Java ground truth.

## 11. Remaining gaps (deliberately not addressed)

* Signed `PIC S9`/`SIGN` clause DISPLAY formatting.
* Edited PICTURE clauses (`Z`, `$`, `,`, literal `.`, `+`/`-` insertion, `CR`/`DB`).
* `DISPLAY` of a whole group item (prints Java's own `null`/default for an uninitialized group field --
  pre-existing, confirmed unaffected by this stage).
* Numeric overflow/truncation (a value wider than its declared PICTURE prints wider than declared, not
  truncated — Java's `int`/`double` impose no COBOL-style storage ceiling).
* Multi-operand `DISPLAY`.
* `OCCURS`/subscripted item `DISPLAY`.
* The pre-existing gap in §7 (6 sources whose in-scope `DISPLAY` never reaches generated Java because its
  paragraph is emitted as an empty stub) — unrelated to this stage, not investigated further.
