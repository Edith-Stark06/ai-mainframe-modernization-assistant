# MMIM — FILE SECTION support: `FD` records become Java fields (Stage 27, `mmim-gen-v24`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v23` -> `mmim-gen-v24`

The audit doc's own `NEXT STEP` line named this first, repeatedly, across many prior cycles: "Declare
FILE SECTION fields as Java fields — the sole remaining reason the same 4 sources fail `javac`, and its
own cycle." This document is the investigation and the fix.

## 1. Scope, established from the docs and current implementation

`docs/MMIM_JAVA_IF_EMISSION_FIX.md` §7 (task #stage12) first named "FILE SECTION fields are not declared
as Java fields (`fdTxVal`, `fdAcctBal`, …), so conditions and moves over them fail `javac` with `cannot
find symbol`." Every stage since then that touched these 4 sources (`t_batch_acct_update`,
`t_daily_trans_report`, `t_inventory_extract`, `t_payroll_file_post`) reconfirmed the same gap was still
the sole reason they stayed uncompilable, most recently `docs/MMIM_NEGATED_COMPARISON_FIX.md` §4/§8 and
`docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md` §7/§8. The parser's own docstrings (`data_parser.py`,
`program_parser.py`) already said explicitly: "FILE SECTION... are unsupported syntax, not silently
assumed empty" — a deliberate placeholder, not an oversight.

## 2. Reproduction and root cause (measured before editing)

`DataDivisionParser.parse()` recognised a `FILE SECTION.` header only to skip it whole
(`_skip_unsupported_section`, `SYN101 "unsupported DATA DIVISION section 'FILE'; its contents are
skipped"`), consuming every token up to the next section/division header without building any AST for
what it skipped. An `FD`'s record fields (`FD-ACCT-BAL`, `FD-OVERDRAFT-PROT`, ...) therefore never entered
the AST, the symbol table (built purely by walking the AST — `app/parser/semantic/visitors
.py::traverse_program`), or the generated Java class. Every real PROCEDURE DIVISION reference to one of
those fields became a bare, undeclared Java identifier: `if (fdAcctBal < 500.00)` with no `fdAcctBal`
field anywhere in the class — a guaranteed `javac "cannot find symbol"` failure, confirmed directly on the
pre-fix isolated baseline for `t_batch_acct_update.cbl`.

## 3. Why this is safely, narrowly fixable (not confounded)

Unlike Stage 26's rejected candidate (a subscripted comparison operand, which needed `OCCURS`/Java-array
modelling this backend does not have), an `FD` record's grammar is **identical** to a WORKING-STORAGE `01`
record's: `FD <file-name>. 01 <record-name>. 05 <field> PIC ... .` — the exact same
`ElementaryItemNode`/`GroupItemNode`/`ConditionNameNode` shapes `_parse_data_items` already parses fully
and correctly for WORKING-STORAGE. Directly confirmed before writing any fix: all 4 real corpus sources'
`FD` blocks are minimal (no `LABEL RECORDS`/`BLOCK CONTAINS`/`RECORD CONTAINS` clauses), and every
downstream consumer of a `VariableSymbol` — symbol collection, Java field construction
(`build_fields_from_symbols`), condition-type awareness (`build_condition_context`) — is already generic
over *any* registered symbol, not WORKING-STORAGE-specific. The only genuinely new code needed was the
FILE SECTION *container* parsing and one extra branch in the shared AST traversal; no existing consumer
needed a FILE-SECTION-specific code path at all.

## 4. The fix (`app/parser/syntax/data_parser.py` — the only new parsing logic)

New `FileSectionNode`/`FileDescriptionNode` AST types (`app/parser/ast/file_section.py`), added as an
optional `DataDivisionNode.file_section` field alongside the existing `working_storage`. Two new parser
methods:

* `_parse_file_section` — consumes `FILE SECTION .`, then loops over `FD` entries (matched by lexeme:
  `FD` is not a reserved lexer word, same as `FILE`/`LINKAGE`/etc. already weren't) until the next section
  header, division, or EOF.
* `_parse_file_description` — consumes `FD <file-name>`, tolerates and skips any clause up to the
  terminating period (none appear in the corpus, but a real `FD` may carry them), then calls
  **the existing** `_parse_data_items` for the record's items.

`_parse_data_items` itself gained three keyword-only parameters (`extra_stop_words`, `context`,
`section_label`), all defaulted to reproduce WORKING-STORAGE's exact prior behaviour byte-for-byte — the
FILE SECTION caller passes `extra_stop_words={"FD"}` (so the item list correctly stops at the *next* `FD`,
a plain `TokenType.IDENTIFIER` that no other check catches) and `context=RecoveryContext.FILE_SECTION`
(a new enum member) so malformed-item diagnostics are correctly labelled.

`app/parser/semantic/visitors.py::traverse_program` gained one new branch, walking `data_div.file_section`
exactly like it already walks `working_storage` — calling `item.accept(visitor)` for each record's items,
so every existing `SemanticVisitor` (symbol collector, type checker, reference resolver, validation)
automatically sees FD fields as ordinary data items, with zero changes to any of those visitor classes.
`app/parser/syntax/program_parser.py::_collect_condition_names` and
`app/backend/java/condition_context.py::build_condition_names` were extended in the same minimal way, for
consistency (no real corpus `FD` record declares a level-88 today, so this has zero corpus impact, but
leaving it WORKING-STORAGE-only would have been a latent inconsistency next to the fix's own stated goal).

**No change to `app/backend/java/generator.py`, `app/parser/semantic/symbol_collector.py`, or
`app/backend/java/statement_emitter.py`** — confirmed directly: `build_fields_from_symbols` iterates
`semantic_ctx.symbol_table.all_symbols()`, a flat list with no section provenance, and
`build_condition_context` derives `field_types` from that same generic field list. Both already worked
correctly the moment FD items became registered symbols.

## 5. Corpus exposure and impact (measured before and after editing)

Exactly **4 sources** have a FILE SECTION (`t_batch_acct_update`, `t_daily_trans_report`,
`t_inventory_extract`, `t_payroll_file_post`) — confirmed by direct source-text search, matching the
already-known "4 sources fail `javac`" set exactly. Full 45-source fingerprint (AST/IR hash, CFG summary,
dependencies, business-rule count, risk count/categories, strategy hash, syntax-diagnostic codes, Java
hash, `javac`; isolated pre-fix baseline vs current tree, via the same `build_analysis_bundle` the real
dataset builder uses):

* **41 of 45 sources: substantively identical** on every dimension except the raw serialized-AST hash,
  which moves for *all* 45 — a confirmed, expected, cosmetic artifact of `DataDivisionNode` gaining a new
  `file_section` field that serializes as `null` for every program that has none (`app/analysis/serializers
  /_common.py::serialize_value` walks every dataclass field generically). Not a content change.
* **4 sources, all-positive changes:**
  - `SYN101` disappears (the section now parses); `javac` **41/45 -> 45/45**.
  - Java text grows with the FD fields as real, typed private fields.
  - `t_daily_trans_report`'s `FD-TX-SUSPICIOUS = 'Y'` — and `t_batch_acct_update`'s
    `FD-OVERDRAFT-PROT = 'Y'` — now correctly reach Stage 24's `_cobolEquals` translation instead of
    identity `==`, because `ConditionContext` now knows their type. `t_daily_trans_report` joins
    `t_batch_acct_update`/`t_policy_redefines` as a helper user (2 -> 3 sources).
  - `n_risks` drops 6 -> 4: the `DATA_COMPLEXITY` risk and one of two `UNSUPPORTED_SYNTAX` risk-category
    entries are both driven directly off `SYN101`/data-item diagnostic codes
    (`app/modernization/risk/analyzer.py::_detect_data_complexity`/`_detect_unsupported_syntax` — read and
    confirmed directly, not guessed) and correctly disappear once it is gone.
  - `t_payroll_file_post`'s `AnalysisResult.success` flips `False -> True` (its FD-field references were
    its last remaining semantic-diagnostic source).
  - AST/dependency/business-rule *counts* for these 4 are unchanged — confirmed directly, not assumed.
* The shared, non-corpus `workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl` fixture's
  own 3-`FD` FILE SECTION also now parses: its `SYN101` is replaced by 3 previously-latent `SYN200`
  "`COMP-3` clause... not represented" warnings on 3 of its fields (net 47 -> 49 diagnostics), and 8 of its
  10 semantic `SEM003 "undefined variable"` diagnostics disappear (the FD fields they were correctly
  flagging are now declared) — see `tests/parser/test_unsupported_syntax_reporting.py
  ::test_complex_fixture_surfaces_49_syntax_diagnostics` for the full accounting.

## 6. Verification

**Isolated pre-fix proof.** A fresh byte-copy of the post-Stage-26 tree was made (`.venv`/caches excluded)
by copying the current (already-fixed) tree and precisely reverting every Stage 27 edit back out of the
copy (7 files; the new `file_section.py` module deleted from the copy). `app.__file__` confirmed to
resolve inside the copy; the reverted copy confirmed to reproduce the exact pre-fix `SYN101`/undeclared-
field Java output byte-for-byte before any new test was added. All **22** new tests
(`tests/parser/test_file_section_fields.py`) then fail to even *collect* on that tree
(`ModuleNotFoundError: No module named 'app.parser.ast.file_section'`) — i.e., all 22 fail pre-fix, all 22
pass post-fix.

**Real corpus `javac`** (actual `javac 25.0.3`, not simulated): all 45 sources compiled individually;
**45/45**, up from 41/45. All 4 previously-failing sources compile cleanly on their own.

**Test suites**, compared against the documented baseline (4671 passed / 12 pre-existing failures at the
start of this cycle):

* `tests/parser` — 9 failed (exactly the 9 documented pre-existing parser-area baseline failures) once 3
  directly-affected tests were updated (§7).
* `tests/dataset`, `tests/backend`, `tests/analysis`, `tests/java_modernization` — fully clean once the
  regenerated dataset's cascading test updates were applied (§8).
* `tests/ir` — 3 failed (exactly the documented `test_ir_control_flow.py` baseline failures).
* Full suite — see the final report for the exact combined totals.

`black`, `ruff check`, and `mypy` (`app/` in full — 357 source files) are clean. No conflict markers
anywhere in the repo.

## 7. Existing tests updated outside the dataset suite (direct, traceable consequences)

* `tests/parser/test_token_type_regressions.py::test_unsupported_section_is_reported_explicitly` — its
  chosen "unsupported section" example was `FILE SECTION`, which is no longer one; swapped to `LINKAGE
  SECTION` (a still-genuinely-unsupported section, matching the sibling test right below it), keeping the
  same test intent.
* `tests/parser/test_unsupported_syntax_reporting.py
  ::test_complex_fixture_surfaces_47_syntax_diagnostics` -> `..._49_...` — the shared fixture's own FILE
  SECTION now parses; see §5's last bullet for the full accounting.
* `tests/parser/test_figurative_constant_operands.py::test_fixture_diagnostic_total_is_unchanged_by_this_fix`
  (Stage 26's own test) — its pinned total (47) moved to 49 for this stage's unrelated reason; docstring
  updated to attribute the move correctly and keep proving Stage 26's own, still-true claim (nothing
  changes at lines 256/263).
* `tests/backend/test_cobol_comparison_semantics.py
  ::test_real_corpus_only_these_two_sources_use_the_helper` -> `..._three_sources_...` —
  `t_daily_trans_report` joins as a third `_cobolEquals` user (§5).
* `tests/backend/test_java_if_emission_fix.py
  ::test_real_daily_trans_report_java_is_balanced_and_carries_both_terms` — its expected header regex
  updated from `fdTxSuspicious == "..."` to `_cobolEquals(fdTxSuspicious, "...")`.
* `tests/backend/test_negated_comparison_java.py
  ::test_real_source_whole_class_does_not_compile_for_an_unrelated_reason` ->
  `..._whole_class_now_compiles` — the gap it documented (and named "resolved in a future stage" nowhere,
  since it wasn't yet planned) is this stage's own fix; rewritten to assert successful compilation.

## 8. Dataset regeneration (`mmim-gen-v24`) and its cascading test updates

Generated content genuinely changes for the 4 affected sources (§5), so `MMIM_GENERATOR_VERSION_V24` was
added and the dataset regenerated. Two independent live regenerations
(`seed=42`, `strict_eligibility=True`) are byte-identical to each other. 351 examples, 226/71/54 splits,
leakage unchanged (`ok=True`, 0 errors, 5 warnings) — all confirmed, not assumed.

`tests/dataset/test_mmim_v2_dataset.py` (the cumulative, every-cycle regression file) needed 24 updates,
every one a direct, mechanically-traceable consequence of §5's real changes, never a weakening:

* 5 `MMIM_GENERATOR_VERSION_V23` references -> `V24`.
* 12 hardcoded `compiles == 41` regression guards (scattered across nearly every earlier stage's own "did
  not change counts elsewhere" test) -> `45`, since every one of them now legitimately observes the current,
  post-Stage-27 dataset.
* 13 occurrences of `{"deterministic": 345, "executable_verified": 2, "reference": 4}` ->
  `{"deterministic": 349, "executable_verified": 2}` — `GroundTruthStatus` is `DETERMINISTIC` if a
  source's `COBOL_TO_JAVA` example compiles, else `REFERENCE` (`app/dataset/mmim_builder.py::_cobol_to_java`,
  read and confirmed directly); all 4 affected sources' single `COBOL_TO_JAVA` example flips accordingly.
* `t_batch_acct_update`'s and `t_daily_trans_report`'s specific expected Java text updated from identity
  `==` to `_cobolEquals(...)` in 2 tests (§5's `_cobolEquals` finding).
* The corpus-wide `(initialized, uninitialized)` field-count pin, `(275, 126)` -> `(275, 152)`, in 4 tests:
  26 new FD fields across the 4 sources, none with a `VALUE` clause in this corpus, so all 26 are
  uninitialized; the initialized count is unaffected.
* The corpus-wide `syntax_diagnostic_count` sum (`PROGRAM_UNDERSTANDING` task), `134 -> 130`: the 4
  `SYN101` removals.
* `test_negated_comparison_helper_used_by_exactly_two_sources`/
  `test_text_comparison_helper_appears_only_where_it_is_used` (Stage 25/24's own tests): both `_cobolEquals`
  user lists gain `t_daily_trans_report`.
* `test_text_comparison_leaves_unknown_typed_and_numeric_comparisons_alone` (Stage 24's own test): its
  premise ("FILE SECTION fields are unknown-type") is exactly what this stage resolves; rewritten to assert
  the opposite, and its "2 remaining unknown-typed comparisons" regex count moved to 0.
* `test_java_fix_did_not_change_compile_flags_or_ground_truth_status`/
  `test_java_literal_fix_three_sources_newly_compile` (Stage 12/13's own tests): their "still not
  compilable: undeclared FILE SECTION fields" loops rewritten to assert the opposite, since that is
  precisely the gap those tests' own comments already correctly named as the reason.

No test was weakened to make it pass; every changed assertion is a demonstrated, directly-verified
consequence of the fix traced in §5, and every updated docstring names the resolving stage.

## 9. Remaining gaps (reproduced or previously documented, NOT fixed)

1. Leading `NOT` before an entire condition, subscripted comparison operands — unchanged
   (`docs/MMIM_NEGATED_COMPARISON_FIX.md` §8 items 1-2).
2. The Java figurative-constant-value-translation gap (`docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md` §6)
   — unrelated, still unfixed.
3. `PERFORM VARYING` entirely unsupported (`docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md` §8) — unrelated
   to this stage's fix; still blocks `table_indexed.cbl`'s own `OCCURS`-table loop.
4. FD clauses other than the file-name (`LABEL RECORDS ARE`, `BLOCK CONTAINS`, `RECORD CONTAINS`, ...) are
   tolerated and skipped, not modelled — none appear in the real corpus (verified directly), so this is a
   reproduced-but-inapplicable gap, not a corpus defect.
5. `OCCURS`/`REDEFINES` on a FILE SECTION or WORKING-STORAGE item is still not represented in the AST
   (`SYN200`, pre-existing, unrelated to this stage).
6. `MOVE 09`, `DataModelElement.initial_value`, `GO TO … DEPENDING ON`, `COMPUTE`, `COMP`/`COMP-3` — as
   recorded before.

## 10. Files

`app/parser/ast/file_section.py` (new), `app/parser/ast/data.py`, `app/parser/diagnostics/recovery.py`,
`app/parser/syntax/data_parser.py`, `app/parser/syntax/program_parser.py`, `app/parser/semantic/visitors.py`,
`app/backend/java/condition_context.py`, `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V24`),
`tests/parser/test_file_section_fields.py` (new, 22 tests), `tests/parser/test_token_type_regressions.py`,
`tests/parser/test_unsupported_syntax_reporting.py`, `tests/parser/test_figurative_constant_operands.py`,
`tests/backend/test_cobol_comparison_semantics.py`, `tests/backend/test_java_if_emission_fix.py`,
`tests/backend/test_negated_comparison_java.py`, `tests/dataset/test_mmim_v2_dataset.py` (24 updates),
`data/dataset/mmim-v2/**` (regenerated v24, including `instruction/`), `docs/MMIM_FILE_SECTION_FIELDS_FIX.md`
(this file), `docs/MMIM_V2_DATASET_AUDIT.md`.
