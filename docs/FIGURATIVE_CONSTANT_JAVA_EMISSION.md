# Java translation of figurative-constant comparison operands (Stage 31)

No dataset impact; `MMIM_GENERATOR_VERSION` unchanged (see §5).

## 1. Summary

A manual end-to-end conversion test compiled a realistic COBOL program containing `IF WS-BALANCE < ZEROS`
and found the generated Java was `if (wsBalance < zeros) {` — `zeros` an undeclared field, a guaranteed
`javac` "cannot find symbol" failure. `docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md` (Stage 26) had already
found and documented this exact gap in its own §6 ("Independent defect found, NOT fixed") without a concrete
reproduction: the Java backend has no figurative-constant-to-Java-value translation at all, for any of the
nine canonical spellings (`ZERO`, `ZEROS`, `ZEROES`, `SPACE`, `SPACES`, `HIGH-VALUE`, `HIGH-VALUES`,
`LOW-VALUE`, `LOW-VALUES`), in a comparison operand. This stage fixes it, for the two spelling families that
have a provably correct Java equivalent.

## 2. Baseline (before any edit)

- Full suite, re-verified directly rather than assumed: `4863 passed, 0 failed` (`stage31_baseline_pytest.txt`) — matches the
  Stage 30 acceptance figure exactly.
- Every one of the 9 canonical spellings, used as a comparison operand against a `WS-BALANCE`/`WS-COUNT`/`WS-NAME`
  field (ordering, equality, inequality, left-hand and right-hand position), reproduced with the real pipeline
  (`AnalysisService`): `result.success = True`, 0 syntax/semantic/backend diagnostics, and Java containing an
  undeclared lowerCamelCase identifier reference. All 9 failed `javac` with "cannot find symbol". `VALUE`-clause
  and level-88 figurative-constant translation were already correct (unaffected baseline).

## 3. Root cause

`app.backend.java.control_flow_emitter._build_condition` translates both operands of a comparison with
`app.backend.java.statement_emitter._translate_operand`, whose fallback rule treats anything that is not a
quoted literal or a numeric literal as a "COBOL identifier" and lowerCamelCases it — exactly the rule a real
field name goes through, with no way to tell a figurative constant apart. Nothing downstream of the parser
(IR, business-rule extraction, the Java backend) distinguishes a figurative-constant operand's `TokenType`
from an ordinary identifier's — both are carried as a plain `str` — so the information needed ("this token is
`ZEROS`, not a field called `ZEROS`") was available only during parsing and was discarded before it could
reach the backend.

## 4. Investigation findings

1. **Parser representation, re-verified directly** (lexer + parser, not assumed from Stage 26): only `ZEROS`
   and `SPACES` lex as `TokenType.KEYWORD` (`app/parser/lexer/keywords.py::KEYWORDS`); the other 7 spellings
   lex as `TokenType.IDENTIFIER`. All 9 parse successfully as an `IF`-condition operand, in both positions,
   with the parser's own `_FIGURATIVE_CONSTANT_KEYWORDS` allowlist (Stage 26) unchanged. `IF X = MOVE`
   (an ordinary reserved word) is still rejected (`SYN005`) — confirmed directly, not assumed.
2. **An existing, precedented, type-aware operand translator already existed for `VALUE` clauses**:
   `app.backend.java.value_initializer.translate_value_literal(literal, java_type)` already turns
   `ZERO`/`ZEROS`/`ZEROES` into `"0"`/`"0.0"` and `SPACE`/`SPACES` into `'""'`, for `int`/`double`/`String`
   respectively — and is already reused, unmodified, by `translate_condition_name` for level-88 values. This
   stage reuses that same function for comparison operands instead of duplicating its logic.
3. **Field-type information already reaches condition translation**: `app.backend.java.condition_context
   .ConditionContext.field_types` (built from the real generated field list) is already threaded through
   `emit_if`/`emit_perform_until`/`_build_condition` for the Stage 24 text-comparison and Stage 23 level-88
   features. No new plumbing was needed — the fix is what those functions do with a figurative-constant
   operand, not a new field-type channel.
4. **`HIGH-VALUE(S)`/`LOW-VALUE(S)` have no existing Java representation anywhere in the codebase.**
   `translate_value_literal` returns `None` for them today even in a `VALUE` clause — a field declared
   `VALUE HIGH-VALUES` is simply left uninitialized. There is no established sentinel (a `0xFF`-fill
   convention, a `Long.MAX_VALUE` mapping, anything) to reuse. Inventing one would be exactly the kind of
   unproven Java semantics this task was explicitly told not to invent, so they are deliberately left
   untranslated — confirmed unchanged by test (`test_high_values_and_low_values_are_never_translated`,
   `test_emit_if_high_values_still_undeclared`).
5. **`PERFORM UNTIL` shares the exact same `_build_condition` function** as `IF`, so the fix applies to both
   without separate code (verified directly: `test_emit_perform_until_zeros`).

## 5. Fix

`app/backend/java/value_initializer.py`: `_ZERO_FIGURATIVES`/`_SPACE_FIGURATIVES` renamed to public
`ZERO_FIGURATIVES`/`SPACE_FIGURATIVES` (added to `__all__`) so the condition-translation layer can reuse the
exact same spelling sets instead of maintaining a second copy. No behavior change.

`app/backend/java/condition_context.py` (new):

- `translate_figurative_operand(operand, other, java_operator, context)` — translates a figurative-constant
  `operand` into a Java literal, typed from `other`'s already-known Java type (a declared field's type, a
  quoted literal → `String`, a bare numeric literal → `int`/`double` from its own shape). `ZERO`-family only
  translates against a numeric `other`; `SPACE`-family only translates against a `String` `other`, and only
  for an equality operator (matching `_cobolEquals`'s own equality-only restriction — COBOL text *ordering* is
  collating-sequence semantics this backend does not model, so it is left exactly as before). Reuses
  `translate_value_literal` — no new literal-formatting logic. Returns `None` (no context, wrong type family,
  unprovable other-operand type) exactly when the old, uncompilable translation should be kept unchanged.
- `_is_text` now also returns `True` for a `SPACE`/`SPACES` operand unconditionally, so `IF WS-NAME = SPACES`
  is recognised by `translate_comparison` as a COBOL text comparison and correctly routed through
  `_cobolEquals`, not raw `==`.
- `translate_comparison`'s `_cobolEquals(...)` argument construction now translates a `SPACE`/`SPACES`
  operand to `""` before falling back to the generic operand translator — otherwise the correctly-selected
  `_cobolEquals` call would itself contain an undeclared `spaces` reference.

`app/backend/java/control_flow_emitter.py`: `_build_condition`'s final fallback tries
`translate_figurative_operand` for each operand before `_translate_operand`; `_build_if_condition`/
`emit_perform_until` needed no change (they already call `_build_condition`).

**Left untouched, deliberately**: `_translate_operand` itself (used by `MOVE`/`DISPLAY`/`ADD`/`CALL`), so a
figurative constant outside a comparison condition (`MOVE ZEROS TO X`) is unaffected — out of scope; every
example in the objective, and the whole motivating defect, is about `IF`/`PERFORM UNTIL` conditions.
`translate_condition_name` (level-88) is untouched — it already had correct figurative-constant handling via
`translate_value_literal` directly.

## 6. Tests

- `tests/backend/test_figurative_constant_java_emission.py` (new, 31 tests): `translate_figurative_operand`
  unit coverage (every required case — `ZERO`/`ZEROS`/`ZEROES` against `int`/`double`, `SPACE`/`SPACES`
  against `String`, left-hand operand, equality and ordering, type mismatch declines, unknown-type declines,
  bare-literal other operand, `HIGH-VALUE(S)`/`LOW-VALUE(S)` never translated, no-context unchanged, an
  ordinary identifier never mistaken for one); `emit_if`/`emit_perform_until` end-to-end translation
  (including the exact `IF WS-BALANCE < ZEROS` acceptance case); the `IF X = MOVE` regression guard; level-88
  and `VALUE`-clause regression checks; the manual test's exact end-to-end scenario compiled and *executed*
  with real `javac`/`java`; a corpus-safety re-verification (search, not the fingerprint — see §7).
- `tests/backend/test_cobol_comparison_semantics.py`: 1 assertion updated
  (`("WS-CODE", "==", "SPACES")` moved from "everything else unchanged" to "known text equality", since it is
  now correctly translated) plus 3 new parametrized cases (`!=`, left-hand, `SPACE`) added to the same list it
  already had a home in, and 2 new `ZERO`-family-against-text cases added to the unchanged-list to keep that
  boundary explicit.
- `tests/parser/test_figurative_constant_operands.py`: `test_figurative_constant_java_translation_gap_is_symmetric_not_new`
  renamed and rewritten as `test_figurative_constant_java_translation_gap_remains_for_type_mismatches` — its
  premise (every spelling produces the same undeclared-identifier shape) is no longer true for `SPACES`
  against a `String` field after this stage; the test now pins what *is* still true (`ZERO`/`ZEROS` against a
  mismatched `String` field) and directly demonstrates the `SPACES` case is no longer symmetric with it.
  Nothing weakened or deleted — both the old and new facts are asserted.

## 7. Corpus impact — zero, empirically proven

Re-verified for this stage, not assumed from Stage 26: `test_no_corpus_source_has_a_figurative_constant_comparison_operand`
searches all 45 training-corpus sources (code columns, comments excluded) for a figurative constant
immediately after a comparison operator, across every spelling — zero occurrences.

Beyond the text search, an isolated before/after fingerprint of the full deterministic pipeline
(`build_analysis_bundle`) was run for all 45 sources, each tree in its own subprocess (`app.__file__` checked
to resolve inside the respective tree): **AST, IR, CFG, dependencies, business rules, risks, strategy,
coverage, syntax diagnostics, paragraphs, generated Java, `success`, and `javac` result are byte-identical
for all 45 sources, before and after this stage.** `javac`: 45/45 both before and after.

Because no corpus source is observably affected, `MMIM_GENERATOR_VERSION` is **not bumped** and
`data/dataset/mmim-v2` is **not regenerated** — the same outcome, for the same reason, as Stage 26 and
Stage 22.

## 8. Verification

- New test file: 31 passed.
- `tests/backend/test_figurative_constant_java_emission.py` +
  `tests/backend/test_cobol_comparison_semantics.py` + `tests/parser/test_figurative_constant_operands.py`:
  169 passed, 0 failed.
- Full suite (isolated, on the fixed tree): see final report for the exact total; baseline was independently
  re-run and confirmed `4863 passed, 0 failed` before any edit.
- `black --check .`, `ruff check .`, `mypy app`: clean on the 3 changed source files and 3 changed/new test
  files (also re-run against the whole repo).
- `git diff --check`: clean. No conflict markers anywhere in the repo.

## 9. Remaining gaps (deliberately not addressed)

- `HIGH-VALUE(S)`/`LOW-VALUE(S)` as a comparison operand remain untranslated (§4 item 4) — no established Java
  representation exists anywhere in this codebase to reuse.
- Figurative constants outside a comparison condition (`MOVE ZEROS TO WS-X`, `DISPLAY SPACES`, a `CALL`
  argument) are unaffected — `_translate_operand` itself is untouched, out of scope for this stage.
- `SPACE`/`SPACES` in an *ordering* comparison (`IF WS-NAME < SPACES`) is not translated — matches
  `_cobolEquals`'s own equality-only restriction; COBOL text ordering is collating-sequence semantics this
  backend does not model for any text comparison, figurative or not.
- **Decimal/`double` precision drift is a separate, pre-existing, unrelated issue** (the same manual test that
  found this stage's defect also found that COBOL `PICTURE`-driven fixed-point truncation is not reproduced
  by this backend's `double`-typed fields across chained `MULTIPLY`/`DIVIDE` operations — e.g. an expected
  COBOL `1743.63` came out as `1743.6350208333333` in Java). This stage does not touch numeric representation,
  `BigDecimal`, or `PICTURE`-scale truncation/rounding in any way — recorded here as a follow-up finding only,
  not investigated or fixed.

## 10. Files

`app/backend/java/value_initializer.py`, `app/backend/java/condition_context.py`,
`app/backend/java/control_flow_emitter.py`, `tests/backend/test_figurative_constant_java_emission.py` (new),
`tests/backend/test_cobol_comparison_semantics.py`, `tests/parser/test_figurative_constant_operands.py`,
`docs/FIGURATIVE_CONSTANT_JAVA_EMISSION.md` (this file). No dataset file, no `docs/MMIM_V2_DATASET_AUDIT.md`
entry (no dataset change to record), and no other source file changed.
