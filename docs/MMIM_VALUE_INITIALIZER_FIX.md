# MMIM — COBOL `VALUE` clause → Java field initializer (Stage 20, `mmim-gen-v19`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v19`

Stage 19 found, and deliberately did not fix, that a COBOL `VALUE` clause never becomes a Java field
initializer: `STEP-INDEX PIC 9(2) VALUE 01` was `private int stepIndex;`, so `t_goto_spaghetti`'s
generated Java, run as-is, took the ELSE path and ended `accumulator=50` instead of the COBOL program's
`30`. This document is the investigation and fix.

## 1. Data flow, traced end to end (before any edit)

| Stage | Location | What happens to `VALUE` |
|---|---|---|
| Parser | `app/parser/syntax/data_parser.py` (~876–1000) | After `PIC`, `VALUE [IS]` is followed by **one** token, stored raw in `ElementaryItemNode.value`. A group item's `VALUE` is discarded. |
| AST | `app/parser/ast/data_items.py` | `ElementaryItemNode.value: str \| None` — the raw lexeme (`'INITIAL'`, `01`, `00065000.00`, `SPACES`). |
| Symbols | `app/parser/semantic/symbol_collector.py::visit_elementary_item` | **Lost here.** `node.value` was never passed on, and `VariableSymbol` had no field for it. |
| IR | `app/ir/builder.py` | Carries no declarations at all — only the procedure division is lowered. |
| Backend | `app/backend/java/generator.py::build_fields_from_symbols` | Hardcoded `initial_value=None`; the docstring called a `VALUE` initializer a "future enhancement". |
| Render | `app/backend/java/field_model.py::JavaField.render` | Already renders `= <initial_value>` when given. Needed no change. |

**Root cause:** `VariableSymbol` had no `value`, so the parsed literal never reached `build_fields_from_symbols`.
`AnalysisService` builds the fields from the symbol table, so carrying the value on the symbol is the smallest
correct wiring (the alternative — threading the AST into the backend by name — would have to re-resolve
names and duplicates that the symbol table already resolved).

## 2. Corpus survey (all 45 sources, measured before editing)

* 408 data items parsed: 322 elementary, 75 group, 11 level-88. **270 elementary items carry a `VALUE`**;
  every one of the 45 sources has at least one, so every generated Java text changes.
* Java field type × literal kind: `String` ← 85 quoted + 19 `SPACE`/`SPACES`; `double` ← 82 decimal;
  `int` ← 84 integer. **No** literal/type mismatch, **no** `int` overflow (widest integer picture is `9(8)`),
  **no** string containing a quote or backslash.
* 52 elementary items, 75 group items and the 11 level-88 items have no initializable `VALUE`.

**The octal hazard is real in this corpus.** Java reads a leading `0` as octal. Of the 36 leading-zero
integer literals: **2 would not compile** (`t_insurance_claim` `DRIVER-AGE VALUE 028`, `t_packed_decimal`
`ACCOUNTING-PERIOD VALUE 09`), **9 would compile with the wrong value** (`t_account_eligibility` `AGE 035`
→ 29, `t_dead_code_audit` `VALID-TOTAL 000500` → 320, `t_inventory_reorder` `SAFETY-STOCK-LEVEL 00150` →
104, …), and 25 are value-preserving only by luck (`00`, `01`, `005`, …). Pasting the literal as written is
therefore wrong; numbers must be emitted from their *value*.

## 3. The fix

* `VariableSymbol.value: str | None = None` (`app/parser/semantic/symbols.py`) — defaulted, so every existing
  construction site is unchanged; `dataclasses.replace(..., cobol_type=...)` in the type builder carries it.
* `SymbolCollectorVisitor.visit_elementary_item` passes `node.value` (`symbol_collector.py`). Group items and
  level-88 condition-names still register `None`.
* New `app/backend/java/value_initializer.py::translate_value_literal(literal, java_type)`, used by
  `build_fields_from_symbols` (`generator.py`):

  | Java type | Accepted | Emitted |
  |---|---|---|
  | `String` | `'text'` / `"text"` | `"text"` (escaped by the statement emitter's own `_escape_java_string_content`) |
  | `String` | `SPACE` / `SPACES` | `""` |
  | `int` | `[+-]digits`, `ZERO`/`ZEROS`/`ZEROES` | the integer's value (`035` → `35`), only if it fits an `int` |
  | `double` | integer or decimal literal, `ZERO…` | value with leading zeros stripped (`00065000.00` → `65000.00`, `5` → `5.0`), no negative zero |
  | anything else | — | `None`: the field is still declared, exactly as before, with **no** initializer |

  Not guessed: `ZERO` on a `String`, `HIGH-VALUES`/`LOW-VALUES`/`QUOTES`, a string literal on a numeric field,
  a decimal on an integer picture, an `int` overflow. None occur in the corpus; all are tested to yield `None`.
* **Convention.** String initializers are stored as written, *not* padded to the picture width — the same
  convention the statement emitter already uses for `MOVE 'X' TO FIELD` — so an initialized field and a
  field assigned by `MOVE` are represented identically. `SPACES` is therefore `""` (and, unlike Java's
  default, not `null`).
* `value_initializer.py` imports `_escape_java_string_content` lazily: `statement_emitter →
  control_flow_emitter → generator`, and `generator` imports the new module, so a top-level import is circular.

### A consequence outside the backend, caught and fixed

`app/java_modernization/architecture/builder.py::_FIELD_RE` recovered the data model by matching
`private <type> <name>;` in the generated Java. Once fields carry initializers (`private int age = 25;`)
that pattern stopped matching, so **every initialized field silently vanished** from `transformation_planning`'s
`data_model` — and a program whose fields are all initialized lost its DTO component. This surfaced in the
first dataset regeneration as an *unexpected* `transformation_planning` diff on all 45 sources (e.g.
`t_goto_spaghetti` `data_model` 5 → 1, 19 sources losing the DTO), not as a test failure. The pattern now
accepts an optional single-line initializer. It deliberately does **not** copy the initializer into
`DataModelElement.initial_value`, so the architecture output is byte-identical to before — that model field
stays unused, and populating it is a separate, optional follow-up.

### Golden files updated (deliberate)

`tests/golden/{arithmetic,combined_program,if_else,perform_until}.java` are compared against the backend's
output for their `.cbl`, and those four `.cbl` files declare `VALUE`s. Exactly 5 lines changed
(`numA = 10`, `numB = 5`, `counter = 1`, `age = 25`, `cnt = 0`), each matching the `VALUE` in its `.cbl`.
Because the dataset uses these files as the *reviewed* Java for `fx_combined` and `fx_perform_until`, their
`cobol_to_java` examples change with them.

Two more spec pins asserted the *old* uninitialized declarations for programs that declare a `VALUE`, and were
updated the same way (found by the full-suite run, not by the focused runs): `tests/integration/test_pipeline.py::
test_combined_program_pipeline` (`private int wsA;` → `private int wsA = 10;`, `wsB` → `= 20`) and the
`tests/regression/fixtures/arithmetic/add.json` expectations (`numA` → `= 10`, `numB` → `= 20`). Each edit
pins a value that is literally in the fixture's `.cbl`; no assertion was removed or loosened.

## 4. Verification

**Isolated pre-fix proof.** The new tests were run on a byte-copy of the pre-edit tree, `cwd` rooted there
(`app.__file__` confirmed inside the copy). Because the new module does not exist pre-fix, the copy of the
test file stubs that one import; the copy of the dataset test pins `V18`. **82 fail, the rest pass**:
76/78 in `test_java_value_initializer.py`, 4 of the new dataset pins, and both new architecture tests. The
5 that pass on both trees are the intended guards (valueless items stay uninitialized, no leading-zero
initializer, compile count 41, architecture data model unchanged).

**Mid-state proof of the architecture regression.** A second copy with the value fix but the *old*
`_FIELD_RE` fails 5 tests, three of them pre-existing
(`test_data_model_maps_working_storage_fields`, `test_data_record_is_generated_from_working_storage`,
`test_patch_to_a_file_without_an_error_is_rejected`) plus the two new architecture tests.

**Executed behavior** (real `javac`/`java`, nothing seeded):
* `t_goto_spaghetti`, run as generated, now follows the loop path the COBOL program takes
  (`2000→4000→2000→4000→2000→5000`) and ends `accumulator=30, stepIndex=4, retryCounter=2,
  terminalState=COMPLETED` — the state Stage 19's independent oracle computed. Before, it ended
  `accumulator=50`.
* A program with `VALUE 035 / 028 / 09 / 00500 / 00065.25 / 'INITIAL' / SPACES` compiles and holds
  `35 / 28 / 9 / 500 / 65.25 / INITIAL / ""`.

**Real corpus before/after (45 sources):** Java text changed for **45/45**; the *only* differing lines are
the **270** field declarations that gained ` = <initializer>` (verified line by line: same line count, no
other diff). Each of the 270 initializers was checked against its COBOL literal — numerically equal for
numbers, textually equal for strings, `""` for `SPACE(S)`. `javac` 41/45 → 41/45 (the same 4 FILE SECTION
failures), braces 45/45, `// TODO` 111 → 111, backend diagnostics 564 → 564.

**Dataset (`mmim-gen-v19`):** only **COBOL_TO_JAVA** changes — **45 examples**, `expected_output.java`
only. `compiles` `True`→`True` for 41 and `False`→`False` for 4, ground-truth statuses unchanged
(345 deterministic / 2 executable_verified / 4 reference), 351 examples, splits 226/71/54, source→split
assignment, leakage report (0 errors / 5 warnings), 157 rules, business-rule conditions (0 changed),
`transformation_planning` and every other task type unchanged. Two independent regenerations are
byte-identical to each other and to the on-disk dataset (SHA-256), except `validation_report.json`, which
differs only in its embedded `path` field.

## 5. Independent defects found, reproduced, NOT fixed

1. **A signed `VALUE` literal drops the whole data item** (`t_packed_decimal`, 5 items). *Resolved in Stage 21 (`mmim-gen-v20`, docs/MMIM_SIGNED_VALUE_FIX.md).* The lexer emits the
   sign as a separate `UNKNOWN` token (`VALUE`, `+`, `000450000.00`); the parser's single-token capture takes
   `+`, then reports `SYN005 expected '.' to terminate data item, got '000450000.00'` and abandons the item.
   `BEGINNING-BALANCE`, `PERIOD-DEBITS`, `PERIOD-CREDITS`, `ENDING-BALANCE`, `VARIANCE-AMOUNT` therefore
   have no symbol and no Java field, and their `VALUE`s cannot be initialized. Reproduced in isolation:
   `PIC S9(3)V99 COMP-3 VALUE +000450.00` and `PIC S9(3) VALUE -5` are dropped; the unsigned
   `PIC S9(3)V99 COMP-3 VALUE 000450.00` parses. This is the actual cause of the `t_packed_decimal` `SYN005`
   that `docs/MMIM_V2_DATASET_AUDIT.md` had attributed to a "COMP-3/VALUE clause-ordering interaction"; it is
   a sign-token problem, not an ordering one. Only this one source is affected (11 `VALUE` clauses in the
   source, 6 parsed; every other source's elementary `VALUE` clauses are all parsed).
2. *(Resolved in Stage 23, `mmim-gen-v21`, docs/MMIM_LEVEL88_VALUE_FIX.md.)* **Level-88 condition-names are emitted as `String` storage fields** (11 in `t_condition_names_88`). They are
   not storage. (This stage keeps them uninitialized.)
3. *(Resolved in Stage 24, `mmim-gen-v22`, docs/MMIM_STRING_COMPARISON_FIX.md.)* **`IF` on `String` fields emits `==`** (reference comparison), not `equals`.
4. **`MOVE 01 TO X` emits the literal unnormalized** (`_translate_operand` rule 3 returns numeric literals
   as written), so the same octal hazard exists in the statement emitter (`MOVE 09 TO WS-N` → `wsN = 09;`,
   reproduced; no corpus source has such a `MOVE`).
5. **`MOVE SPACES TO X`** emits an undeclared identifier (`wsS = spaces;`, reproduced — figurative constants
   are not handled in `_translate_operand`); no corpus source has a `MOVE` of a figurative constant.
6. `VALUE` on a group item is discarded by the parser (none in the corpus); multi-value `VALUE` lists on
   elementary items are not modelled; `OCCURS`/`REDEFINES` storage is not represented (each REDEFINES
   member is a separate Java field, so an initializer on the base item is not visible through its overlay).
7. `DataModelElement.initial_value` in the architecture model is still never populated.

## 6. Files

`app/parser/semantic/symbols.py`, `app/parser/semantic/symbol_collector.py`,
`app/backend/java/value_initializer.py` (new), `app/backend/java/generator.py`,
`app/java_modernization/architecture/builder.py`, `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V19`),
`tests/backend/test_java_value_initializer.py` (new, 78 tests), `tests/java_modernization/test_architecture.py`
(+2), `tests/dataset/test_mmim_v2_dataset.py` (V19 pins + §3r, 7 tests),
`tests/dataset/test_instruction_adapter_v2.py`, `tests/golden/{arithmetic,combined_program,if_else,perform_until}.java`
(5 lines), `tests/integration/test_pipeline.py` (2 lines), `tests/regression/fixtures/arithmetic/add.json`
(2 lines), `tests/backend/test_java_go_to_translation.py` (one stale docstring sentence),
`data/dataset/mmim-v2/**` (regenerated v19).
