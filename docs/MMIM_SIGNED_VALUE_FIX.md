# MMIM — signed numeric `VALUE` literals (Stage 21, `mmim-gen-v20`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v20`

Stage 20 found, and deliberately did not fix, that `VALUE +000450000.00` makes the data-division parser
abandon the whole data item. Five `COMP-3` items of `t_packed_decimal` were affected, and this was the
actual cause of that source's `SYN005` (an earlier audit note had guessed a "`COMP-3`/`VALUE` ordering
interaction"). This document is the investigation and the fix.

## 1. Exact token streams (measured, before any edit)

`+` and `-` are `UNKNOWN` tokens in the lexer's single-character table (`app/parser/lexer/lexer.py`,
alongside `*`, `/`, `=`, `<`, `>`) — everywhere, because they are also the arithmetic operators. Tokens after
`VALUE` (`type`, `lexeme`):

| Source text | Tokens after `VALUE` | Parsed item (pre-fix) |
|---|---|---|
| `VALUE +000450000.00.` | `UNKNOWN '+'`, `NUMBER '000450000.00'`, `PERIOD` | **item dropped**, `SYN005 … got '000450000.00'` |
| `VALUE -000450000.00.` | `UNKNOWN '-'`, `NUMBER '000450000.00'`, `PERIOD` | **item dropped** |
| `VALUE +5.` / `VALUE -5.` | `UNKNOWN '+'/'-'`, `NUMBER '5'`, `PERIOD` | **item dropped** |
| `VALUE IS -5.` | `IDENTIFIER 'IS'`, `UNKNOWN '-'`, `NUMBER '5'`, `PERIOD` | **item dropped** |
| `VALUE + 5.` (detached) | identical to `+5` — the lexer keeps no whitespace | **item dropped** |
| `VALUE 000450000.00.` | `NUMBER '000450000.00'`, `PERIOD` | `value = '000450000.00'` ✓ |
| `VALUE ZERO.` | `IDENTIFIER 'ZERO'`, `PERIOD` | `value = 'ZERO'` ✓ |

The lexer behavior is a deliberate contract: `tests/parser/test_lexer_numeric_prefixed_names.py` pins both
`VALUE -1` → (`UNKNOWN '-'`, `NUMBER '1'`) and `B - C`. So a lexer fix (gluing the sign into the number) was
rejected: it would break that contract and change how every `A -5` / `A - 5` / `A + B` is tokenized.

## 2. Parser path and why the item disappears

`DataDivisionParser._parse_elementary_or_group` (`app/parser/syntax/data_parser.py`): after the picture it
skips unmodelled clauses (`COMP-3` → `SYN200`), then on `VALUE`: consume `VALUE`, consume optional `IS`, take
**exactly one token** `val_tok` as the literal (`value = val_tok.lexeme`), skip unmodelled clauses again, then
`_expect_period`. For a signed literal `val_tok` is the sign, so `value` would be `'+'`; the cursor is now on the
`NUMBER`, `_expect_period` finds no `PERIOD` and raises `ParserError("expected '.' to terminate data item, got
'000450000.00'")`. The item loop catches it and calls `record_and_synchronise(… code="SYN005")`, which skips to
the next period and returns **no node** — so no `ElementaryItemNode`, no `VariableSymbol`, no Java field, and
the recovered region is gone from the AST, coverage, and every downstream artifact.

## 3. Affected occurrences in the 45-source corpus

Exactly **5**, all `+`, all `PIC S9(9)V99 COMP-3`, all in `data/sources/phase6-v2/packed_decimal.cbl`
(lines 11–15): `BEGINNING-BALANCE +000450000.00`, `PERIOD-DEBITS +000085200.50`, `PERIOD-CREDITS
+000062100.25`, `ENDING-BALANCE +000000000.00`, `VARIANCE-AMOUNT +000000000.00`. No negative literal, no `IS`
form, no signed level-88 value, and no other signed `VALUE` anywhere in the corpus or the repo's `.cbl` files
(regex over every source, comments excluded). Before the fix `t_packed_decimal` reported 16 syntax diagnostics
(`SYN003`×1, `SYN005`×5, `SYN100`×2, `SYN200`×8) and had 8 data items.

## 4. Could the same tokenization affect other syntax?

The *tokenization* does: any `+`/`-` is an `UNKNOWN` token, and the procedure division consumes them
differently. Measured (read-only probe, unchanged by this stage):

* `COMPUTE …` (any operators) is an unsupported statement (`SYN100`) — including the two `COMPUTE`s in
  `t_packed_decimal`.
* `SUBTRACT 1 FROM X`, `ADD B TO A` parse normally.
* **A signed literal in a procedure statement is mis-parsed**: `MOVE -5 TO WS-A` yields
  `MoveStatementNode(source='- 5')` and Java `wsA = f5;`; `ADD -1 TO WS-A` yields `left='- 1'` and `wsA += f1;`;
  `IF WS-A > -5 …` fails with "expected operand". No corpus source contains such a statement
  (regex over every source), so this is latent, independent, and **not fixed here**.

None of that shares a code path with the fix: the change lives entirely inside the elementary-item `VALUE`
branch of `_parse_elementary_or_group`, so it cannot alter how the procedure parser, the arithmetic parsers, the
lexer, or level-88 entries see `+`/`-`.

## 5. The fix

`app/parser/syntax/data_parser.py` only: new `_NUMERIC_SIGNS = {"+", "-"}` and, right after the single literal
token is consumed, *if* that token is an `UNKNOWN` `+`/`-` **and** the next token is a `NUMBER` on the same line
starting at exactly `sign.offset + 1`, the two are joined (`value = '+' + '000450000.00'`) and both consumed.

Why this cannot regress `+`/`-` parsing:
* It is inside the `VALUE` branch of a data item — no other grammar production reaches it.
* It only fires when the literal token *is* a bare sign, which before the fix could never produce a correct
  result (the item was always abandoned, or — for `-.50` — kept with the garbage value `'-'`).
* Unsigned, string and figurative literals never take the new branch (tested unchanged).
* **Adjacency is required.** COBOL requires the sign to sit directly against the digits, so a detached sign
  (`VALUE + 5`) is not silently accepted as `+5`; it fails exactly as before, same `SYN005`, and the next item
  still parses (tested).
* The lexer is unchanged (tested via the token stream), as are `test_lexer_numeric_prefixed_names.py` and every
  operator test.

Propagation needed no further change: the joined lexeme flows through `ElementaryItemNode.value` →
`VariableSymbol.value` → Stage 20's `translate_value_literal`, which already handled a leading sign
(`+000450000.00` → `450000.00`, `-000012.50` → `-12.50`, `-000000.00` → `0.00` with no negative zero, never a
leading `+` in Java). Type resolution already gave `PIC S9(9)V99 COMP-3` a `double`.

## 6. Verification

**Isolated pre-fix proof.** The new tests were run on a byte-copy of the pre-fix tree with `cwd` rooted there
(`app.__file__` confirmed inside the copy; the parser fix confirmed absent from it). **23 fail**: 17 in
`tests/parser/test_signed_value_literal.py` and 6 dataset pins. The 14 that pass on both trees are the
intended guards (unsigned/figurative/string literals unchanged, detached sign not joined, lexer token stream
unchanged, procedure statements unaffected, the corpus has exactly these 5 signed `VALUE`s).

**Executed behavior** (real `javac`/`java`, nothing seeded): `t_packed_decimal`'s generated Java compiles and its
fields hold `450000.0 / 85200.5 / 62100.25 / 0.0 / 0.0`; a synthetic program with `+7`, `-5`, `-000012.50`,
`+000000.00`, `-000000.00` holds `7 / -5 / -12.5 / 0.0 / 0.0` (never `-0.0`).

**Real corpus before/after (45 sources, per-source fingerprint: AST items, syntax/semantic/backend diagnostics,
IR instruction count, Java text, `javac`):** exactly **1** source changes, `t_packed_decimal` — AST data items
8 → 13, Java fields 8 → 13 (32 → 37 lines), syntax diagnostics 16 → 11 (all 5 `SYN005` gone; `SYN003`, `SYN100`,
`SYN200` unchanged). Semantic (0), backend (11) and IR (14) counts, `// TODO` count, and brace balance are
unchanged; `javac` **41/45 → 41/45** (the same 4 FILE SECTION failures). The other 44 sources are
fingerprint-identical. Corpus-wide: 408 → 413 data items, 143 → 138 syntax diagnostics (exactly the 5).

**Dataset (`mmim-gen-v20`):** 351 examples, splits 226/71/54, source→split assignment, leakage report (0 errors
/ 5 warnings), 157 rules (0 condition changes), 345/2/4 statuses, and the 41-compiling count are unchanged. Only
`t_packed_decimal`'s **8 examples** change (one per task type): AST `working_storage.items` 8 → 13 in the
embedded analysis; `cobol_to_java` gains the 5 `double` fields; `program_understanding` syntax diagnostics 16 →
11 and codes `[SYN003, SYN005, SYN100, SYN200]` → `[SYN003, SYN100, SYN200]`; `risk_classification` /
`modernization_strategy` `SYNTAX_ERROR` occurrences 6 → 1 and AST coverage 13/23 (0.5652) → 18/28 (0.6429);
`transformation_planning` `data_model` 8 → 13 (new architecture id/hash). Every changed field is a direct
consequence of the 5 recovered items. Two independent regenerations are byte-identical to each other and to the
on-disk dataset (SHA-256), except `validation_report.json`, which differs only in its embedded `path`.

Stage 20's exact-count pin moved 270 → 275 initializers (270 + the 5 recovered items) and is updated; nothing
else in the existing suite needed to change.

## 7. Independent gaps found, reproduced, NOT fixed

1. **Leading-decimal-point literals** (`VALUE .50`, `VALUE -.50`) — *resolved in Stage 22 (no dataset change;
   docs/MMIM_LEADING_DECIMAL_VALUE_FIX.md)*; as found: the lexer emits `PERIOD`, `NUMBER`. Unsigned
   `.50` drops the item (`SYN005 … got '50'`); signed `-.50` keeps the item with the garbage value `'-'` (no
   initializer is emitted for it, since `-` translates to nothing) and reports `SYN005` on the leftover. Not
   in the corpus.
2. *(Resolved in Stage 23, docs/MMIM_LEVEL88_VALUE_FIX.md.)* **Signed level-88 values** (`88 NEG VALUE -1.`, `VALUES -1 -2.`): the condition-name parser rejects the sign
   token and drops the entry with a clear `SYN005` ("expected literal after VALUE …") — explicit, not silently
   wrong. Not in the corpus, so untouched.
3. **Signed literals in procedure statements** (`MOVE -5`, `ADD -1`, `IF … > -5`) are mis-parsed (§4).
4. `COMPUTE` is an unsupported statement, so `t_packed_decimal`'s two `COMPUTE`s (and paragraph
   `1000-COMPUTE-ENDING-BALANCE`) remain empty stubs; the recovered items are declared and initialized but not
   yet *computed on* (`SYN100`×2 unchanged).
5. `COMP`/`COMP-3` usage is skipped with `SYN200` and not modelled, so a packed field is a plain Java `double`.

## 8. Files

`app/parser/syntax/data_parser.py`, `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V20`),
`tests/parser/test_signed_value_literal.py` (new, 31 tests), `tests/dataset/test_mmim_v2_dataset.py` (V20
pins, §3s — 5 tests, and the 270 → 275 pin), `tests/dataset/test_instruction_adapter_v2.py`,
`data/dataset/mmim-v2/**` (regenerated v20), `docs/MMIM_SIGNED_VALUE_FIX.md` (this file),
`docs/MMIM_V2_DATASET_AUDIT.md`, `docs/MMIM_VALUE_INITIALIZER_FIX.md` (resolution pointer for its §5.1).
