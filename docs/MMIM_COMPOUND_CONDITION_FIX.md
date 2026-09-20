# STEP 14 — Compound AND/OR Condition Extraction Fix

## 1. Read before editing

- `docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md` — the prior task: `parse_condition`
  now recognises `IS-TRUE`/`IS-FALSE`. Named compound `AND`/`OR` conditions as the
  dominant remaining blocker (§10).
- `docs/MMIM_V2_DATASET_AUDIT.md` — dataset state before this task: 350 examples,
  35/45 (77.8%) VALIDATION_REASONING coverage, `mmim-gen-v8`.
- `app/behavioral/extraction/conditions.py`, `app/behavioral/extraction/extractor.py`
  and the existing `tests/behavioral/` suite (conventions taken from
  `test_level88_condition_operator_fix.py` and `test_decimal_condition_extraction_fix.py`).
- `app/modernization/business_rules/extractor.py` (`_walk`, `_emit_branch`,
  `_render_condition`, `_fmt_comparison`, `_condition_variables`) — the upstream
  producer of every condition string. Read-only for this task.

## 2. Audit (done before any code changed)

All 8 real business rules of `t_condition_names_88` were printed:

| Rule | Condition string (verbatim) | Shape |
|---|---|---|
| BR-001 | `TX-VALID-KIND IS-FALSE TX-VALID-KIND` | single term |
| BR-002 | `(NOT (TX-VALID-KIND IS-FALSE TX-VALID-KIND)) AND (TX-DEPOSIT IS-TRUE TX-DEPOSIT)` | AND, 2 terms |
| BR-003 | `(NOT (TX-VALID-KIND IS-FALSE …)) AND (NOT (TX-DEPOSIT IS-TRUE …)) AND (TX-WITHDRAWAL IS-TRUE …)` | AND, 3 terms |
| BR-004 | `… AND (NOT (TX-WITHDRAWAL IS-TRUE …)) AND (NOT (TX-TRANSFER IS-TRUE …))` | AND, 4 terms |
| BR-005 | `… AND (NOT (TX-WITHDRAWAL IS-TRUE …)) AND (TX-TRANSFER IS-TRUE …)` | AND, 4 terms |
| BR-006 | `(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND (NOT (TX-AMOUNT > 1000.00))` | AND, 2 terms |
| BR-007 | `(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND (TX-AMOUNT > 1000.00)` | AND, 2 terms |
| BR-008 | `ONLINE-CHANNEL IS-TRUE ONLINE-CHANNEL` | single term |

**Finding: the compound structure is *flattened into a string*.** It is not genuinely
lost upstream and not partially represented elsewhere. Each parenthesised part is,
once its wrapping parens are stripped, exactly a string `parse_condition` can already
parse. `parse_condition` returned `None` only because the string as a whole is not a
single term. No parser change was needed and none was made.

`app/modernization/business_rules/extractor.py` was searched for any path that emits
`" OR "`: there is none. Every real compound in the corpus is `AND`-joined, produced by
nested-`IF`/`ELSE` cascades accumulating enclosing context. **`OR` support is therefore
exercised only by synthetic inputs** (no real corpus source can currently reach it).

## 3. Fix design

`parse_condition` is untouched. Three additions in `conditions.py`, all *composing*
the existing single-term semantics:

- `parse_compound_condition(text) -> CompoundComparison | None` — finds top-level
  parenthesised parts (`_COMPOUND_PART_RE`, one level of nesting: exactly the
  `NOT (...)` wrapper case, deliberately not a balanced-parens matcher), requires a
  single uniform connector (`AND` or `OR`, never mixed), and calls `parse_condition`
  on each part. No expression grammar, no precedence. Anything else returns `None`.
- `generate_compound_boundary_values(compound, known_values_by_variable, alias_of)` —
  candidate values per variable are the union of each term's own
  `generate_boundary_values` output. Cases are found by searching the (capped at 4096)
  product of those candidates for an assignment whose per-term truth vector is the one
  a case needs, so every case is verified by `evaluate_term` before it is returned.
  - **AND** (evidence satisfies the conjunction): one all-true case, plus one case with
    exactly one term false (the first term for which that is realisable).
  - **OR** (evidence satisfies an appropriate branch): one all-false case, plus one
    case per term where that term alone holds.
  - A case that cannot be realised is dropped, never fabricated. A condition-name term
    with no declared domain makes the whole compound underivable (`[]`).
- `evaluate_compound` / `evaluate_term` — one canonical truth evaluator, shared by the
  single-term caller (`extractor._evaluate` now delegates to it) and by compounds.

`extractor.py` gains a second pass in `extract_behavioral_tests` for rules the
single-term pass did not handle, plus `_build_compound_tests` (mirrors the single-term
loop: same executability checks and error/category handling; `inputs` holds one
`InputValue` per distinct underlying variable) and `_collect_condition_name_parents`.

### 3.1 Correctness problem found and fixed during verification

The first implementation treated every condition-name as its own variable. Checking
the generated evidence against the real COBOL showed that is impossible for this
source: `TX-DEPOSIT`, `TX-WITHDRAWAL`, `TX-TRANSFER`, `TX-FEE` and `TX-VALID-KIND` are
all level-88 conditions on the **one** item `TX-TYPE-CODE`
(`data/sources/phase6-v2/condition_names_88.cbl` lines 8-12), and `PHYSICAL-BRANCH` /
`ONLINE-CHANNEL` share `CHANNEL-ORIGIN`. Inputs such as `TX-VALID-KIND='D'` together
with `TX-WITHDRAWAL='W'`, or `TX-DEPOSIT='D'` with `TX-VALID-KIND='OTHER'`, cannot
occur in real COBOL.

Fix: `_collect_condition_name_parents` maps each level-88 name to its parent (the
nearest preceding non-88 item in the flat WORKING-STORAGE list) and compound evidence
assigns the *parent*. Cases that would require contradictory values for one storage
location are dropped by the search. The same verification also protects terms that
reference one variable twice (`(X > 100) AND (X < 200)`), which a naive
one-value-per-term assignment would have silently overwritten. Measured on the corpus:
before the change 0 of 102 non-88 compound cases were internally inconsistent (the
overwrite happened to be right), so the 12 non-88 examples that changed are
different-but-valid value choices; the material change is the level-88 aliasing.

The single-term (STEP 13) tests keep their condition-name-keyed inputs; changing that
would alter STEP 13 ground truth and is out of scope.

### 3.2 What was preserved

- `parse_condition`, `_COND_RE`, `_CONDITION_NAME_RE`: unchanged. `RATE = 0.00`,
  `AMOUNT > 100`, `TX-DEPOSIT IS-TRUE`, `TX-VALID-KIND IS-FALSE` parse and generate
  exactly as before (regression tests below).
- No parser, AST, or business-rule-layer code was touched.
- The four named-unrelated gaps (`NOT =`, `PERFORM UNTIL` recovery, decimal
  accumulator arithmetic, strategy-analyzer rationale) were not touched.

## 4. Real-corpus validation — `t_condition_names_88`

Evidence for all six compound rules, checked against the COBOL. `TX-TYPE-CODE` /
`CHANNEL-ORIGIN` are the real data items assigned; provenance (`source_refs`) traces to
the real lines.

| Rule | Connector | Taken | Assigned input | Expected output | Source lines | Matches COBOL |
|---|---|---|---|---|---|---|
| BR-002 | AND | true | `TX-TYPE-CODE='D'` | `OUTCOME-ACTION='CREDIT-ACCOUNT'` | 38-39 | yes |
| BR-002 | AND | false | `TX-TYPE-CODE='W'` | none | — | yes (deposit false) |
| BR-003 | AND | true | `TX-TYPE-CODE='W'` | `OUTCOME-ACTION='DEBIT-ACCOUNT'` | 41-42 | yes |
| BR-003 | AND | false | `TX-TYPE-CODE='T'` | none | — | yes |
| BR-004 | AND | true | `TX-TYPE-CODE='F'` | `OUTCOME-ACTION='FEE-ASSESSMENT'` | 44-47 | yes |
| BR-004 | AND | false | `TX-TYPE-CODE='OTHER'` | none | — | yes (rejected by BR-001) |
| BR-005 | AND | true | `TX-TYPE-CODE='T'` | `OUTCOME-ACTION='XFER-ACCOUNT'` | 44-45 | yes |
| BR-005 | AND | false | `TX-TYPE-CODE='F'` | none | — | yes |
| BR-006 | AND | true | `CHANNEL-ORIGIN='BRN'`, `TX-AMOUNT=999.99` | `FEES-LEVIED='0.00'` | 55-58 | **see §6.2** |
| BR-006 | AND | false | `CHANNEL-ORIGIN='OTHER'`, `TX-AMOUNT=999.99` | none | — | yes |
| BR-007 | AND | true | `CHANNEL-ORIGIN='BRN'`, `TX-AMOUNT=1000.01` | `FEES-LEVIED='5.00'` | 55-56 | **see §6.2** |
| BR-007 | AND | false | `CHANNEL-ORIGIN='OTHER'`, `TX-AMOUNT=1000.01` | none | — | yes |

Total tests for the source: 9 → 21 (the 9 STEP 13 tests are unchanged). All six
compound rules are `AND`; none is `OR`. `test_real_corpus_every_compound_case_reverifies_against_its_own_condition`
independently re-evaluates all 12 compound cases against their own condition using the
real declared domains and the parent map.

## 5. Corpus-wide blast radius (measured, not assumed)

A before/after scan over all 45 sources (compound parsing disabled vs enabled) found
**17 sources** change, not only the task's named primary target — many sources' nested-IF
cascade rules were previously dropped entirely:

| Source | Tests before → after |
|---|---:|
| `t_account_eligibility` | 2 → 16 |
| `t_account_validate` | 2 → 6 |
| `t_batch_acct_update` | 0 → 4 (**newly eligible**) |
| `t_condition_names_88` | 9 → 21 |
| `t_credit_approval` | 8 → 20 |
| `t_credit_limit` | 3 → 7 |
| `t_customer_record` | 2 → 6 |
| `t_discount_tier` | 3 → 7 |
| `t_fraud_pipeline` | 6 → 10 |
| `t_grade_letter` | 3 → 9 |
| `t_late_fee` | 3 → 7 |
| `t_loan_underwrite` | 5 → 13 |
| `t_payroll_deduct` | 10 → 18 |
| `t_policy_redefines` | 7 → 11 |
| `t_pricing_tier` | 15 → 29 |
| `t_tax_withhold` | 4 → 8 |
| `t_vacation_accrual` | 3 → 7 |

Sources with ≥1 test: 35 → 36. `t_batch_acct_update` was spot-checked against
`data/sources/phase6-v2/batch_acct_update.cbl` lines 57-61: balance `< 500.00` with
overdraft protection `'Y'` yields fee 12.50, otherwise 35.00; the boundary values
`499.99` / `500.00` come from `Decimal` stepping. Its tests are all
`executable=False` (the source has unsupported `FILE SECTION`/`OPEN`/`READ`), which
does not affect VALIDATION_REASONING eligibility (`suite.tests` non-empty).

## 6. New independent gaps (reproduced, documented, not fixed)

### 6.1 `_condition_variables` treats the operator word as a variable

`app/modernization/business_rules/extractor.py::_condition_variables` tokenises a
`NOT`-wrapped term's rendered text and includes `IS-FALSE`/`IS-TRUE` in
`rule["variables"]["reads"/"conditions"]`. Not consumed anywhere under
`app/behavioral/extraction/`, so it does not affect this task.

### 6.2 `_walk` never reads `IfStatementNode.extra_conditions` (corpus-wide, affects evidence)

> **Resolved** in `mmim-gen-v10` by `docs/MMIM_EXTRA_CONDITIONS_FIX.md`: the business-rule
> engine now renders every term (BR-006/BR-007 regain `TX-WITHDRAWAL`, and the 5 real `OR`
> conditions reach the behavioral extractor). The text below is the original finding, kept
> as the historical record; the same fix doc reports the newly found IR/Java/dependency
> analogue of this gap.

The parser correctly captures an `IF`'s own `AND`/`OR` terms in
`IfStatementNode.extra_conditions`, but `business_rules/extractor.py::_walk` never
consumes them, so they are absent from every rendered condition string. An AST scan of
the 45 sources found **11 IF statements in 8 sources** with non-empty
`extra_conditions`, including `OR` terms:

`t_account_eligibility` (67), `t_condition_names_88` (54), `t_credit_approval` (37 `OR`,
40, 43), `t_daily_trans_report` (56 `OR`), `t_insurance_claim` (37, 40 `OR`),
`t_mortgage_service` (50), `t_payment_gateway` (46 `OR`), `t_pricing_tier` (69 `OR`).

Concrete consequence in this task's primary target: line 54 is
`IF PHYSICAL-BRANCH AND TX-WITHDRAWAL`; the `AND TX-WITHDRAWAL` conjunct is missing from
BR-006/BR-007's condition. The evidence for those two rules is faithful to the string the
upstream engine emitted but **not to the COBOL**: with the default
`TX-TYPE-CODE='D'`, `CHANNEL-ORIGIN='BRN'` does not levy a fee. The two `taken=true`
BR-006/BR-007 tests are therefore incomplete ground truth, and single-term tests derived
from the other seven sources' truncated conditions share the same weakness (pre-existing,
not introduced here). This is the top recommended next task: consume `extra_conditions`
in `_walk`/`_render_condition`. It changes BUSINESS_RULE_EXTRACTION ground truth for 8
sources, so it must be its own regeneration cycle. It also means `OR` conditions would
start reaching the compound path for real.

## 7. Dataset regeneration

`generator_version` `mmim-gen-v8` → `mmim-gen-v9`
(`app/dataset/version.py::MMIM_GENERATOR_VERSION_V9`). `dataset_version` stays
`"mmim-v2"`. Touches VALIDATION_REASONING only; business-rule counts confirmed unchanged
(`t_condition_names_88` 8, `t_batch_acct_update` 2, `t_account_eligibility` 8,
`t_credit_approval` 11, `t_pricing_tier` 14).

| Metric | mmim-gen-v8 | mmim-gen-v9 |
|---|---:|---:|
| Total examples | 350 | 351 |
| Sources | 45/45 | 45/45 |
| VALIDATION_REASONING coverage | 35/45 (77.8%) | 36/45 (80.0%) |
| Train / Validation / Test | 226 / 70 / 54 | 226 / 71 / 54 |
| Benchmark leakage | 0 | 0 |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |

`t_batch_acct_update` was already assigned to `validation`; no source moved
(`split_manifest.json` source→split map unchanged). Regeneration is byte-deterministic:
two independent full regenerations produced identical `all.jsonl`, split files,
`manifest.json`, `split_manifest.json`, `leakage_report.json` and all
`instruction/*` files (only `validation_report.json`'s recorded output path differs).
`benchmark-v1` and `mmim-v1` are untouched (`git status` clean for both).

The largest instruction example is now 13 814 estimated tokens
(`t_pricing_tier` VALIDATION_REASONING, 29 tests) — see the correction in
`docs/MMIM_V2_DATASET_AUDIT.md` §15.

## 8. Remaining VALIDATION_REASONING skips (9)

`fx_perform_until`, `fx_simple_proc`, `t_dead_code_audit`, `t_temp_convert` (no derivable
conditional/loop logic in reachable code); `t_goto_spaghetti` (`GO TO`);
`t_inventory_extract` (`FILE SECTION`/`OPEN`/`READ`); `t_order_hierarchy`,
`t_table_indexed` (`OCCURS`); `t_inventory_reorder` (variable-vs-variable comparison).

## 9. Tests

`tests/behavioral/test_compound_condition_extraction_fix.py` — 37 tests, covering the 9
required categories: existing single-term unchanged; two-term AND (parse, conjunction,
one-false case); two-term OR (parse, branch semantics, all-false case — synthetic,
documented as such because no real source reaches it); mixed condition-name +
comparison; `IS-TRUE` and `IS-FALSE` inside a compound (incl. `NOT`-folded);
multi-value level-88 inside a compound using the declared domain; false/negative
branches from the real corpus; malformed/unsupported compounds (unbalanced parens, mixed
`AND`/`OR`, unsupported connector, missing connector, single part, unparseable part) fail
safely; plus shared-parent aliasing, same-variable terms, contradictory conjunctions
(no case emitted), and undeclared condition-name (no case emitted). The real-corpus
end-to-end regression covers all six compound rules, provenance, parent-keyed inputs,
independent re-evaluation, and determinism.

`tests/dataset/test_mmim_v2_dataset.py` — version bump to V9, 36/45 coverage, new §3h
tests (newly-covered source, all six compound rules present, no regression against the
v8 source set, business-rule counts unchanged); two STEP 13 tests that pinned exact
counts (`==35`, `test_count==9`) were relaxed to membership/subset checks because the
pinned values legitimately moved. `tests/dataset/test_instruction_adapter_v2.py` —
version bump, 350 → 351 examples.

## 10. Exact files changed

- `app/behavioral/extraction/conditions.py` — `CompoundComparison`,
  `parse_compound_condition`, `generate_compound_boundary_values`, `evaluate_compound`,
  `evaluate_term` (shared), `__all__`.
- `app/behavioral/extraction/extractor.py` — compound second pass,
  `_build_compound_tests`, `_collect_condition_name_parents`; `_evaluate` delegates to
  `evaluate_term`.
- `app/dataset/version.py` — `MMIM_GENERATOR_VERSION_V9`.
- `tests/behavioral/test_compound_condition_extraction_fix.py` — new.
- `tests/dataset/test_mmim_v2_dataset.py`, `tests/dataset/test_instruction_adapter_v2.py`.
- `docs/MMIM_COMPOUND_CONDITION_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`.
- `data/dataset/mmim-v2/**` — regenerated in place.
