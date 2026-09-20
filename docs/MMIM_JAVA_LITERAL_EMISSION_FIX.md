# Java backend: COBOL single-quoted string literals

Branch `feat/mmim-java-literal-emission` (from `feat/mmim-java-if-emission`). Follows
`docs/MMIM_JAVA_IF_EMISSION_FIX.md` §7, which named this the highest-leverage remaining gap.
`generator_version` `mmim-gen-v12` -> `mmim-gen-v13`; `dataset_version` stays `mmim-v2`.

## 1. Path traced before any code changed

```
COBOL   MOVE 'Y' TO WS-R          IF WS-CODE = 'ACH'
  lexer      _read_string keeps the delimiting quotes in the lexeme, either
             ' or ": STRING token lexeme = "'Y'" / "'ACH'"
  AST        MoveStatementNode.source = "'Y'" (raw token text, quotes included)
             IfStatementNode.condition_right = "'ACH'"
  IR         IRBuilder.build_operand(text):
               1. text.startswith('"') and endswith('"')  -> literal   (NO -- starts with ')
               2. _is_numeric_literal(text)                -> literal   (NO)
               3. else -> build_variable_reference(text)               <-- HERE
             build_variable_reference("'Y'"):
               canonical = "'Y'".upper() = "'Y'"   (upper() is a no-op on punctuation)
               symbol_table.lookup("'Y'")  -> None (not a real symbol)
               returns "'Y'" unchanged
             => IRMove(source="'Y'", ...) / IRIf(right="'ACH'", ...)
  Java       control_flow_emitter._build_condition / statement_emitter's
             emit_move etc. all call the one shared _translate_operand("'Y'"):
               1. startswith('"') and endswith('"')  -> NO
               2. re.match(numeric)                   -> NO
               3. else -> to_java_field_name("'Y'")  = "y"             <-- BUG
             => wsR = y;               // undeclared variable, javac error
             => if (wsCode == ach) {   // undeclared variable, javac error
```

Reproduced on the isolated pre-fix tree (`PYTHONPATH` pointing at a byte-copy of it):
`_translate_operand("'Y'")` -> `'y'`, `_translate_operand("'SKIPPED-ALPHA'")` -> `'skippedAlpha'`.
A three-statement program (`MOVE 'Y' TO WS-R`, `MOVE "HELLO" TO WS-R`, `IF WS-R = 'ACH' DISPLAY
'MATCHED'`) generated `wsR = y; wsR = "HELLO"; if (wsR == ach) { System.out.println(matched); }` and
failed `javac` with `cannot find symbol` for `y`, `ach`, `matched`.

**Root cause is precisely `IRBuilder.build_operand`'s classification** (recognises only `"`, not
`'`) **feeding `_translate_operand` an operand it also only half-recognises.** Both layers are
missing the same case, but a fix confined to `_translate_operand` alone is complete: because a
single-quoted operand that reaches it took the `build_variable_reference` path, and that function's
only transformation is `.upper()` on the whole token (quotes included) — a no-op for punctuation and
already-uppercase letters — the exact original quoted text (`"'Y'"`, `"'SKIPPED-ALPHA'"`, …) survives
unchanged all the way to `_translate_operand`. Verified against the real corpus, not assumed: every
single-quoted literal in all 45 sources is already upper-case (`grep -rhoE "'[^']*'" data/sources/
phase6-v2/*.cbl | grep -E "[a-z]"` returns nothing).

## 2. The fix (one function, `app/backend/java/statement_emitter.py`)

`_translate_operand` gains one new rule, ordered next to the existing double-quote rule (a COBOL
identifier can never itself contain a quote character, so ordering relative to the numeric/identifier
rules does not matter):

```python
# 2. Single-quoted string literal (COBOL's own delimiter)
if operand.startswith("'") and operand.endswith("'") and len(operand) >= 2:
    return f'"{_escape_java_string_content(operand[1:-1])}"'
```

`_escape_java_string_content` escapes only backslash and double-quote. Nothing more is needed:
the lexer that produced the token forbids an embedded newline or carriage return (raises
`LexerError: unterminated string literal`), so the content is always one line, and it can never
contain the literal's own delimiter (`'`) since the lexer stops scanning at the first one — so
`_read_string` never even produces a token whose content has an unescaped `'` in the first place
(COBOL's doubled-quote escape, `'IT''S'`, is not supported by this lexer at all; a separate,
pre-existing, out-of-scope lexer gap — see §6). Verified against a literal containing an embedded
double quote and one containing a backslash: both produce syntactically valid, correctly-valued
Java string literals.

Double-quoted literals, numeric literals, and unquoted-identifier translation are byte-for-byte
unchanged (all three existing rules are untouched, only reordered by one). Every emitter that calls
`_translate_operand` — `emit_move`, `emit_display`, `emit_call`, and `control_flow_emitter._build_condition`
(shared by `emit_if` and `emit_perform_until`) — gains the fix automatically, since it is the single
shared translator (confirmed by grepping every call site).

## 3. Tests

`tests/backend/test_java_literal_emission_fix.py` — 39 tests: every real corpus literal *form*
(single letter, hyphenated code, phrase with spaces, punctuation, digits-that-look-numeric, empty
literal, a lone space); double-quoted/numeric/identifier behaviour unchanged; a 1-character `"'"`
operand (not a real lexer output, but the length guard is tested anyway); backslash and
embedded-double-quote escaping; the full COBOL -> AST -> IR -> Java pipeline for MOVE, DISPLAY, a
plain IF and a compound IF; a `javac` compile of pipeline output; and the real corpus (7 real forms
across 5 sources, plus a structural-`javac`-error check across all 5 previously-unbalanced sources).
**25 of the 39 fail on the isolated pre-fix tree**; the 14 that pass are the unchanged-behaviour
guards (double-quoted/numeric/identifier translation never touched this rule).

Two assertions in the prior cycle's `tests/backend/test_java_if_emission_fix.py` used `\S+` as a
placeholder for "some operand" in a real-corpus regex, written when a single-quoted literal still
translated to a bare, space-free identifier. `AUTH-OUT-RESP-CODE = ' '`'s translated value now
contains a literal space, so `\S+` no longer matches; both were updated to `"[^"]*"` (a Java string
literal, which may contain spaces) — the patterns still assert only structure (both operands present,
correct connector), never the literal's translated value, which is this file's job. Every other
pre-existing backend test passes unmodified.

## 4. Real-corpus before/after (45 sources, isolated trees, real `javac 25.0.3`)

"Before" = a byte-copy of the pre-fix (`mmim-gen-v12`) `app/` tree in a subprocess with `PYTHONPATH`
pointing at it; "after" = the repository. The snapshot records `app.__file__`, the emitter's
SHA-256, and whether `_escape_java_string_content` exists; the comparison asserts they differ
(`abc64b28cd23` vs `1a760e088ed5`).

| Measure | Before | After |
|---|---:|---:|
| Sources whose generated Java changed | — | **7 / 45** |
| Java with balanced braces | 45 / 45 | 45 / 45 (unaffected — already fixed in v12) |
| `BE007` diagnostics anywhere | 0 | 0 (unaffected) |
| `javac` compiles | 38 / 45 | **41 / 45** |

The 7 changed sources — 2 more than the "5 previously unbalanced" set named in the brief, because a
single-quoted literal inside a *syntactically valid* (already-balanced) statement, e.g. a plain
`MOVE`, is also `cannot find symbol`, not a brace-balance problem, so it was not visible in the prior
cycle's brace count:

| Source | Change | `javac` before -> after |
|---|---|---|
| `t_batch_acct_update` | `y` -> `"Y"` (MOVE and IF) | False -> False (FILE SECTION fields) |
| `t_daily_trans_report` | `y` -> `"Y"`, `highrisktransactionflagged`/`standardtransactionsettled` -> their real phrases | False -> False (FILE SECTION fields) |
| `t_fallthrough_flow` | `skippedAlpha` -> `"SKIPPED-ALPHA"` | **False -> True** |
| `t_goto_spaghetti` | `started`/`completed` -> `"STARTED"`/`"COMPLETED"` | **False -> True** |
| `t_inventory_extract` | `y` -> `"Y"` (x2) | False -> False (FILE SECTION fields) |
| `t_payroll_file_post` | `y` -> `"Y"` (x2) | False -> False (FILE SECTION fields) |
| `t_policy_redefines` | `auto`/`life` -> `"AUTO"`/`"LIFE"` | **False -> True** |

3 sources newly compile (38 -> 41). The other 4 — the same 4 that stayed non-compiling in the prior
cycle, plus the newly-visible `t_inventory_extract`/`t_payroll_file_post` — were re-checked directly
with `javac`: **every remaining error is `cannot find symbol` for either an undeclared FILE SECTION
field** (`fdAcctBal`, `fdTxVal`, `fdMinThreshold`, `fdOutEmpId`, …) **or a `READ ... AT END`-clause
identifier the reference resolver could not fully parse** (`wsEofFlagnotatend`, `wsEofendRead`,
`wsInvEofendRead`, `wsPayEofendRead` — see §6). No structural error, and no single-quoted-literal
symbol, remains anywhere in the corpus.

No source outside these 7 changed (verified by comparing every source's Java SHA-256, not merely the
5 named ones).

## 5. Dataset regeneration (`mmim-gen-v13`)

`app/dataset/version.py::MMIM_GENERATOR_VERSION_V13`. Only the Java text changed, so only COBOL_TO_JAVA.

| | mmim-gen-v12 | mmim-gen-v13 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 |
| Examples changed | — | **7** (COBOL_TO_JAVA of the 7 sources; every other example byte-identical) |
| `compiles == True` | 38 | **41** |
| Ground truth (deterministic / executable_verified / reference) | 342 / 2 / 7 | **345 / 2 / 4** (3 sources moved `reference` -> `deterministic`) |
| VALIDATION_REASONING coverage | 36/45 | 36/45 |
| Source->split assignment | — | identical |
| Benchmark leakage | 0 | 0 |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |

Two independent full regenerations are byte-identical (`all.jsonl`, split files, `manifest.json`,
`split_manifest.json`, `leakage_report.json`, every `instruction/*` file); `validation_report.json`
differs only in its recorded output `path`. `benchmark-v1` and `mmim-v1` are untouched.

## 6. New independent gaps (reproduced, documented, NOT fixed)

> **Gap 2 below is resolved in `mmim-gen-v14`** by `docs/MMIM_READ_AT_END_PARSING_FIX.md`: a dedicated
> `_skip_read_statement` now protects `READ`'s `AT END`/`NOT AT END` clauses the same way `EVALUATE`'s
> `WHEN` clauses were already protected. That same investigation found a further, independent CFG
> defect (empty-paragraph `PERFORM` targets misclassified as unresolved/external) -- see that
> document's §6; still not fixed. Gaps 1, 3 and 4 are unchanged.

1. **`IRBuilder.build_variable_reference` uppercases a single-quoted literal's whole token,
   content included, when it is misclassified as a variable reference.** Harmless today only
   because every real corpus literal is already upper-case (verified in §1); a future *mixed-case*
   single-quoted literal (e.g. `'Mixed Case'`) would have its content silently corrupted to
   `'MIXED CASE'` before it ever reaches the Java backend. This lives in `app/ir/builder.py`, not
   the backend, so it is out of this task's scope (a genuine fix is
   `build_operand` recognising `'...'` as a literal alongside `"..."`, matching what the AST already
   preserves — the IR classification gap this task's backend-only fix works around).
2. **`READ ... AT END` / `NOT AT END` clause parsing merges the clause keywords into the target
   identifier** (`ReferenceResolverVisitor: undefined variable: 'WS-EOF-FLAG NOT AT END'`), producing
   Java identifiers like `wsEofFlagnotatend`/`wsEofendRead`/`wsInvEofendRead`/`wsPayEofendRead` that
   have no declared field. Confirmed pre-existing (present on the isolated pre-fix tree too, with the
   identical mangled names) and unrelated to string-literal translation — a parser-layer defect, out
   of scope (parser tokenization is explicitly untouched by this task). It is the reason
   `t_batch_acct_update`, `t_daily_trans_report`, `t_inventory_extract` and `t_payroll_file_post`
   still fail `javac` even with every literal now correct.
3. **Undeclared FILE SECTION fields**, already named in `docs/MMIM_JAVA_IF_EMISSION_FIX.md` §7 — still
   the other half of why those same 4 sources do not compile.
4. `==` on the resulting Java `String` is reference equality, not value equality — already named in
   `docs/MMIM_JAVA_IF_EMISSION_FIX.md` §7 as a separate issue requiring type information the IR does
   not carry; not attempted here per the task's explicit instruction.

Still open from earlier cycles and untouched: the behavioral parser's `NOT ((a) AND (b))` limitation,
`_condition_variables` reading `IS-FALSE` as a variable, `IF <var> NOT = <literal>`, `PERFORM UNTIL`
recovery, decimal accumulator arithmetic, and the strategy-analyzer rationale.

## 7. Exact files changed (this task)

* `app/backend/java/statement_emitter.py` (`_escape_java_string_content`, `_translate_operand` rule 2)
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V13`)
* `tests/backend/test_java_literal_emission_fix.py` (new, 39 tests)
* `tests/backend/test_java_if_emission_fix.py` (2 real-corpus regex patterns updated, `\S+` -> `"[^"]*"`)
* `tests/dataset/test_mmim_v2_dataset.py` (V13 pins + §3l, 4 new tests; two prior cycles' "did not
  change" global-count assertions updated to the new, legitimately-changed totals, each with a
  comment explaining why and pointing at the test that verifies the new value)
* `tests/dataset/test_instruction_adapter_v2.py` (version bump)
* `docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
  `docs/MMIM_JAVA_IF_EMISSION_FIX.md` (resolution note)
* `data/dataset/mmim-v2/**` (regenerated)
