# MMIM — leading-decimal-point numeric `VALUE` literals (Stage 22, no generator change: `mmim-gen-v20`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v20` (unchanged — see §6)

Stage 21 fixed signed `VALUE` literals by joining a bare `+`/`-` token to the `NUMBER` that follows it, and
recorded that `VALUE .50` and `VALUE -.50` were still broken: `.50` dropped the item, and `-.50` kept it with
the garbage value `'-'`. This document is the investigation and the fix for leading-decimal-point literals.

## 1. Exact token streams (measured before any edit)

`Tokens after VALUE` are `(type, lexeme)`; each row is `01 A PIC S9(3)V99 <clause>.` followed by
`01 B PIC 9 VALUE 1.` so that damage to the *next* item is visible.

| Clause | Tokens after `VALUE` | Pre-fix result |
|---|---|---|
| `VALUE .50` | `PERIOD '.'`, `NUMBER '50'`, `PERIOD` | **item A dropped** (only `B` parsed) |
| `VALUE -.50` | `UNKNOWN '-'`, `PERIOD '.'`, `NUMBER '50'`, `PERIOD` | item A **kept with value `'-'`** |
| `VALUE +.50` | `UNKNOWN '+'`, `PERIOD '.'`, `NUMBER '50'`, `PERIOD` | item A **kept with value `'+'`** |
| `VALUE 0.50` | `NUMBER '0.50'`, `PERIOD` | `'0.50'` ✓ |
| `VALUE -0.50` | `UNKNOWN '-'`, `NUMBER '0.50'`, `PERIOD` | `'-0.50'` ✓ (Stage 21) |
| `VALUE +000450000.00` | `UNKNOWN '+'`, `NUMBER '000450000.00'`, `PERIOD` | `'+000450000.00'` ✓ (Stage 21) |
| `VALUE + .50` (detached) | same types/lexemes as `+.50`; the `.` starts 2 columns after the sign, not 1 | item A **kept with value `'+'`** |

In the `-.50` / `+.50` / `+ .50` rows the item survives only by accident: the bare sign is taken as the whole
literal and the *period of the leftover `.50`* is then accepted as the item terminator, leaving `50.` in the
stream, which the item loop reports as an invalid level number (`SYN005`).

## 2. Why `.50` is not one numeric literal, and the parser path

* **Lexer.** `_read_number` (`app/parser/lexer/lexer.py`) is entered only when the current character is a digit,
  and `_at_decimal_point` accepts a `.` only *after* digits (`12.50`), when a digit follows it. A `.` that
  *starts* a token is not a digit, so it falls to the single-character symbol table (`"." → PERIOD`), and `50`
  is then read as its own `NUMBER`. Both tokens keep their exact source offsets.
* **Parser.** `DataDivisionParser._parse_elementary_or_group`, after the picture and any unmodelled clauses: on
  `VALUE` it consumes `VALUE`, an optional `IS`, then takes **exactly one token** as the literal. For `.50` that
  token is the `PERIOD`, so `value` would be `'.'`, and `_expect_period` then finds `NUMBER '50'` where a `PERIOD`
  is required → `ParserError("expected '.' to terminate data item, got '50'")`. The item loop catches it and
  `record_and_synchronise(…, code="SYN005")` abandons the item — no AST node, symbol, or Java field. For a signed
  form Stage 21 already joins `sign + NUMBER`, but `sign + PERIOD + NUMBER` had no branch.

## 3. Parser recombination or lexer change?

**The parser can recombine safely; no lexer change is needed.** Reasons:

1. The lexer preserves precise offsets, so "directly against" is decidable: `PERIOD` at offset *o* and
   `NUMBER` at *o+1* on the same line.
2. COBOL's own rule (quoted in `_at_decimal_point`): a *terminating* period is always followed by whitespace.
   A `PERIOD` that is directly against digits at the position where a literal is expected can therefore only be a
   decimal point. (Terminators after a literal — `VALUE 5.` / `VALUE .5.` — are never at the literal position.)
3. At the literal position after `VALUE [IS] [sign]`, a `PERIOD` could previously never be valid.

A lexer change (emit `NUMBER('.50')`) was rejected: it would change tokenization for **every** `.<digit>`
in every context, not just this clause — including places that fail today and would silently change behavior
(§5), and it would touch the token-stream contract that `test_lexer_numeric_prefixed_names.py` and
`test_decimal_and_compound_condition_fix.py` pin (`+`/`-` are separate `UNKNOWN` tokens; `12.50` is one token).

## 4. Corpus occurrences

**None.** Searched: every `.cbl`/`.cob`/`.cpy` in the repo (159 files, excluding `.venv` and the runtime
`workspace/`), the 45 loaded corpus records (code columns only, strings and comments excluded, for *any* token
beginning `.<digit>` — not just after `VALUE`), and every Python/Markdown/JSON/TXT under `app`, `tests`,
`scripts`, `examples`. Zero hits for `VALUE [IS] [sign] .digits` in all of these, and zero for any token starting `.<digit>` in the
COBOL sources. (The only mentions are in Stage 21/22 docs.) So this fix cannot change any generated MMIM output.

## 5. Does the same token pattern affect other parser paths? (read-only probe; nothing here was changed)

| Construct | Result today | Note |
|---|---|---|
| `MOVE .5 TO WS-A` | `SYN005 expected source operand after MOVE` + `SYN001` | statement dropped, explicit |
| `ADD .5 TO WS-A` | `SYN005 expected operand after ADD` + `SYN001` | statement dropped, explicit |
| `IF WS-A > .5 …` | `SYN005 expected operand for IF condition` + `SYN001` | statement dropped, explicit |
| `MOVE 0.5 TO WS-A` (control) | parses (`source='0.5'`) | |
| `PIC .99` | `SYN005 expected picture string after PIC … got '.'` | item dropped |
| `88 X VALUE .5.` | `SYN005 expected literal after VALUE for condition 'X'` | entry dropped |
| `VALUE 5. 01 B …` (terminator, then item, same line) | both items parse | period is a terminator |

All fail with explicit diagnostics (not silently wrong), and all are outside this stage's scope. They are
re-asserted as *unchanged* by the new tests, so the fix is shown not to leak into them.

## 6. The fix (parser only)

`app/parser/syntax/data_parser.py`: two module-level helpers and an extended branch in the `VALUE` clause.

* `_adjacent(first, second)` — same line and `second.offset == first.offset + len(first.lexeme)`.
* `_is_fraction(point, digits)` — `point` is a `PERIOD`, `digits` is a `NUMBER` whose lexeme is all digits
  (`str.isdigit()`, so `.5.5` — `PERIOD` + `NUMBER('5.5')` — is *not* a fraction), and they are adjacent.
* The `VALUE` branch, after the single literal token is consumed:
  * **sign** (`UNKNOWN '+'/'-'`): directly-adjacent `NUMBER` → join (Stage 21, unchanged); else directly-adjacent
    fraction (`.` + digits) → join as `sign + "." + digits` (**new**: `-.50`, `+.50`); else, if the next token is
    a `PERIOD`, raise `ParserError("expected a numeric literal directly after the sign …")` (**new**, see below);
  * **`PERIOD`** followed by a directly-adjacent all-digit `NUMBER` → `"." + digits` (**new**: `.50`).

Result literals are raw lexemes: `.50`, `-.50`, `+.50`. They flow `ElementaryItemNode.value` →
`VariableSymbol.value` → Stage 20's `translate_value_literal`, which already handled a leading sign and a missing
integer part, giving Java `0.50`, `-0.50`, `0.50` (never `.50`, never a leading `+`).

**Detached forms.** COBOL requires the sign, and the point, to sit directly against the digits. `VALUE + 5`,
`VALUE + .50`, `VALUE . 50` are therefore *not* literals. `+ 5` and `. 50` already failed (item abandoned,
`SYN005`) and are unchanged, including their diagnostic text. `+ .50` / `-.` were the one hole: the bare sign was
taken as the value and the detached period as the terminator, so the item was **kept with the garbage value
`'+'`** — the same class of defect as `-.50` before this stage. Leaving it would have meant "fixing" `-.50`
while `- .50` still produced junk, so an un-joined sign followed by a period is now rejected like every other
detached form (item abandoned with `SYN005`, next item still parses). This is the only behavior change beyond
the newly accepted literals, and it applies only to input that was never valid.

Why this cannot regress existing `+`/`-`/decimal parsing:
* the change lives entirely inside the elementary-item `VALUE` branch — the lexer, procedure/arithmetic parsing,
  level-88 entries and picture reading are untouched (re-asserted in tests);
* ordinary decimals (`0.50`, `-0.50`, `000450000.00`), integers, strings and figurative constants never enter
  the new branches (tested unchanged, along with all 31 Stage 21 tests, unmodified);
* unsigned terminators (`VALUE 5.`, `VALUE .5.`) keep their period, because the next token is not directly
  against it (tested).

## 7. Verification

**Isolated pre-fix proof.** The new tests were run on a byte-copy of the pre-fix tree, `cwd` rooted there
(`app.__file__` inside the copy; the fix confirmed absent). **22 of the 55 new tests fail**: every
`.50`/`-.50`/`+.50`/`IS …` literal case (10), the item-neighbour, no-syntax-error, usage-clause, symbol-table,
Java-field and executed-Java tests, the terminator test, the sign-message test, and 4 of the 8 detached/incomplete forms
(`+ .50`, `- .50`, `IS + .50`, `-.` — the ones that used to keep a garbage value). The 33 that pass on both trees are
the intended guards: lexer token streams (6), other `VALUE` forms incl. `0.50`, `-0.50`, `+000450000.00`, strings
and figuratives (18), the four detached forms that already failed, `+ 5` keeping its Stage 21 message, malformed
`.5.5`, procedure/88-level/`PIC .99` unchanged, and the corpus containing no leading-decimal `VALUE`.
The 31 Stage 21 tests pass on both trees.

**Executed behavior** (real `javac`/`java`, nothing seeded): a program with `.50`, `-.50`, `+.50`, `0.50`, `-0.50`,
`.0125`, `+000450000.00`, `'ABC'`, `SPACES` compiles, and its fields hold
`0.5 / -0.5 / 0.5 / 0.5 / -0.5 / 0.0125 / 450000.0 / "ABC" / ""`.

**Real corpus before/after (45 sources, per-source fingerprint: AST items, syntax/semantic/backend diagnostics,
IR instruction count, Java text, `javac`):** the pre-fix snapshot was taken from the isolated baseline tree
(`app.__file__` inside it). **Zero** fingerprints change; all 45 Java texts are byte-identical; 413 data items and
138 syntax diagnostics before and after; `javac` **41/45 → 41/45** (the same 4 FILE SECTION failures).

**Dataset.** Because no generated output changes, `mmim-gen-v20` is **not** bumped and `mmim-v2` is not
regenerated. That was verified rather than assumed: two independent regenerations at `mmim-gen-v20` are
byte-identical to each other, to the on-disk dataset, and to a snapshot of the dataset taken before this stage
(SHA-256 over all 12 files, `validation_report.json` compared without its embedded `path`). Unchanged: 351
examples, splits 226/71/54, leakage 0 errors / 5 warnings, benchmark leakage clean (0 overlap), 157 rules.

## 8. Independent gaps found, reproduced, NOT fixed

1. Leading-`.` operands in **procedure statements** (`MOVE .5`, `ADD .5`, `IF … > .5`) and in `PIC .99` still
   fail with explicit diagnostics (§5); fixing them needs either a lexer change or per-parser recombination.
2. *(Resolved in Stage 23, docs/MMIM_LEVEL88_VALUE_FIX.md.)* **Level-88** `VALUE`/`VALUES` with a signed or leading-decimal literal was dropped with `SYN005` — a
   different production (`_parse_condition_name`), separable from this path and not needed by it.
3. Signed literals in procedure statements (`MOVE -5` → source `'- 5'` → Java `x = f5;`), `COMPUTE`,
   `COMP`/`COMP-3` semantics, level-88 Java representation, `String ==`, `MOVE 09`, `MOVE SPACES`,
   `DataModelElement.initial_value`, PERFORM semantics, `GO TO … DEPENDING ON`, unsupported IF headers and FILE
   SECTION declarations remain as recorded in earlier stages.

## 9. Files

`app/parser/syntax/data_parser.py`, `tests/parser/test_leading_decimal_value_literal.py` (new, 55 tests),
`docs/MMIM_LEADING_DECIMAL_VALUE_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
`docs/MMIM_SIGNED_VALUE_FIX.md` (resolution pointer for its §7.1). No dataset file, generator version, backend,
lexer, or existing test changed.
