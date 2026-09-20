# `extra_conditions` consumption in the business-rule engine

Branch `feat/mmim-extra-conditions`. Follows `docs/MMIM_COMPOUND_CONDITION_FIX.md` §6.2,
which reported the defect and recommended this task. `generator_version`
`mmim-gen-v9` -> `mmim-gen-v10`; `dataset_version` stays `mmim-v2`.

Path note: the task brief named `app/business_rules/extractor.py`; the module is
`app/modernization/business_rules/extractor.py` (tests live in
`tests/modernization/business_rules/`).

## 1. Audit — the prior report was reproduced, not assumed

`IfStatementNode` (`app/parser/ast/statements.py`) holds the *first* comparison in
`condition_left/operator/right` and every further term in
`extra_conditions: tuple[ConditionTerm, ...]`, each `ConditionTerm` carrying
`connector` (`"AND"`/`"OR"`, the keyword that joined it to the **previous** term),
`left`, `operator`, `right`. The parser (`_parse_if_statement`) builds a flat
left-to-right list. Facts read from the code, not inferred:

| Question | Answer |
|---|---|
| Term ordering preserved? | Yes — source order. |
| Connector per term? | Yes, on each extra term; the first term has none. |
| Precedence? | Documented on `ConditionTerm`: `AND` binds tighter than `OR` (`A AND B OR C` = `(A AND B) OR C`); a consumer must group. |
| Parentheses? | Not represented. `A AND (B OR C)` is a `ParserError`, never a flat list. |
| Level-88 terms? | Same shape: `(name, "IS-TRUE"/"IS-FALSE", name)`. |
| What did the engine read? | `_walk` read only `condition_left/operator/right` and never `extra_conditions` (the module docstring even claimed compound conditions were "not representable in the current AST" — stale since the parser fix). |
| What does downstream expect? | `parse_condition` (single term) and `parse_compound_condition` (one level of parenthesised parts, one uniform `AND` **or** `OR`; `NOT (...)` wrapper only around a single term). |

Real-corpus inventory (AST scan of all 45 sources, 132 IF nodes) — exactly the prior
audit's figures: **11 IFs in 8 sources, 5 with `OR`**. Rule condition the engine
emitted for each, before the fix:

| Source:line | Real COBOL condition | Emitted before |
|---|---|---|
| t_account_eligibility:67 | `EXISTING-ACCOUNTS >= 3 AND ANNUAL-INCOME > 75000.00` | `EXISTING-ACCOUNTS >= 3` |
| t_condition_names_88:54 | `PHYSICAL-BRANCH AND TX-WITHDRAWAL` | `PHYSICAL-BRANCH IS-TRUE …` (no `TX-WITHDRAWAL`) |
| t_credit_approval:37 | `BANKRUPTCY-FLAG = 'Y' OR CREDIT-SCORE < 580` | `BANKRUPTCY-FLAG = 'Y'` |
| t_credit_approval:40 | `CREDIT-SCORE >= 740 AND DTI-PERCENTAGE <= 35.00` | `CREDIT-SCORE >= 740` |
| t_credit_approval:43 | `CREDIT-SCORE >= 660 AND DTI-PERCENTAGE <= 45.00` | `CREDIT-SCORE >= 660` |
| t_daily_trans_report:56 | `FD-TX-VAL > 10000.00 OR FD-TX-SUSPICIOUS = 'Y'` | `FD-TX-VAL > 10000.00` |
| t_insurance_claim:37 | `POLICE-REPORT-FILED = 'N' AND CLAIM-AMOUNT > 5000.00` | `POLICE-REPORT-FILED = 'N'` |
| t_insurance_claim:40 | `DRIVER-AGE < 21 OR DRIVER-AGE > 75` | `DRIVER-AGE < 21` |
| t_mortgage_service:50 | `OUT-CREDIT-STATUS = 'OK' AND IN-LTV-RATIO <= 80.00` | `OUT-CREDIT-STATUS = 'OK'` |
| t_payment_gateway:46 | `AUTH-OUT-RESP-CODE = ' ' OR AUTH-OUT-RESP-CODE = '000'` | `AUTH-OUT-RESP-CODE = ' '` |
| t_pricing_tier:69 | `PAYMENT-METHOD = 'ACH' OR PAYMENT-METHOD = 'WIRE'` | `PAYMENT-METHOD = 'ACH'` |

An `OR` dropped this way is not merely incomplete: it *narrows* the rule, and the ELSE
branch was negated over the first term alone (`NOT (PAYMENT-METHOD = 'ACH')` claims
`WIRE` payments take the else path). The dropped terms also vanished from the
*enclosing context* of every nested rule (e.g. `t_credit_approval` BR-003..BR-005).

## 2. The fix (only `app/modernization/business_rules/extractor.py`)

* `_condition_runs(stmt)` — first term + `extra_conditions` grouped into OR-separated
  runs of AND-connected terms (the parser's precedence). Any incomplete term (empty
  operand/operator, unknown connector) returns `None`: the level is then treated exactly
  as the old "cannot represent reliably" case — nested IFs are still walked, but **no
  partial condition is emitted**.
* A small frozen `_Level` replaces the ad-hoc `(left, op, right)` / `("NOT","",text)`
  context tuples. One `IF` = one level (so `confidence` and the "reconstructed from N
  nested IF comparison(s)" evidence keep their meaning). A level carries the conjunct
  texts it contributes, its positive comparison leaves, and, for ELSE levels, the inner
  text of each `NOT (...)`.
  * THEN, pure-AND chain -> further conjuncts: `(A) AND (B) AND (C)` (flat, so it composes
    with enclosing conditions and stays consumable downstream).
  * THEN, chain containing `OR` -> one explicit group: `(A) OR (B)`;
    `((A) AND (B)) OR (C)` makes precedence visible.
  * ELSE -> exact De Morgan complement, one `NOT (...)` conjunct per AND-run:
    else of `A OR B` = `(NOT (A)) AND (NOT (B))`; else of `A AND B` = `NOT ((A) AND (B))`.
* Single-term IFs render byte-identically (`WS-A > 5`, `NOT (WS-A > 5)`).
* One extra evidence line records `extra_conditions` (`"IF condition has N additional
  AND/OR term(s) (extra_conditions): OR"`). No parser, AST, behavioral or dataset-builder
  code changed. The module docstring's stale "not representable" claim was corrected.

Deliberately **not** changed: `_condition_variables`' tokenisation of `NOT (...)` text
(known gap: the `IS-FALSE` operator word is read as a variable) — new ELSE levels go
through the same path as before, so they inherit it identically; positive levels read
their leaves directly and are exact.

## 3. Real-corpus before/after (isolated trees)

The earlier methodology mistake (import state making "before" and "after" the same
code) was avoided: "before" ran in a **subprocess against a byte-copy of the pre-fix
`app/` tree** (plus read-only `data/sources`, `data/benchmark`, `tests/fixtures`,
`tests/golden`) with `PYTHONPATH` pointing at it; "after" ran against the repository.
The snapshot script records `app.__file__` and the extractor's SHA-256 and the
comparison asserts they differ (before `b626ebe90384…`, after `9c5f54188235…`). The
baseline is the pre-fix *working tree*, not `origin/main`, because `origin/main` lacks
all the accumulated parser/dataset work and would conflate everything.

| Measure (45 sources) | Result |
|---|---|
| Sources changed | **8 / 45** — exactly the 8 audited sources |
| Parser diagnostics (count and codes) | 0 sources differ |
| Procedure statement nodes | 0 sources differ |
| Business-rule counts | 0 sources differ (157 -> 157) |
| Rule conditions changed | 18 |
| Rule categories changed | 2 (below) |
| Rule confidences changed | 0 |
| Sources with >= 1 behavioral test | 36 -> 36 |
| Behavioral tests | 275 -> 274 (below) |

Important condition changes (all 18 are in the 8 sources; full list in the audit
script output, summarised):

* **t_condition_names_88 BR-006/BR-007 regain the missing term:**
  `(PHYSICAL-BRANCH IS-TRUE …) AND (TX-WITHDRAWAL IS-TRUE TX-WITHDRAWAL) AND (TX-AMOUNT > 1000.00)`
  and the `NOT (TX-AMOUNT > 1000.00)` variant.
* **The 5 real `OR` cases** are now `(a) OR (b)` (credit_approval:37, daily_trans_report:56,
  insurance_claim:40, payment_gateway:46, pricing_tier:69), with their ELSE branches
  `(NOT (a)) AND (NOT (b))` (daily_trans_report, pricing_tier).
* Enclosing contexts: `t_credit_approval` BR-003..BR-005 now include
  `NOT (CREDIT-SCORE < 580)` and the DTI terms; `t_account_eligibility` BR-006..BR-008
  include `ANNUAL-INCOME > 75000.00`.
* `t_mortgage_service`: the two rules swap IDs (BR-003 <-> BR-004) — IDs are assigned
  after sorting by condition text, so a changed condition can reorder them.
* Categories: `t_credit_approval` BR-002 and `t_mortgage_service` (`OK AND LTV <= 80.00`)
  move `CONDITIONAL_VALIDATION` -> `LIMIT_CHECK`, because the category comes from the
  *last* positive comparison, which is now the compound IF's last term
  (`CREDIT-SCORE < 580`, `IN-LTV-RATIO <= 80.00` — relational against a numeric
  literal). A consequence of representing the whole condition, not an intended
  reclassification.

### Downstream (behavioral extraction)

| Source | Tests before -> after | Why |
|---|---|---|
| t_account_eligibility | 16 -> 12 | 2 rules (BR-007/BR-008) now carry `NOT ((a) AND (b))` — not consumable, dropped (they previously produced tests from an *incomplete* condition) |
| t_credit_approval | 20 -> 17 | same, BR-004/BR-005; the `OR` rule gains a true/false/true set |
| t_daily_trans_report | 3 -> 5 | OR rule and its ELSE now testable |
| t_payment_gateway | 4 -> 5 | OR rule |
| t_pricing_tier | 29 -> 32 | OR rule + ELSE |
| t_condition_names_88, t_insurance_claim, t_mortgage_service | count unchanged, content changed | BR-006/BR-007 now include `TX-WITHDRAWAL`; insurance OR rule |

Real `OR` evidence checked against the COBOL (`PAYMENT-METHOD = 'ACH' OR 'WIRE'`:
`ACH`/`WIRE` -> discount 2.50, other value -> nothing; `BANKRUPTCY-FLAG = 'Y' OR
CREDIT-SCORE < 580`: `('Y','580')` and `('OTHER','579')` both `HIGH`, `('OTHER','580')`
not taken; `FD-TX-VAL > 10000.00 OR FD-TX-SUSPICIOUS = 'Y'`: each branch alone fires,
neither does not). The BR-006/BR-007 fee tests now assign `TX-TYPE-CODE='W'` (required
by the source's `IF PHYSICAL-BRANCH AND TX-WITHDRAWAL`), so they finally reproduce the
COBOL — the caveat recorded in `MMIM_COMPOUND_CONDITION_FIX.md` §6.2 is resolved.

**Remaining limitation, surfaced (not introduced) by this fix:** the ELSE branch of an
AND-compound IF is rendered `NOT ((a) AND (b))`, a nested group that
`parse_compound_condition` (one level, uniform connector) does not model, so the 5 rules
listed above (t_account_eligibility BR-007/BR-008, t_credit_approval BR-004/BR-005,
t_mortgage_service BR-004 after the ID swap) yield **no** behavioral test. They fail
safely (`parse_condition` and `parse_compound_condition` both return `None`; pinned by
`test_negated_conjunction_is_not_consumable_and_fails_safely`). Making them testable
means extending the behavioral compound parser to mixed/nested connectors — a separate
task.

## 4. Tests

* `tests/modernization/business_rules/test_extra_conditions_extraction_fix.py` — 40
  tests: unchanged single-term/nested behaviour; AND; OR; else of AND / OR / mixed;
  three-term ordering; `AND`-over-`OR` precedence; flattening and grouping inside an
  enclosing condition; level-88 `IS-TRUE`/`IS-FALSE` terms in a compound; variables and
  confidence; 6 fail-safe cases (incomplete terms, unknown connector); consumability by
  `parse_condition`/`parse_compound_condition`; and real-corpus tests through the real
  pipeline (5 real ORs, real ANDs, real ELSE-of-OR, cn88 BR-006/BR-007 exact strings,
  cn88 fee evidence with `TX-TYPE-CODE='W'`, real OR evidence from declared values only,
  and an AST-driven per-source check that no real `extra_conditions` term is dropped).
  **Run against the pre-fix extractor (isolated tree) 36 of 40 fail**; the 4 that pass are
  the "behaviour unchanged" guards plus the AST-driven check for `t_condition_names_88`
  (its term text already appeared in *other* rules, so BR-006/BR-007 has its own exact
  test).
* `tests/modernization/test_intelligence_negative.py::test_condition_is_not_fabricated_beyond_the_ast`
  — **changed, not weakened.** It encoded the obsolete premise "the parser cannot
  represent `A AND B` on one IF; any `AND` must come from nesting (confidence 0.75)".
  The parser now represents it, so the old assertion was exactly the bug. It now asserts
  the exact condition `(WS-A >= 18) AND (WS-B = 'X')` with confidence 1.0 and, for a
  plain IF, that no conjunct appears.
* `tests/dataset/test_mmim_v2_dataset.py` — version pins V9 -> V10 and a new §3i
  (6 tests: real ORs in the ground truth, BR-006/BR-007, rule counts unchanged,
  OR outcomes both reach VALIDATION_REASONING, cn88 fee evidence, coverage 36/45).
  `test_instruction_adapter_v2.py` — version bump.

## 5. Dataset regeneration (`mmim-gen-v10`)

`app/dataset/version.py::MMIM_GENERATOR_VERSION_V10`, following the existing
`v2..v9` convention: bump when a deterministic pipeline change alters ground truth.
Unlike v9 (behavioral extractor only) this is an **upstream** change, so it touches
BUSINESS_RULE_EXTRACTION and every task quoting a rule condition.

| | mmim-gen-v9 | mmim-gen-v10 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 |
| VALIDATION_REASONING coverage | 36/45 | 36/45 |
| Skipped | 9 | 9 |
| Source->split assignment | — | identical |
| Benchmark leakage | 0 | 0 |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |
| Max instruction example (tokens) | 13 814 | 15 010 |

**39 examples changed** (all in the 8 sources): BUSINESS_RULE_EXTRACTION 8,
MODERNIZATION_STRATEGY 8, RISK_CLASSIFICATION 7, TRANSFORMATION_PLANNING 8,
VALIDATION_REASONING 8. The strategy/risk/architecture changes are rule conditions
quoted in evidence text plus derived IDs/content hashes (e.g. `BR-001: (FD-TX-VAL >
10000.00) OR (FD-TX-SUSPICIOUS = 'Y')`). PROGRAM_UNDERSTANDING, DEPENDENCY_REASONING and
COBOL_TO_JAVA are untouched (see §6 for why that is itself a finding). Two independent
full regenerations are byte-identical (`all.jsonl`, the three split files, manifest,
split_manifest, leakage_report, all instruction files; `validation_report.json` differs
only in its recorded output path). `benchmark-v1` and `mmim-v1` are untouched.

## 6. New independent gaps (reproduced, documented, NOT fixed)

> **Resolved in `mmim-gen-v11`** by `docs/MMIM_EXTRA_CONDITIONS_DOWNSTREAM_FIX.md`: the IR builder,
> dependency analyzer, CFG label and the legacy extractor now consume `extra_conditions`, and the
> Java emitter emits every term. **Correction to the text below:** it says `WIRE`, `580` and
> `SUSPICIOUS` are absent from the generated Java because the terms were dropped. That was
> incomplete — those IFs are also kept out of whole-program Java by two separate, pre-existing
> backend limits (PERFORM'd paragraphs are `BE009` stubs; COBOL's `=` is rejected as an
> unsupported operator). See that document, §4.

**The IR builder / Java backend and the dependency analyzer also ignore
`extra_conditions`.** Reproduced on a synthetic source and on real sources:

* `IF WS-A > 5 OR WS-B = 2` generates `if (wsA > 5) {` — the `OR WS-B = 2` term is gone
  from the Java, so the generated program has different semantics.
* No dependency edge is recorded for `WS-B`.
* Real corpus: `WIRE` (pricing_tier), `580` (credit_approval) and `SUSPICIOUS`
  (daily_trans_report) do not appear anywhere in the generated Java or dependency edges.
  It affects the same 8 sources and therefore COBOL_TO_JAVA and DEPENDENCY_REASONING
  ground truth.
* The legacy `app/analysis/rules/extractor.py` likewise reads only the first triple.

This was discovered, not caused, by this task and sits outside the business-rule engine
boundary the task set; fixing it would change COBOL_TO_JAVA/DEPENDENCY_REASONING ground
truth for those 8 sources and needs its own cycle (a `mmim-gen-v11`).

The ELSE-of-AND consumability limitation in §3 is a direct consequence of this fix and
is reported there rather than here. The named unrelated gaps (`NOT =`, `PERFORM UNTIL`
recovery, decimal accumulator arithmetic, strategy rationale, `_condition_variables`
treating `IS-FALSE` as a variable) were not touched.

## 7. Exact files changed (this task)

* `app/modernization/business_rules/extractor.py`
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V10`)
* `tests/modernization/business_rules/test_extra_conditions_extraction_fix.py` (new)
* `tests/modernization/test_intelligence_negative.py`
* `tests/dataset/test_mmim_v2_dataset.py`, `tests/dataset/test_instruction_adapter_v2.py`
* `docs/MMIM_EXTRA_CONDITIONS_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
  `docs/MMIM_COMPOUND_CONDITION_FIX.md` (resolution note on §6.2)
* `data/dataset/mmim-v2/**` (regenerated)
