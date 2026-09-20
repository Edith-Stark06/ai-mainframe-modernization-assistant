# MMIM — level-88 `VALUE` parsing and Java representation (Stage 23, `mmim-gen-v21`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v21`

Stages 21 and 22 fixed signed and leading-decimal `VALUE` literals on *elementary* items and recorded that the
same forms were still dropped on level-88 condition-names (`88 X VALUE -1.`). Stage 20 recorded that level-88
entries were emitted as `String` storage fields. This document is the investigation and the fix for both.

## 1. The level-88 pipeline, traced end to end (before any edit)

| Stage | Location | What a level-88 entry is / does |
|---|---|---|
| Lexer | `app/parser/lexer/lexer.py` | No special handling. `-1` is `UNKNOWN '-'` + `NUMBER`; `.5` is `PERIOD` + `NUMBER`; `IS`, `ARE` are `IDENTIFIER`s. |
| Parser | `DataDivisionParser._parse_condition_name` | `VALUE` takes one literal, `VALUES` a run of literals; a literal must be `STRING`/`NUMBER`/`IDENTIFIER`/`KEYWORD`. `THRU` is rejected on purpose. Builds `ConditionNameNode(value, values)`. |
| AST | `app/parser/ast/data_items.py` | `ConditionNameNode`: `value` (single) and `values` (tuple of every literal). It is **metadata**: no `picture`. |
| Cross-division | `program_parser._collect_condition_names` → `ParserState.known_condition_names` | Lets the procedure parser recognise a bare `IF NAME` as a condition-name reference. |
| Procedure parser | `procedure_parser.py` | `IF NAME` / `IF NOT NAME` → `condition_operator` sentinel `IS-TRUE` / `IS-FALSE`, `left == right == NAME`. |
| Symbols | `symbol_collector.visit_condition_name` | Registers `VariableSymbol(level=88, picture=None)` (the values are *not* copied onto it); `TypeBuilder` gives it `GroupType`. |
| IR | `IRBuilder` | `IRIf(left=NAME, operator="IS-TRUE", right=NAME)`. |
| Backend | `control_flow_emitter` | `IS-TRUE`/`IS-FALSE` are not in `SUPPORTED_OPERATORS` → `BE007`, the guarded block is **omitted** with a `// TODO`. Pinned by `test_java_if_emission_fix.py` / `test_extra_conditions_java_fix.py`. |
| Backend fields | `build_fields_from_symbols` | Turned *every* `VariableSymbol` — including level 88 — into a field: `GroupType` → `private String isDep;`. |
| Behavioral | `extractor._collect_condition_name_values/_parents` | Reads level-88 entries straight off the serialized AST: a name → parent map ("a level-88 condition-name is a condition on its parent data item") and `values` as opaque strings for boundary-value generation. |

## 2. Reproduced failures (measured)

`88 C <clause>.` under `01 P PIC S9V99 VALUE 1.`:

| Clause | Pre-fix |
|---|---|
| `VALUE -1`, `+1`, `-0.5` | entry **dropped**, `SYN005 expected literal after VALUE … got '-'` |
| `VALUES -1 -2` | entry dropped, `SYN005 … VALUES … got '-'` |
| `VALUE .5`, `VALUE -.5` | entry dropped, `SYN005` **plus a spurious second `SYN005`** (`expected data-name after level 5, got '.'` — the leftover `5.` read as a level number) |
| `VALUE IS 1` | entry dropped, `SYN005 expected '.' to terminate data item, got '1'` (elementary items already accept `IS`) |
| `VALUES IS 1 2` | entry **kept with `values = ('IS', '1', '2')`** — the noise word silently captured as a *value* |
| `VALUE 'D'`, `1`, `01`, `0.5`, `ZERO`, `SPACES`, `VALUES 1 2 3`, `VALUES 'A' 'B'` | parse correctly |
| `VALUE 1 THRU 5`, `VALUES 1 THRU 5`, `VALUES 1, 2, 3` | dropped (`THRU` is deliberately unsupported; commas unsupported) |

The last row's forms are **not** touched (see §6). The corpus has exactly **11** level-88 entries in the whole
repo, all in `condition_names_88.cbl`, all plain string values (`'D'`, `VALUES 'D' 'W' 'T' 'F'`, …); no source
uses a signed, leading-decimal, `IS`/`ARE` or figurative 88 value. So the parser part cannot change any
generated output; the Java-representation part does.

## 3. Decision: condition metadata, not storage fields

Evidence from the existing architecture and tests (nothing new invented):
1. The AST models a level-88 as a `ConditionNameNode` with `values`, not as a storage item.
2. The behavioral extractor already treats it as *a condition on its parent* (name → parent map; several
   conditions constrain one shared variable) and reads `values` as the condition's domain.
3. The procedure parser resolves `IF NAME` through `known_condition_names`; the IR carries it as the
   `IS-TRUE`/`IS-FALSE` sentinel; the backend deliberately refuses to translate that sentinel (`BE007`), with
   tests pinning it, including on the real `condition_names_88.cbl:54`.
4. The semantic layer must keep the symbol (`test_condition_name_registered`; reference resolution needs the name).
5. **No test pins an 88 Java field**, and no generated statement ever reads or writes one.
6. In COBOL a condition-name has no storage of its own; a `private String isDep;` implied state that does not
   exist (always `null`, never assigned).

So: **no Java field for a level-88 symbol.** The symbol stays in the symbol table, and the literals stay on the
AST. Rejected alternatives: keeping the fields (wrong); translating `IS-TRUE` into Java boolean helpers/`IF`
expressions — a real feature (needs parent + values on the symbol, string-vs-numeric comparison rules, `NOT`,
`AND`/`OR`, and it collides with the separate `String ==` issue), i.e. a new architecture, left as a documented
gap.

## 4. The fix

**Parser** (`app/parser/syntax/data_parser.py`): a new `_read_condition_literal(state, name, keyword)` used by
both the `VALUE` and `VALUES` branches. It accepts what was always accepted, plus — joined only when each piece
sits directly against the next (`_adjacent`, `_is_fraction`, `_NUMERIC_SIGNS` from Stages 21/22) — `sign NUMBER`
(`-1`), `. NUMBER` (`.5`) and `sign . NUMBER` (`-.5`). A sign not joined to a number is rejected with the *same*
message as before (`expected literal after VALUE … got '-'`). Also new: the optional noise words —
`VALUE IS 1`, `VALUES IS|ARE 1 2` — are skipped instead of dropping the entry / captured as values. In the
`VALUES` loop a `PERIOD` ends the clause **unless** it is the point of the next leading-decimal literal
(`VALUES 1 .5` → `('1', '.5')`); a *detached* period (`VALUES 1 . 5`) is still a terminator, exactly as before.
`THRU`/`THROUGH` and comma separators remain rejected. The elementary-item `VALUE` code (Stages 21/22) is
**not modified**.

**Backend** (`app/backend/java/generator.py`): `build_fields_from_symbols` skips `level == 88`
(`_CONDITION_NAME_LEVEL`) before the type/`BE002`/`BE003` checks, with **no diagnostic** (skipping is by
design, not a mapping failure), so backend diagnostic counts are unchanged. Every other level is unchanged.

**Version:** `MMIM_GENERATOR_VERSION_V21` (`app/dataset/version.py`) and `mmim-v2` regenerated (§5).

### Consequence outside the backend (checked, no code needed)
`architecture/builder.py` derives `data_model` from the generated `private …;` lines, so the DTO now lists only
real WORKING-STORAGE data (8, was 19) — the correct effect; its `_FIELD_RE` (Stage 20) needed no change.

## 5. Verification

**Isolated pre-fix proof.** All new and moved tests were run on a byte-copy of the pre-fix tree, `cwd` rooted
there (`app.__file__` inside the copy; both fixes confirmed absent; the dataset test copy pinned to V20).
**50 fail**: 30 in `tests/parser/test_level88_value_literals.py` (every signed / leading-decimal / `IS` /
`ARE` / mixed-list form and the run-of-entries, propagation and noise-word tests), 14 in
`tests/backend/test_level88_java_representation.py` (no-field unit tests, the pipeline field test, executed
Java, the real source, and the 4 `IF` tests whose 88 declaration used to be dropped), 5 dataset pins, and the one
Stage 20 pin that used to assert an 88 field. The tests that pass on both trees are the intended guards: plain
`'D'`/`1`/`ZERO`/`SPACES` forms, the elementary-item forms of Stages 21/22, lexer token streams, the
terminator/period rules, the deliberately-rejected forms, and the corpus AST.

**Executed Java** (real `javac`/`java`, nothing seeded): a program with 7 condition-names of every form
compiles and its class has exactly the storage fields `wsCode="D"`, `wsN=1`, `wsOut=null`; the same with an
omitted `IF <condition>` still compiles; the real `condition_names_88` compiles and has exactly its 8 storage
fields (`txTypeCode="D"`, `txAmount=2500.0`, …).

**Real corpus before/after (45 sources, fingerprint: AST items, syntax/semantic/backend diagnostics, IR, Java
text, `javac`; "before" taken from the isolated baseline tree):** exactly **1** source changes,
`t_condition_names_88` — Java fields 19 → 8 (43 → 32 lines), and the only differing lines are the 11
`private String <condition>;` declarations. AST items (413), syntax diagnostics (138), semantic/backend
diagnostic counts, IR and `// TODO` counts are identical; `javac` **41/45 → 41/45**; corpus fields 412 → 401.

**Dataset (`mmim-gen-v21`):** only **2 examples** change, both for `t_condition_names_88`: `cobol_to_java`
(`expected_output.java`, still `compiles: true`) and `transformation_planning` (`data_model` 19 → 8, DTO
evidence "19 → 8 WORKING-STORAGE field(s)", new architecture id/hash). The embedded AST of *every* example is
identical (all 11 conditions and their values are still on the AST). Unchanged: 351 examples, splits 226/71/54
and source→split assignment, leakage 0 errors / 5 warnings, benchmark leakage clean, 157 rules (0 changed), 41
compiling, statuses 345/2/4. Two independent regenerations are byte-identical to each other and to the on-disk
dataset (SHA-256; `validation_report.json` compared without its embedded `path`).

**Existing pins that moved (all direct consequences):** the uninitialized-field count 137 → 126 (Stage 20 and
21 dataset pins, 11 fewer fields); the Stage 20 `test_items_without_a_value_clause_stay_uninitialized` now asserts
the 88 field is *absent* rather than "has no initializer"; and Stage 22's guard that 88 `.5` stays dropped is
narrowed to `PIC .99` (the 88 half is now covered here). Nothing was deleted or loosened.

## 6. Remaining gaps (reproduced, NOT fixed)

1. *(Resolved in Stage 24, `mmim-gen-v22`, docs/MMIM_STRING_COMPARISON_FIX.md, for every form that can be translated provably correctly.)* **`IF <condition-name>` is still untranslatable** (`BE007`, block omitted). A real translation needs the
   parent item and value list on the symbol, string-vs-numeric equality rules (entangled with the separate
   `String ==` issue), `NOT`, and compound conditions — a feature, not part of this stage.
2. `SET <condition-name> TO TRUE` is an unsupported statement (`SYN100`).
3. `VALUES a THRU b` ranges (deliberately rejected, with a clear message), comma/semicolon-separated value
   lists, and a bare `VALUE 1 2` (two literals under singular `VALUE`) are not supported.
4. The symbol for an 88 entry still carries `GroupType` and no values (harmless now that the backend ignores it).
5. A leading `.` in procedure operands (`MOVE .5`) and in `PIC .99`, signed procedure literals, `COMPUTE`,
   `COMP`/`COMP-3` semantics, `String ==`, `MOVE 09`, `MOVE SPACES`, `DataModelElement.initial_value`, PERFORM
   semantics, `GO TO … DEPENDING ON`, unsupported IF headers and FILE SECTION declarations remain as recorded.

## 7. Files

`app/parser/syntax/data_parser.py`, `app/backend/java/generator.py`, `app/dataset/version.py`
(`MMIM_GENERATOR_VERSION_V21`), `tests/parser/test_level88_value_literals.py` (new, 81 tests),
`tests/backend/test_level88_java_representation.py` (new, 21 tests), `tests/dataset/test_mmim_v2_dataset.py`
(V21 pins, §3t — 4 tests, and two count pins 137 → 126), `tests/dataset/test_instruction_adapter_v2.py`,
`tests/backend/test_java_value_initializer.py` (one assertion), `tests/parser/test_leading_decimal_value_literal.py`
(one test narrowed), `data/dataset/mmim-v2/**` (regenerated v21), `docs/MMIM_LEVEL88_VALUE_FIX.md` (this file),
`docs/MMIM_V2_DATASET_AUDIT.md`, and resolution pointers in `docs/MMIM_LEADING_DECIMAL_VALUE_FIX.md`,
`docs/MMIM_SIGNED_VALUE_FIX.md`, `docs/MMIM_VALUE_INITIALIZER_FIX.md`.
