# Java backend: COBOL `=` and untranslatable IF headers

Branch `feat/mmim-java-if-emission` (from `feat/mmim-extra-conditions`).
Follows `docs/MMIM_EXTRA_CONDITIONS_DOWNSTREAM_FIX.md` §7, which reported two independent Java-backend
defects. `generator_version` `mmim-gen-v11` -> `mmim-gen-v12`; `dataset_version` stays `mmim-v2`.

## 1. Path traced before any code changed

```
COBOL  IF WS-A = 5
  lexer      OPERATOR_EQ, lexeme "="
  parser     _parse_simple_condition keeps the lexeme; _COMPARISON_OPERATOR_LEXEMES =
             { =  >  <  >=  <=  !=  == }  -> IfStatementNode.condition_operator = "="
  IR         IRBuilder.build_if_statement passes it through unchanged -> IRIf(operator="=")
  Java       generator._collect_statements
               -> control_flow_emitter.emit_if -> _build_condition
               -> operator not in SUPPORTED_OPERATORS {== != > >= < <=}
               -> BE007, returns []
             back in _collect_statements: depth += 1 ANYWAY, dead.append(False)
               -> the guarded statements are emitted one level deep, with no header
               -> IREndIf: depth -= 1, emits "}"
```

`=` is the **only** parser-producible operator the backend rejects (`==` and `!=` are supported; `<>` is
never produced). The existing backend tests hand-build IR with `==`, which is why the real pipeline's `=`
was never exercised.

Both defects reproduced on an isolated copy of the pre-fix tree (`PYTHONPATH` pointing at it):

| Program | Pre-fix Java (`run()`) | `javac` |
|---|---|---|
| `IF WS-A = 5 / MOVE … / END-IF` | `wsR = y; }` — body, **no header**, stray `}` (3 `{`, 4 `}`) | `statements not expected outside of methods` |
| same with `ELSE` | `wsR = y; } else { wsR = n; }` — **both branches** run unconditionally | `illegal start of type` |
| control: `IF WS-A > 5` | `if (wsA > 5) { wsR = y; }` | fine structurally |

## 2. Root causes

1. **No spelling map for COBOL's equality operator.** The parser/IR keep `=`; the emitter only knows Java's `==`.
2. **Header emission was assumed infallible in the depth accounting.** `_collect_statements` incremented the
   nesting depth whether or not `emit_if`/`emit_perform_until` produced a header, so the body, any `ELSE`
   and the closer were emitted around a header that did not exist: unbalanced Java, and — had a construct
   balanced by coincidence — guarded statements executing unconditionally.

## 3. The fix (`app/backend/java/` only)

* `control_flow_emitter.py`: `OPERATOR_ALIASES = {"=": "=="}`, applied in the shared `_build_condition`
  (so `IF`, compound `extra_terms`, and `PERFORM UNTIL` all gain `=`). `SUPPORTED_OPERATORS` is deliberately
  **unchanged** (an existing test pins it, and it stays "the Java operators"). Every other operator, and
  every unsupported one (`GREATER`, `<>`, `""`, the level-88 `IS-TRUE`/`IS-FALSE` sentinels), behaves exactly
  as before.
* `generator.py::_collect_statements`: when a header cannot be translated, the **whole construct** — header,
  body, `ELSE` branch, nested constructs and the closing `IREndIf`/`IREndPerform` — is omitted and replaced by
  one `// TODO: IF condition cannot be translated (BE007); guarded block omitted.` comment
  (`PERFORM UNTIL`: `loop body`). Nothing is opened, nothing left unmatched, nothing runs unconditionally, and
  no truncated condition is ever emitted (a compound with one untranslatable term omits the whole construct).
  The matching closer is found by `_matching_close`, which matches nested constructs by type. If the IR is
  malformed and has **no** matching closer, only the header is omitted, so the existing contracts
  `test_generation_continues_after_bad_if` and `test_be007_does_not_suppress_be005` hold unmodified. The
  comment is a fixed string — no COBOL text is copied into it (Java processes `\u` escapes even in comments).

No parser, business-rule, behavioral, dependency, IR or dataset-builder code changed.

## 4. Tests

`tests/backend/test_java_if_emission_fix.py` — 45 tests: `=` -> `==` for literals, variables, decimals and
negatives, in `IF`, compound (`OR`/`AND`/mixed) and `PERFORM UNTIL`; every other supported operator unchanged;
the unsupported ones still `BE007`; `SUPPORTED_OPERATORS` unchanged; pipeline COBOL -> Java; an untranslatable
`IF` (with/without `ELSE`, nested inside/outside, `PERFORM UNTIL`, malformed unclosed) never emits its body
or an unmatched brace; a level-88 program through the real pipeline; a `javac` compile of a program with an
omitted IF; and the real corpus (below). **28 of the 45 fail on the pre-fix tree**; the 17 that pass are the
"unchanged behaviour" guards.

Two assertions in last task's `tests/backend/test_extra_conditions_java_fix.py` pinned the defect itself
(`=` "unsupported") and were updated, not weakened: the fail-safe parameter now uses `IS-TRUE`, and the
real-corpus skip test now covers only `condition_names_88.cbl:54` (the other six now emit — asserted in the
new file). All pre-existing backend tests pass unmodified.

## 5. Real-corpus before/after (45 sources, isolated trees)

"Before" = a byte-copy of the pre-fix (`mmim-gen-v11`) `app/` tree run in a subprocess with `PYTHONPATH`
pointing at it; "after" = the repository. The snapshot records `app.__file__`, the emitter's SHA-256 and
whether `OPERATOR_ALIASES` exists; the comparison asserts they differ (`4d9b23dbcdab`/no alias vs
`8b3679cd92f3`/alias). Every source's Java was written out, brace-counted and compiled with the real
`javac 25.0.3` (`_check_javac`, the function the dataset builder uses).

| Measure | Before | After |
|---|---:|---:|
| Sources whose generated Java changed | — | **5 / 45** |
| Java with balanced braces | 40 / 45 | **45 / 45** |
| Sources with a `BE007` diagnostic | 5 | 0 |
| `javac` compiles | 38 / 45 | 38 / 45 (no change) |
| Sources failing `javac` with a *structural* error | 5 | **0** |

The 5 changed sources are exactly the previously unbalanced ones, each gaining the header that was skipped:

| Source | Added header | Braces |
|---|---|---|
| `t_batch_acct_update` | `if (fdOverdraftProt == y) {` | 11/12 -> balanced |
| `t_daily_trans_report` | `if (fdTxVal > 10000.00 \|\| fdTxSuspicious == y) {` (**both** terms) | 7/8 -> balanced |
| `t_fallthrough_flow` | `if (stepAHitCount == 0) {` | 4/5 -> balanced |
| `t_goto_spaghetti` | `if (stepIndex == 1) {` | 5/6 -> balanced |
| `t_policy_redefines` | `if (policyKind == auto) {` and `if (policyKind == life) {` | 7/9 -> balanced |

`t_daily_trans_report` (the one compound IF in an emitted paragraph) went `balanced-but-wrong` (v10: the OR was
dropped) -> `unbalanced` (v11: header skipped) -> **correct and balanced** with both terms.

**`javac`.** Before, the 5 failed with structural errors (`illegal start of type`, `statements not expected
outside of methods`, `<identifier> expected`). After, *all 7* non-compiling sources fail only with
`cannot find symbol`, from two unrelated pre-existing defects (§7): single-quoted COBOL literals emitted as
identifiers (`y`, `auto`, `life`, `started`, `completed`, `skippedAlpha`, `highrisktransactionflagged`) and
undeclared FILE SECTION fields (`fdTxVal`, `fdAcctBal`, `fdOverdraftProt`, `fdTxSuspicious`). So compile
status is unchanged, honestly: the fix removes the structural breakage without making these programs
compilable.

The 7 real compound IFs skipped last cycle: the 6 that contained only `=` now emit (verified with `emit_if` on
the real `IRIf`s, since 5 of them live in `BE009`-stubbed paragraphs and never appear in whole-program Java):
`credit_approval:37` `bankruptcyFlag == … || creditScore < 580`, `daily_trans_report:56`, `insurance_claim:37`
`… == … && claimAmount > 5000.00`, `mortgage_service:50` `… == … && inLtvRatio <= 80.00`, `payment_gateway:46`
`authOutRespCode == … || authOutRespCode == …`, `pricing_tier:69` `paymentMethod == … || paymentMethod == …`.
The 7th, `condition_names_88:54`, uses the level-88 `IS-TRUE` sentinel, is still untranslatable, and is omitted
safely. No `PERFORM UNTIL` header changed anywhere in the corpus, and **no corpus source now exercises the
omission path** (0 `BE007`); that path is covered by the unit and pipeline tests.

## 6. Dataset regeneration (`mmim-gen-v12`)

`app/dataset/version.py::MMIM_GENERATOR_VERSION_V12`. Only the Java text changed, so only COBOL_TO_JAVA.

| | mmim-gen-v11 | mmim-gen-v12 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 |
| Examples changed | — | **5** (COBOL_TO_JAVA of the 5 sources; every other example byte-identical) |
| `compiles == True` | 38 | 38 |
| Ground truth (deterministic / executable_verified / reference) | 342 / 2 / 7 | 342 / 2 / 7 |
| VALIDATION_REASONING coverage | 36/45 | 36/45 |
| Source->split assignment | — | identical |
| Benchmark leakage | 0 | 0 |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |

Two independent full regenerations are byte-identical (`all.jsonl`, split files, `manifest.json`,
`split_manifest.json`, `leakage_report.json`, every `instruction/*` file); `validation_report.json` differs only
in its recorded output `path`. `benchmark-v1` and `mmim-v1` are untouched.

## 7. Remaining gaps (independent, reproduced, NOT fixed)

> **Gap 1 below is resolved in `mmim-gen-v13`** by `docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md`:
> `_translate_operand` now recognises COBOL's own `'...'` string-literal delimiter. 3 sources newly
> compile (38 -> 41 of 45); the other 4 non-compiling sources fail only on undeclared FILE SECTION
> fields (gap 3) and a newly-documented `READ ... AT END` identifier-mangling defect. Gaps 2 and 4
> are unchanged.

1. **Single-quoted COBOL literals are translated as identifiers.** `MOVE 'Y' TO WS-R` -> `wsR = y;`; a
   condition `X = 'ACH'` -> `x == ach`. `_translate_operand` only recognises double-quoted literals while the
   lexer keeps COBOL's single quotes. It affects every operator and statement (it is why the 7 sources above
   still fail `javac`), so this task asserts operators and structure, never a single-quoted literal's translation.
2. **`==` on Java `String` is reference equality.** `=` is now `==` as specified; for a `String` field compared
   with a literal that compiles but is not value equality — correct output needs field types (`.equals`), which
   the IR operands do not carry.
3. **FILE SECTION fields are not declared as Java fields** (`fdTxVal`, `fdAcctBal`, …), so conditions and moves
   over them fail `javac` with `cannot find symbol`.
4. The level-88 `IS-TRUE`/`IS-FALSE` sentinels have no Java translation; their IFs are omitted whole (safe, but
   the guarded logic is absent from the Java).

Still open from earlier cycles and untouched: the behavioral parser cannot consume `NOT ((a) AND (b))`,
`_condition_variables` reading `IS-FALSE` as a variable, `IF <var> NOT = <literal>`, `PERFORM UNTIL` recovery,
decimal accumulator arithmetic, and the strategy-analyzer rationale.

## 8. Exact files changed (this task)

* `app/backend/java/control_flow_emitter.py`, `app/backend/java/generator.py`
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V12`)
* `tests/backend/test_java_if_emission_fix.py` (new), `tests/backend/test_extra_conditions_java_fix.py`
  (two assertions updated), `tests/dataset/test_mmim_v2_dataset.py` (V12 pins + §3k, 4 tests),
  `tests/dataset/test_instruction_adapter_v2.py`
* `docs/MMIM_JAVA_IF_EMISSION_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
  `docs/MMIM_EXTRA_CONDITIONS_DOWNSTREAM_FIX.md` (resolution note)
* `data/dataset/mmim-v2/**` (regenerated)
