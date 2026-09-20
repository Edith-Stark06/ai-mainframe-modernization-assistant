# MMIM — COBOL text comparison and level-88 condition translation (Stage 24, `mmim-gen-v22`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v22`

Two related but distinct backend gaps, fixed separably:

1. **Text comparison.** `IF WS-CODE = 'AUTO'` was emitted as `wsCode == "AUTO"`.
2. **Level-88 condition references.** `IF NAME` / `IF NOT NAME` were always omitted with `BE007`
   (Stage 23 kept the metadata and removed the storage fields; this stage uses that metadata).

They share **one** expression-generation path — `control_flow_emitter._build_condition` — and one small
context object; nothing else is shared (§4).

## 1. The comparison path, traced end to end

| Stage | Where | What happens to `IF A = 'x'` |
|---|---|---|
| Parser | `procedure_parser` | `IfStatementNode(condition_left, condition_operator, condition_right, extra_terms…)`; the operator is kept as written (`=`, `>`, `!=` …). `NOT =` and `<>` are not parsed (existing gap). |
| IR | `IRBuilder` | `IRIf(left, operator, right, extra_terms)` / `IRPerformUntil(left, operator, right)` — operands are strings; **no type information**. A condition-name is `IRIf(left=NAME, operator="IS-TRUE"/"IS-FALSE", right=NAME)`. |
| Backend | `generator._collect_statements` → `emit_if` / `emit_perform_until` → `_build_if_condition` → **`_build_condition`** | The *only* place a Java comparison is produced: `"<left> <op> <right>"` with `=` aliased to `==`; the sole other consumers of the result are compound `AND`/`OR` terms and `while (!(…))`. `grep` finds no other `==`/`equals` generator in `app/`. |

`_build_condition` had no idea whether an operand was text or a number — the IR does not say, and the emitter
was never given the field types.

## 2. Reproduction (isolated pre-fix tree, real `javac`/`java`)

```cobol
01 WS-CODE PIC X(4) VALUE 'AUTO'.   01 WS-RES PIC X(3) VALUE 'NO'.   01 WS-NOT PIC X(3) VALUE 'NO'.
IF WS-CODE = 'AUTO'  MOVE 'YES' TO WS-RES END-IF
IF WS-CODE = 'LIFE'  MOVE 'BAD' TO WS-NOT END-IF
```
Java: `if (wsCode == "AUTO") …` / `if (wsCode == "LIFE") …`. Executed with the field left alone, seeded with an
*equal but distinct* `String` object, and seeded `LIFE`:

| Seed for `wsCode` | Pre-fix result | COBOL semantics |
|---|---|---|
| untouched (literal `"AUTO"`) | `wsRes=YES` | `YES` |
| `new String("AUTO")` | `wsRes=NO` ✗ | `YES` |
| `new String("LIFE")` | `wsRes=NO, wsNot=NO` ✗ | `wsRes=NO, wsNot=BAD` |

The first row is why the defect hides: both sides are the same interned compile-time constant, so `==` is
true. Any equal string from anywhere else — a `MOVE` from another field, runtime input, reflection (the
behavioral harness sets fields that way) — defeats it.

## 3. What is the correct translation?

COBOL alphanumeric comparison pads the shorter operand with spaces, so **trailing spaces never matter**
(`'AUTO'` = `'AUTO  '`), and a field that was never given a value is blank. It is *not* `.equals()` (that
would still say `"AUTO".equals("AUTO  ")` is false, and would throw on a never-set `null` field), and it is
**not** for every `==`: numbers must stay `==`.

Rules implemented (`app/backend/java/condition_context.py`):

* `=`/`!=` become `_cobolEquals(l, r)` / `!_cobolEquals(l, r)` **only when both operands are known text** — a
  quoted literal, or a field the generator declared as `String` (alphanumeric *and* group items).
* Anything else is emitted exactly as before: numeric operands, **mixed** text/number (`wsCode == 5`),
  operands of **unknown type** (FILE SECTION fields — never declared by the backend — and figurative constants
  such as `SPACES`), and every **ordering** operator (`<`, `>`, `<=`, `>=` on text depend on the collating
  sequence and are not modelled).
* `_cobolEquals` is a small static helper (rtrim both sides, `null` ≡ blank, `equals`), emitted once after
  `run()` **only by a class that uses it**, with no JDK-version dependency.
* It is **package-private** and named with an underscore. The scanners that read method names back out of
  generated Java (`behavioral/extraction/extractor.py`, `java_modernization/generation/generator.py` and
  `compilation/compiler.py`, `knowledge/chunkers.py`) match only `public|private|protected` methods and treat
  each one as a COBOL paragraph — a `private` helper would have appeared as a fake paragraph `_COBOL-EQUALS`
  and created a spurious artifact. (An underscore also cannot collide with a COBOL-derived name.) Tested.

## 4. Level-88 conditions: is the existing metadata sufficient?

**Yes, without touching the IR.** A condition-name is true when its *parent item* equals any declared value.
Both facts already exist: the parent is the nearest preceding non-88 item (the rule the behavioral extractor
already applies), and the values are `ConditionNameNode.values` (Stage 23 extended which literals parse).
The IR carries neither, so — exactly like Stage 19's `paragraph_order` — `AnalysisService` derives a small
`{NAME: ConditionName(parent, values)}` map from the AST (`build_condition_names`) and passes it to
`generate_with_diagnostics(…, condition_names=…)`. The generator combines it with the field list it already
receives into a `ConditionContext(field_types, condition_names)` that `emit_if`/`emit_perform_until` accept as
an **optional** argument (default `None` ⇒ byte-for-byte the old output, which is what every hand-built-IR
test relies on).

Translation (`translate_condition_name`): the parent compared with each value — text values through
`_cobolEquals`, numeric values through `==` — joined with `||`; `IF NOT` is the negation, written as the
conjunction of the inequalities (`(p != 1 && p != 2)`, `(!_cobolEquals(p,"D") && …)`). A single value needs no
parentheses; a multi-value condition is parenthesised so it composes inside a compound `IF`. Values are
rendered with Stage 20's `translate_value_literal`, so they are octal-safe (`007` → `7`), signed
(`-1`), leading-decimal (`.5` → `0.5`), and `SPACES` → `""`.

**Not guessed — kept as `BE007` (block omitted), with the reason in the message:** a figurative constant with
no proven Java equivalent (`ZERO` on a text parent, `HIGH-VALUES`, `LOW-VALUES`, `QUOTES`), a text value on a
numeric parent, a number on a text parent, a decimal on an integer parent, an `int` overflow, a parent that
is not a declared field, and a compound `IF` in which any term is untranslatable (the whole header is
skipped, never emitted with a term missing). A reference to a condition-name the context does not know keeps
the original "unsupported operator `IS-TRUE`" message.

**Separability.** The text-comparison fix uses only `field_types`; the condition-name fix additionally uses
`condition_names` and reuses the text comparison for text-valued conditions (`_cobolEquals`). Either could
ship alone; they share the context object and the helper because a text-valued condition *is* a text
comparison.

## 5. Corpus exposure (measured before editing)

IR-level (`IRIf`/`IRPerformUntil`, including compound terms) over the 45 sources:

| Term shape | Terms | Sources |
|---|---|---|
| `String` field `=` string literal | 49 | 17 |
| string literal `=` *unknown-type* operand (FILE SECTION `FD-…`) | 2 | 2 (`t_batch_acct_update`, `t_daily_trans_report`) |
| level-88 `IS-TRUE` / `IS-FALSE` | 6 / 1 | 1 (`t_condition_names_88`) |
| numeric comparisons (`int`/`double` vs literal or field) | 83 (+5 on unknown-typed FILE SECTION operands) | ~30 |

But almost all of them sit in paragraph bodies the backend lowers *after* an unconditional `STOP RUN`/`GOBACK`
and therefore skips as unreachable (`BE011`). **Only four *text* comparisons reach generated Java at all:**
`policyKind == "AUTO"` / `"LIFE"` in **`t_policy_redefines`** (declared `String` field vs literal — the one
affected source), and `fdOverdraftProt == "Y"` / `fdTxSuspicious == "Y"` (FILE SECTION fields of unknown type
— deliberately unchanged; those two sources already fail `javac` for the undeclared fields). No level-88
reference is in reachable code, so the condition translation changes no corpus output.

## 6. Verification

**Isolated pre-fix proof** (byte-copy of the pre-edit tree, `cwd` rooted there, `app.__file__` inside it, new
module confirmed absent; the copied test file gets local stand-ins for the one missing import). Of the **98**
new tests, **91 fail** pre-fix: **24 on genuinely wrong behavior of the unmodified code** (executed-Java
oracle mismatches for every text seed but the coincidental ones, for every level-88 seed, the real source, and
wrong generated text), 67 because the new API does not exist (56 missing function, 11 missing parameter). The **7
that pass on both trees** are the intended guards: `emit_if` without a context is byte-identical;
ordering / mixed / unknown comparisons unchanged; an 88 with an untranslatable value omitted with `BE007`; and 4
text seeds where identity `==` happens to agree with COBOL. Four pins in other files that asserted the old
behavior also fail pre-fix (§7).

**Executed Java** — the strong checks: real `javac`/`java`, a reflection harness seeding *equal but distinct*
`String` objects, and an **independent Python oracle** of the COBOL semantics that never reads the Java text:
* text: 11 seeds (equal in distinct objects, different, equal-to-literal-but-not-to-field, trailing spaces on
  either side, longer string, case difference, empty, never-set fields, unset vs value, numeric
  differences) × 9 comparisons (`=`/`!=` vs literal and vs field, padded literal, numeric `=`/`!=`, decimal `=`),
  plus the untouched-defaults state;
* level-88: 8 seeds × 15 conditions (single/multi text values, `IF NOT`, signed, multi signed,
  `VALUE ZERO`, leading-decimal `.5`/`-.5`, `VALUES ARE` decimals, padded value, `AND`/`OR`/`NOT` compounds) plus
  the defaults;
* `PERFORM UNTIL <condition-name>` (hand-built IR: the COBOL parser rejects a bare condition-name there) with
  4 flag states, including zero iterations and a padded flag;
* the real `t_policy_redefines` class compiles and, driven with distinct `String` objects (`AUTO`, `LIFE`,
  `AUTO␠␠`, `BOAT`), takes the branch COBOL takes.

**Real corpus before/after (45 sources, per-source hashes of AST, IR, CFG, dependencies, business rules,
risks, strategy, syntax/semantic/backend diagnostics, Java text, `javac`; "before" from the isolated
baseline tree):** exactly **1** source changes — `t_policy_redefines`' Java text (two conditions rewritten +
the 15-line helper). AST, IR, CFG, dependencies, rules, risks, strategy, syntax and backend diagnostics are
identical for all 45; `javac` **41/45 → 41/45**; identity text comparisons in Java 4 → 2 (the two FILE
SECTION ones). (The semantic-diagnostics hash of that source also moved — an artifact: its `SEM001`
duplicate-`FILLER` message embeds a random temp-dir path and differs between any two runs.)

**Dataset (`mmim-gen-v22`):** only **1 example** changes — `t_policy_redefines` `cobol_to_java`
(`expected_output.java`, still `compiles: true`). 351 examples, splits 226/71/54 and assignment, leakage
0 errors / 5 warnings, benchmark leakage clean, 157 rules, 41 compiling, statuses 345/2/4, and every other
task type — including `transformation_planning` (the helper does not match the architecture's field
pattern) — are unchanged. Two independent regenerations are byte-identical to each other and to the on-disk
dataset (SHA-256; `validation_report.json` compared without its embedded `path`).

## 7. Existing tests that moved (all direct consequences; none deleted or weakened)

* `test_java_literal_emission_fix.py` (2): the expected header text is now `_cobolEquals(…)`.
* `test_mmim_v2_dataset.py` (1): `policyKind ==` → `_cobolEquals(policyKind, "AUTO")`.
* `test_level88_java_representation.py` (Stage 23): the ordinary-comparison assertion, and the "condition
  reference is untranslatable" parametrization narrowed to the forms that genuinely still are
  (`HALF`, `SIGNS`, `BLANK`, compounds containing them).
* `test_java_if_emission_fix.py` (2 + header): they used `IF IS-OK` to exercise "an untranslatable IF is
  omitted safely". `IS-OK` is now translated, so they use a new `88 IS-UNSAFE VALUE ZERO` (a figurative
  constant on a text item — still untranslatable), preserving their intent.

## 8. Remaining gaps (reproduced, NOT fixed)

1. *(Resolved in Stage 25, `mmim-gen-v23`, docs/MMIM_NEGATED_COMPARISON_FIX.md.)* `IF X NOT = 'A'` and `IF X <> 'A'` are not parsed (`SYN005`) — the existing unsupported-header gap.
2. `PERFORM UNTIL <condition-name>` is rejected by the parser (`SYN005`); the backend handles it (tested with
   hand-built IR).
3. Ordering comparisons on text (`IF X > 'A'`) still emit Java `>` on `String` (does not compile) — needs
   collating-sequence semantics. Mixed text/number comparisons likewise unchanged.
4. Figurative constants as comparison operands (`IF X = SPACES`) are unchanged (`spaces` is emitted as an
   undeclared identifier); FILE SECTION fields are undeclared, so their comparisons stay identity `==`.
5. `SET <condition-name> TO TRUE` is unsupported (`SYN100`); level-88 `THRU` ranges / comma lists remain
   rejected.
6. `MOVE` still stores a text literal as written (no padding/truncation to the picture width); the
   comparison is insensitive to trailing spaces, but a `MOVE` of an over-long literal is not truncated.
7. Decimal fields are Java `double`; `==` on computed decimals is exact-bit equality.
8. `MOVE 09`, `MOVE SPACES`, `DataModelElement.initial_value`, PERFORM semantics, `GO TO … DEPENDING ON`,
   unsupported IF headers, FILE SECTION declarations, `COMPUTE`, `COMP`/`COMP-3` — as recorded before.

## 9. Files

`app/backend/java/condition_context.py` (new), `app/backend/java/control_flow_emitter.py`,
`app/backend/java/generator.py`, `app/analysis/service.py`, `app/dataset/version.py`
(`MMIM_GENERATOR_VERSION_V22`), `tests/backend/test_cobol_comparison_semantics.py` (new, 98 tests),
`tests/dataset/test_mmim_v2_dataset.py` (V22 pins, §3u — 5 tests, one assertion),
`tests/dataset/test_instruction_adapter_v2.py`, `tests/backend/test_java_literal_emission_fix.py`,
`tests/backend/test_java_if_emission_fix.py`, `tests/backend/test_level88_java_representation.py`,
`data/dataset/mmim-v2/**` (regenerated v22), `docs/MMIM_STRING_COMPARISON_FIX.md` (this file),
`docs/MMIM_V2_DATASET_AUDIT.md`, and resolution pointers in `docs/MMIM_LEVEL88_VALUE_FIX.md`,
`docs/MMIM_VALUE_INITIALIZER_FIX.md`.
