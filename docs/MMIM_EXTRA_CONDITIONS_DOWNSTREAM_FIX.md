# `extra_conditions` in the IR, Java, dependency, CFG and legacy-rule consumers

Branch `feat/mmim-extra-conditions`. Follows `docs/MMIM_EXTRA_CONDITIONS_FIX.md` §6, which
found that consumers other than the business-rule engine also ignore
`IfStatementNode.extra_conditions`. `generator_version` `mmim-gen-v10` -> `mmim-gen-v11`;
`dataset_version` stays `mmim-v2`.

## 1. Reproduction (before any code changed, in an isolated pre-fix tree)

`IF WS-A > 5 OR WS-B = 2`, run against a byte-copy of the pre-fix `app/` tree
(`PYTHONPATH` pointing at it; `app.__file__` printed):

| Stage | Result |
|---|---|
| Parser AST | `first = WS-A > 5`, `extra_conditions = (ConditionTerm('OR', 'WS-B', '=', '2'),)` — **kept** |
| IR | `IRIf(left='WS-A', operator='>', right='5')` — **lost** in `IRBuilder.build_if_statement` |
| Dependencies | `CONDITION WS-A` only — **lost** in `DependencyAnalyzer.visit_if_statement` |
| Java | `if (wsA > 5) {` — header built from the (already truncated) `IRIf` |
| CFG | decision node `IF WS-A > 5` — label built from the `IRIf` |
| Legacy rules | condition `WS-A > 5`, else `NOT (WS-A > 5)` — **lost** in `visit_if_statement` |

Real corpus, `t_daily_trans_report.cbl:56` (`IF FD-TX-VAL > 10000.00 OR FD-TX-SUSPICIOUS = 'Y'`):
the AST has the OR term; the IR has only `FD-TX-VAL > 10000.00`; no `FD-TX-SUSPICIOUS` dependency
exists anywhere; the generated Java contained `if (fdTxVal > 10000.00) {` — a condition that was
silently *wider than the program's*.

Inventory (AST scan of all 45 sources, 132 IF nodes): **11 IFs, 8 sources, 5 with `OR`** — the
previous audit's figures, reproduced. The 5 real ORs:
`BANKRUPTCY-FLAG = 'Y' OR CREDIT-SCORE < 580` (credit_approval:37),
`FD-TX-VAL > 10000.00 OR FD-TX-SUSPICIOUS = 'Y'` (daily_trans_report:56),
`DRIVER-AGE < 21 OR DRIVER-AGE > 75` (insurance_claim:40),
`AUTH-OUT-RESP-CODE = ' ' OR AUTH-OUT-RESP-CODE = '000'` (payment_gateway:46),
`PAYMENT-METHOD = 'ACH' OR PAYMENT-METHOD = 'WIRE'` (pricing_tier:69).

## 2. Semantics reused, representation added only where the IR had none

The AST contract is unchanged from `MMIM_EXTRA_CONDITIONS_FIX.md` §1: first triple + ordered
`ConditionTerm`s, each with the connector that joined it to the previous term; `AND` binds tighter
than `OR`; no parentheses (`A AND (B OR C)` is a parse error); `NOT` only as the level-88 sentinels
`IS-TRUE`/`IS-FALSE`. The AST is the source of truth: nothing below is derived from rendered text,
and the business-rule engine's output is only the *semantic reference* the results were checked against.

The IR, unlike the AST, had **no** way to carry a second term (`IRIf` is one
`left/operator/right` triple), so a minimal mirror was added — not a competing expression model:

* `IRConditionTerm(connector, left, operator, right)` — the IR image of `ConditionTerm`, operands
  already lowered by `IRBuilder.build_operand`.
* `IRIf.extra_terms: tuple[IRConditionTerm, ...] = ()` plus `IRIf.condition_text()`.
* The generic serializer skips a field flagged `metadata={"omit_if_empty": True}` while empty, so a
  **plain IF serializes byte-identically** (the IR JSON embedded in 39 sources' COBOL_TO_JAVA and
  TRANSFORMATION_PLANNING examples does not change; only compound IFs gain `extra_terms`). This was
  chosen over a new `IRCompoundIf` type because many consumers dispatch on the string `"IRIf"`.

Consumers:

| Consumer | Change |
|---|---|
| `app/ir/builder.py::build_if_statement` | lowers every `extra_conditions` term, in order, into `extra_terms` |
| `app/backend/java/control_flow_emitter.py::emit_if` | `AND` -> `&&`, `OR` -> `\|\|`, in order; an AND-run inside an OR chain is parenthesised (Java's `&&`-over-`\|\|` precedence already matches COBOL's). Each term goes through the existing `_build_condition` validation; **one untranslatable term (unsupported operator, empty operand, unknown connector) skips the whole header with that term's `BE007`** — never an `if` with a term silently missing |
| `app/analysis/dependencies/analyzer.py::visit_if_statement` | inspects both operands of every term via the existing `_maybe_add_operand_dependency` (literals filtered exactly as for the first term) |
| `app/modernization/flow/generator.py::visit_if` | decision label is `IF {condition_text()}` (a plain IF's label is unchanged) |
| `app/analysis/rules/extractor.py` (legacy) | see below |
| `app/behavioral/extraction/loops.py::_run_body` | a compound `IRIf` inside a PERFORM UNTIL body is "not derivable" (`None`) instead of being evaluated on its first term only |

**Legacy business-rule extractor — ACTIVE, fixed.** `app/api/routers/analysis.py` imports it
(`from app.analysis.rules.extractor import BusinessRuleExtractor`) and builds the `/analysis` API's
`business_rules` from it; it is *not* on the MMIM dataset path (that uses
`app.modernization.business_rules`, fixed in `mmim-gen-v10`). Its plain-text style is kept:
terms in source order joined by their connector (`A > 5 OR B = 2`); an OR-containing chain is
parenthesised as one conjunct of the enclosing ` AND ` stack (`(A > 5 OR B = 2)`); a pure-AND chain
is just more conjuncts; the ELSE branch is `NOT (<whole condition>)`. No re-grouping is invented.

Not changed: `IRPerformUntil` (the parser records only one condition for `PERFORM UNTIL`),
`_condition_variables`, the behavioral parser's handling of `NOT ((a) AND (b))`, and every gap the
task named as out of scope.

## 3. Real-corpus before/after (45 sources, isolated trees)

"Before" ran in a subprocess against a byte-copy of the pre-fix `app/` tree (plus read-only
`data/sources`, `data/benchmark`, `tests/fixtures`, `tests/golden`), with `PYTHONPATH` pointing at it;
"after" ran against the repository. The snapshot records `app.__file__` and the IR builder's
SHA-256 and the comparison asserts they differ (before `6b0be4b5ac1b…`, after `f3ad80d3e1d4…`).
The baseline is the pre-fix working tree, not `origin/main` (which lacks all the accumulated work).

| Measure | Result |
|---|---|
| Sources changed | **8 / 45** — exactly the 8 audited sources |
| Parser diagnostics (count and codes) | 0 sources differ |
| Procedure statement nodes | 0 sources differ |
| Business-rule counts and conditions (modernization engine) | 0 sources differ (157 -> 157) |
| Behavioral tests | 274 -> 274, 0 sources differ; sources with >= 1 test 36 -> 36 |
| IR `IRIf` with extra terms | 0 -> **11**, each equal one-for-one to the AST's `extra_conditions` |
| Dependency edges | 6 sources gain an edge (below) |
| CFG decision labels | 8 sources |
| Legacy extractor conditions | 8 sources, 18 conditions |
| Generated Java | 1 source (`t_daily_trans_report`), see below |

Dependency edges added (all `CONDITION`, source line = the IF): `t_account_eligibility`
`ANNUAL-INCOME`@67; `t_condition_names_88` `TX-WITHDRAWAL`@54; `t_credit_approval` `CREDIT-SCORE`@37 and
`DTI-PERCENTAGE`@40 (its old `CREDIT-SCORE`@40 is now `@37`, since CONDITION targets are recorded
once at their first read); `t_daily_trans_report` `FD-TX-SUSPICIOUS`@56; `t_insurance_claim`
`CLAIM-AMOUNT`@37; `t_mortgage_service` `IN-LTV-RATIO`@50. `t_payment_gateway` and `t_pricing_tier`
gain none — their OR terms reuse a variable the first term already recorded.

### The 5 real OR conditions

| Condition | IR | Dependencies | CFG label | Legacy rule | Java header |
|---|---|---|---|---|---|
| `BANKRUPTCY-FLAG = 'Y' OR CREDIT-SCORE < 580` | both terms | `CREDIT-SCORE`@37 (new) | both | `(… OR …)` and `NOT (… OR …)` | skipped, `=` (below) |
| `FD-TX-VAL > 10000.00 OR FD-TX-SUSPICIOUS = 'Y'` | both terms | `FD-TX-SUSPICIOUS`@56 (new) | both | both | skipped, `=` |
| `DRIVER-AGE < 21 OR DRIVER-AGE > 75` | both terms | `DRIVER-AGE` | both | both | **`if (driverAge < 21 \|\| driverAge > 75) {`** |
| `AUTH-OUT-RESP-CODE = ' ' OR … = '000'` | both terms | `AUTH-OUT-RESP-CODE` | both | both | skipped, `=` |
| `PAYMENT-METHOD = 'ACH' OR … = 'WIRE'` | both terms | `PAYMENT-METHOD` | both | both | skipped, `=` |

5/5 survive into the IR, the CFG and the legacy extractor. Java is 1/5 (see below), and dependencies
record variables, not literals, so the literals `580`, `'WIRE'` and `'Y'` are correctly *not* edges.

### `WIRE`, `580`, `SUSPICIOUS`

| Term | IR | Dependencies | CFG | Legacy | Whole-program Java |
|---|---|---|---|---|---|
| `'WIRE'` (pricing_tier:69) | before no -> **after yes** | literal: never | no -> **yes** | no -> **yes** | no -> no |
| `580` (credit_approval:37) | no -> **yes** | literal: never (variable `CREDIT-SCORE`@37 is new) | no -> **yes** | no -> **yes** | no -> no |
| `SUSPICIOUS` (daily_trans_report:56) | no -> **yes** | no -> **yes** (`FD-TX-SUSPICIOUS`@56) | no -> **yes** | no -> **yes** | no -> no |

## 4. Java — what can and cannot be shown, and the one visible consequence

Correcting the previous report: it said `WIRE`, `580` and `SUSPICIOUS` were "absent from the
generated Java" as if only because the terms were dropped. That was incomplete. Two pre-existing,
independent backend limits also keep these IFs out of whole-program Java:

1. The generator emits only the entry paragraph's body and stubs every PERFORM'd paragraph
   (`BE009`); all 11 real compound IFs are in PERFORM'd paragraphs, except `daily_trans_report:56`.
2. `control_flow_emitter.SUPPORTED_OPERATORS` is `== != > >= < <=`, but the parser passes COBOL's
   `=` through unchanged, so **any** IF containing `=` (single or compound) has its header skipped
   with `BE007` (`IRIf has unsupported operator '='`).

So the real-corpus Java check runs `emit_if` on the *real* `IRIf` instructions the real pipeline
built: `if (driverAge < 21 || driverAge > 75) {`, `if (existingAccounts >= 3 && annualIncome > 75000.00) {`,
`if (creditScore >= 740 && dtiPercentage <= 35.00) {`, `if (creditScore >= 660 && dtiPercentage <= 45.00) {`.
The other 7 real compound IFs contain `=` or the level-88 `IS-TRUE` sentinel and are skipped with
`BE007` — asserted as such, never as a partial header.

**Visible consequence, `t_daily_trans_report`.** Its IF *is* in an emitted paragraph. Before: `if
(fdTxVal > 10000.00) {` (balanced braces, but a wrong condition — the `OR` term was lost). After:
the header is skipped (`FD-TX-SUSPICIOUS = 'Y'` uses `=`) and, because the generator's skip path still
emits the body and the closing `}`, the Java is unbalanced (7 `{`, 8 `}`). This is not a new mechanism:
on the pre-fix tree 4 sources already had `BE007`-skipped headers with unbalanced Java
(`t_batch_acct_update`, `t_fallthrough_flow`, `t_goto_spaghetti`, `t_policy_redefines`);
`t_daily_trans_report` is the fifth. Its dataset `compiles` flag was already `False` (`reference`)
before the fix, so no ground-truth status changed. The alternative — emitting the truncated header —
is exactly the silent wrong answer this task removes, so it was not restored.

## 5. Tests

New files, each in the directory that already tests that layer (87 tests):

* `tests/ir/test_extra_conditions_ir_fix.py` — plain IF unchanged (incl. exact serialized keys), AND,
  OR, multiple-term order, variable/decimal operands, level-88 `IS-TRUE`/`IS-FALSE`, nested IFs,
  serialization, CFG label, loop-simulator fail-safe, the 5 real ORs, cn88 (line 54), and an
  AST-driven check that every real `extra_conditions` term equals the IR's one-for-one (11 IFs).
* `tests/backend/test_extra_conditions_java_fix.py` — `&&`/`||`, order, precedence and parenthesisation,
  indentation, 5 fail-safe cases (unsupported operator/connector, empty operand, `=`), pipeline Java,
  and `emit_if` on the real `IRIf`s (4 supported, 7 asserted skipped-with-`BE007`).
* `tests/analysis/dependencies/test_extra_conditions_dependency_fix.py` — every variable of a
  compound condition, order, variable-vs-variable, level-88 names, literals never dependencies,
  the 11 real IFs, and the specific `FD-TX-SUSPICIOUS`@56 / `CREDIT-SCORE`@37 / `WIRE` cases.
* `tests/analysis/rules/test_extra_conditions_legacy_extractor_fix.py` — plain/AND/OR/multiple/nested,
  normalization, every real extra term appears in a rule, and that the API imports this extractor.
* `tests/dataset/test_mmim_v2_dataset.py` — version pins V10 -> V11 and §3j (4 tests: `extra_terms`
  only in the 8 sources, plain-IF IR unchanged elsewhere, dependency ground truth, counts and
  ground-truth statuses unchanged).

**Old implementation loses a term:** run inside the isolated pre-fix tree, **69 of the 87** new tests
fail; the 18 that pass are the "unchanged behaviour" guards. No existing test was weakened; the 3
`tests/ir/test_ir_control_flow.py` failures (a stale `condition=` keyword) are the documented
pre-existing ones and fail with the identical error on both trees.

## 6. Dataset regeneration (`mmim-gen-v11`)

| | mmim-gen-v10 | mmim-gen-v11 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 |
| VALIDATION_REASONING coverage | 36/45 | 36/45 |
| Skipped | 9 | 9 |
| Source->split assignment | — | identical |
| Ground truth (deterministic / executable_verified / reference) | 342 / 2 / 7 | 342 / 2 / 7 |
| Benchmark leakage | 0 | 0 |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |
| Max instruction example (tokens) | 15 010 | 15 010 |

**54 examples changed**, all in the 8 sources: COBOL_TO_JAVA 8 (embedded IR JSON), DEPENDENCY_REASONING
8, PROGRAM_UNDERSTANDING 8, MODERNIZATION_STRATEGY 8, RISK_CLASSIFICATION 8 (CFG labels and rule text quoted
in evidence), TRANSFORMATION_PLANNING 8, BUSINESS_RULE_EXTRACTION 6 (only the embedded `analysis.
dependencies` list — rule conditions and counts are identical). VALIDATION_REASONING is unchanged.
Two independent full regenerations are byte-identical (`all.jsonl`, split files, `manifest.json`,
`split_manifest.json`, `leakage_report.json`, every `instruction/*` file); `validation_report.json`
differs only in its recorded output `path`. `benchmark-v1` and `mmim-v1` (144 examples) are untouched.

## 7. New independent gaps (reproduced, documented, NOT fixed)

> **Gaps 1 and 2 below are resolved in `mmim-gen-v12`** by `docs/MMIM_JAVA_IF_EMISSION_FIX.md`: COBOL's `=`
> is emitted as Java `==`, and an untranslatable header now omits the whole construct instead of emitting its
> body and closing `}`. All 45 corpus Java outputs are brace-balanced (40 -> 45). Gap 3 is unchanged.

1. **The Java backend rejects COBOL's `=`.** `SUPPORTED_OPERATORS` has `==`, the parser/IR carry `=`, so
   every IF using `=` — the most common COBOL comparison — has its header skipped (`BE007`). It also
   blocks whole-program Java for 7 of the 11 real compound IFs. Fixing it (normalising `=` -> `==`)
   would change Java for many unrelated sources.
2. **The skip path emits the body and the closing `}` without the header.** The resulting Java is
   unbalanced and, were it balanced, would run the guarded body unconditionally. 5 corpus sources
   (4 before this task, plus `t_daily_trans_report`).
3. Only the entry paragraph is emitted; PERFORM targets are `BE009` stubs — already-known
   flat-paragraph limitation, listed only because it is why real IFs seldom reach whole-program Java.

Still open from earlier cycles and untouched: the behavioral parser cannot consume
`NOT ((a) AND (b))` (5 rules yield no test), `_condition_variables` reading `IS-FALSE` as a variable,
`IF <var> NOT = <literal>`, `PERFORM UNTIL` recovery, decimal accumulator arithmetic, and the
strategy-analyzer rationale text.

## 8. Exact files changed (this task)

* `app/ir/instructions.py` (`IRConditionTerm`, `IRIf.extra_terms`, `condition_text`),
  `app/ir/__init__.py`, `app/ir/builder.py`
* `app/analysis/serializers/_common.py` (`omit_if_empty` field metadata)
* `app/backend/java/control_flow_emitter.py`
* `app/analysis/dependencies/analyzer.py`
* `app/analysis/rules/extractor.py` (legacy)
* `app/modernization/flow/generator.py` (CFG label)
* `app/behavioral/extraction/loops.py` (fail-safe for a compound IF)
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V11`)
* tests: the 4 new files above, `tests/dataset/test_mmim_v2_dataset.py`,
  `tests/dataset/test_instruction_adapter_v2.py`
* docs: this file, `docs/MMIM_V2_DATASET_AUDIT.md`, `docs/MMIM_EXTRA_CONDITIONS_FIX.md` (correction note)
* `data/dataset/mmim-v2/**` (regenerated)
