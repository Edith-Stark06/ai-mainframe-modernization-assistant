# MMIM — figurative-constant operands (`SPACES`, `ZEROS`) in `IF` conditions (Stage 26, no version bump)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v23` (unchanged — see §4)

Stage 25's own remaining-gaps list (`docs/MMIM_NEGATED_COMPARISON_FIX.md` §8, item 3) named this: "a
figurative-constant operand (`IF X NOT = SPACES`) is rejected outright: the comparison grammar's operand check
only accepts `STRING`/`NUMBER`/`IDENTIFIER` token types, and `SPACES` lexes as `KEYWORD`." This document is the
investigation and the fix.

## 1. Scope, established by investigation

Stage 25's gap note described the defect as "figurative constants are rejected." Direct investigation
(reproducing every COBOL figurative-constant spelling against the current parser) showed that framing is too
broad: **7 of the 9 canonical spellings already parsed successfully** (`ZERO`, `SPACE`, `ZEROES`,
`HIGH-VALUE`, `HIGH-VALUES`, `LOW-VALUE`, `LOW-VALUES`) — only `SPACES` and `ZEROS` failed. The root cause is
narrower than "the grammar doesn't support figurative constants": `app/parser/lexer/keywords.py`'s `KEYWORDS`
reserved-word set happens to list exactly those two words (apparently added only so `MOVE`/`VALUE`-clause code
elsewhere could recognise them), so only those two lex as `TokenType.KEYWORD`; every other spelling is not a
reserved word in this lexer and lexes as a plain `TokenType.IDENTIFIER`, which
`_parse_simple_condition`'s comparison-operand check already accepted. The actual gap is a **two-word
inconsistency in the operand-acceptance check**, not a missing grammar feature.

This is confirmed by an existing precedent already in this codebase: the analogous level-88 `VALUE`-literal
grammar (`app/parser/syntax/data_parser.py::_read_condition_literal`, written during Stage 20-23) already
accepts `{STRING, NUMBER, IDENTIFIER, KEYWORD}` for exactly this reason — it already treats a figurative
constant, however it lexes, as a valid literal. `_parse_simple_condition`'s comparison-operand check had simply
never been widened to match.

Deliberately out of scope, and separately investigated and ruled out during this stage's scoping work (see
`docs/MMIM_NEGATED_COMPARISON_FIX.md` §8, items 1 and 2, for detail on why they remain unfixed): the leading
`NOT` before an entire condition, and a subscripted operand (`IF WA-STATUS(WS-IDX) = 'C'`). The subscripted
case was investigated in depth for this stage and rejected as the Stage 26 target: correctly translating it to
Java requires modelling `OCCURS` tables as Java arrays, which this backend does not do at all today (confirmed:
`SYN200` already reports every `OCCURS` clause in the corpus as "not represented in the AST and was skipped");
the parser fix alone, without that, would recover the condition into the AST/IR but could not honestly reach
compilable Java, so it stays a deferred, larger-scoped gap rather than a "smallest fix."

## 2. Reproduction and root cause (measured before editing)

`IF WS-CODE = SPACES`: `_parse_simple_condition` requires the right-hand token to be
`TokenType.IDENTIFIER`/`NUMBER`/`STRING`. `SPACES` lexes as `TokenType.KEYWORD` (confirmed directly:
`CobolLexer().tokenize(...)` on a minimal synthetic program), so the check raised
`ParserError("expected operand for IF condition")`, and panic-mode recovery dropped the entire `IF`
statement — in the minimal synthetic reproduction, both the `IF` *and* the following `GOBACK` (0 of 2
top-level statements survived).

`ZERO`/`SPACE`/`ZEROES`/`HIGH-VALUE(S)`/`LOW-VALUE(S)` do not appear in `KEYWORDS` and lex as
`TokenType.IDENTIFIER`, so they already satisfied the existing check and parsed without any diagnostic.

## 3. The fix

**Parser only** (`app/parser/syntax/procedure_parser.py`, `_parse_simple_condition`): a new frozenset,
`_FIGURATIVE_CONSTANT_KEYWORDS = frozenset({"ZEROS", "SPACES"})` — exactly the two words `KEYWORDS` reserves —
and a new helper, `_is_comparison_operand_token(token)`, replacing the inline
`IDENTIFIER`/`NUMBER`/`STRING` check at both operand positions (left and right). It accepts the same three
token types as before, plus `TokenType.KEYWORD` when the token's lexeme is in
`_FIGURATIVE_CONSTANT_KEYWORDS`. No other `TokenType.KEYWORD` is newly accepted — an ordinary reserved word in
operand position (`IF X = MOVE`) still fails exactly as before; this is verified directly
(`test_operand_token_still_rejects_an_ordinary_reserved_word`).

The accepted operand's *value* is unchanged: `left`/`right` are still just `tok.lexeme` (`"SPACES"`,
`"ZEROS"`), exactly the same shape `"ZERO"`/`"SPACE"` already were. Nothing downstream — IR, business-rule
extraction, behavioral extraction, the Java backend — distinguishes `TokenType.KEYWORD` from
`TokenType.IDENTIFIER` after this point (both are carried as plain `str`), so no other file needed a change.
`_parse_simple_condition`'s existing `NOT`-negation logic (Stage 25) is untouched and composes for free: `IF
WS-CODE NOT = SPACES` and `IF WS-CODE <> ZEROS` both parse to operator `<>` exactly as any other operand pair
would.

`PERFORM UNTIL <condition>`'s own condition parsing (`_parse_perform_statement`) is a separate, much cruder,
pre-existing implementation that does not call `_parse_simple_condition` at all and performs no operand-type
validation whatsoever — it already accepted any token lexeme unconditionally, so it needed (and received) no
change.

## 4. Corpus exposure (measured before editing) — zero, no dataset regeneration

Searched every source in the 45-source training corpus (code columns, comments excluded) for a figurative
constant immediately following a comparison operator (`=`, `<>`, `<=`, `>=`, `<`, `>`), across every canonical
spelling: **zero occurrences**, of any figurative constant, anywhere. The one real occurrence found anywhere
in the repository is in the shared, non-corpus `workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl`
fixture, line 263: `IF WS-CURRENT-ACCOUNT NOT = SPACES`. That fixture's containing paragraph
(`4000-PROCESS-TRANSACTIONS`) already fails to parse at line 256 — its `READ TXN-FILE AT END ... NOT AT END
...` block is a separate, pre-existing, unrelated parser gap (`SYN005 "expected statement in PERFORM
block"`) — so parsing never reaches line 263 either before or after this fix. Directly confirmed
(`test_fixture_diagnostic_total_is_unchanged_by_this_fix`): the fixture's syntax-diagnostic count is
**byte-identical, 47, before and after this change**, and line 263 produces no diagnostic in either case
(masked, not fixed).

Because no corpus source and no already-tested fixture path is observably affected, `MMIM_GENERATOR_VERSION`
is **not bumped** and `data/dataset/mmim-v2` is **not regenerated** — the same outcome, for the same reason, as
task #stage22 (a genuine grammar-recognition fix with confirmed zero real-corpus impact).

## 5. Verification

**Isolated pre-fix proof.** A fresh byte-copy of the post-Stage-25 tree was made (`.venv`/caches excluded;
`app.__file__` confirmed to resolve inside the copy; `_FIGURATIVE_CONSTANT_KEYWORDS` confirmed textually absent
from the copy's source). All **37** new tests were copied onto that tree: the module fails to even *collect*
(`ImportError: cannot import name '_FIGURATIVE_CONSTANT_KEYWORDS'`), so all 37 fail pre-fix. All 37 pass on the
fixed tree.

**Symmetry check on the separate, pre-existing Java-translation gap (§6).** `emit_if` was called directly with
`IRIf(left="WS-CODE", operator="=", right=word)` for `ZERO` (already parseable before this stage) and
`SPACES`/`ZEROS` (newly parseable): all three produce the identical shape of output,
`if (wsCode == <lowerCamelCase(word)>) {`, referencing an undeclared Java field. This confirms the fix makes
`SPACES`/`ZEROS` reach the *same, already-existing* backend limitation as their synonyms — not a new one.

**Test suites**, compared against the documented baseline (**4671 passed, 12 pre-existing failures**: 3 in
`tests/ir/test_ir_control_flow.py`, 2 in `tests/parser/test_lexer.py`, 1 in
`tests/parser/test_lexer_regression.py`, 4 in `tests/parser/test_procedure_parser.py` missing-period tests, 2
in `tests/parser/test_token_types.py`):

* `tests/parser` — 9 failed (exactly the 9 parser-area baseline failures), 1237 passed.
* `tests/backend`, `tests/ir`, `tests/dataset`, `tests/modernization` — 3 failed (exactly the 3
  `test_ir_control_flow.py` baseline failures, in `tests/ir`), 1598 passed; `tests/backend`/`tests/dataset`/
  `tests/modernization` fully clean.
* Full suite — see the final report for the exact totals; no new failures anywhere relative to baseline.

`black`, `ruff check`, and `mypy` are clean on both changed files; no conflict markers anywhere in the repo.

## 6. Independent defect found (documented, NOT fixed)

The Java backend (`app/backend/java/statement_emitter.py::_translate_operand`,
`app/backend/java/control_flow_emitter.py::_build_condition`) has **no figurative-constant-to-Java-value
translation at all**, for any spelling. Every figurative constant falls through
`_translate_operand`'s generic "everything else is a COBOL identifier" rule (rule 4) and is emitted as a bare,
undeclared Java field reference (`ZERO` → `zero`, `SPACES` → `spaces`, `HIGH-VALUES` → `highValues`, ...) — a
guaranteed `javac` "cannot find symbol" failure. This is not new: it already silently affected every
already-parseable spelling (`ZERO`, `SPACE`, `ZEROES`, `HIGH-VALUE(S)`, `LOW-VALUE(S)`) before this stage, with
zero real-corpus exposure (§4) and therefore never observed or reported before. This stage does not fix it —
doing so correctly (translating `ZERO`→a numeric `0`, `SPACES`→a blank-fill comparison of the appropriate
length, `HIGH-VALUES`/`LOW-VALUES`→a sentinel comparison) is a genuinely separate, medium-sized backend
feature, unrelated to parser-level operand recognition. Making `SPACES`/`ZEROS` parseable does not worsen this
gap; it makes those two spellings symmetric with the 7 that already reached it (§5).

## 7. Remaining gaps (reproduced or previously documented, NOT fixed)

1. The *leading* `NOT` before an entire condition (`IF NOT WS-CODE = 'AUTO'`) remains unhandled for anything
   other than a known level-88 condition-name — unchanged, per `_parse_condition_term`'s own documented
   boundary (`docs/MMIM_NEGATED_COMPARISON_FIX.md` §1).
2. A subscripted operand (`IF WA-STATUS(WS-IDX) = 'C'`) is still not accepted by the comparison grammar —
   investigated in depth for this stage (§1) and deliberately not fixed: correctly reaching compilable Java
   requires `OCCURS`/Java-array modelling this backend does not have. Confirmed present in the real corpus
   (`table_indexed.cbl:43`, inside a `PERFORM VARYING` loop) and in the shared workspace fixture (line 323,
   already pinned by `tests/parser/test_unsupported_syntax_reporting.py`); both real-corpus occurrences found
   during this stage's survey are additionally confounded by `PERFORM VARYING` being entirely unsupported by
   this parser (§8) — a second, independent reason neither is observable without a larger fix.
3. The figurative-constant-operand parse gap this document fixes — resolved.
4. The independent business-rule-dependency defect (`_operand_bucket`), `docs/MMIM_NEGATED_COMPARISON_FIX.md`
   §7 — unrelated, still unfixed.
5. The Java figurative-constant-value-translation gap, §6 above — newly found this stage, unfixed.
6. `MOVE 09`, `DataModelElement.initial_value`, `GO TO … DEPENDING ON`, unsupported IF headers, FILE SECTION
   declarations, `COMPUTE`, `COMP`/`COMP-3` — as recorded before.

## 8. Newly found, independent defect (documented, NOT fixed): `PERFORM VARYING` is entirely unsupported

Discovered while scoping this stage's candidate gap 2 (subscripted operands): `PERFORM VARYING <id> FROM <n>
BY <n> UNTIL <condition> ... END-PERFORM` has zero support anywhere in `procedure_parser.py` (confirmed: no
`"VARYING"` reference in the file). `_parse_perform_statement` only recognises `PERFORM UNTIL <condition>` (no
`VARYING`) or a bare `PERFORM <paragraph-name>`; a `PERFORM VARYING` statement falls into the latter branch,
which treats the literal word `VARYING` as the target paragraph name, then fails on the next token
(`SYN001 "unexpected token '<id>' at statement level"`) with the entire loop body — every statement it would
have contained — silently absent from the AST. Confirmed present in the real corpus
(`table_indexed.cbl:40`, the sole paragraph exercising an `OCCURS` table) and in the shared workspace fixture
(line 460). Not fixed here — out of scope for an operand-recognition task, and a much larger feature (it also
requires the `OCCURS`/Java-array modelling gap 2 above depends on, to be worth completing end-to-end).

## 9. Files

`app/parser/syntax/procedure_parser.py`, `tests/parser/test_figurative_constant_operands.py` (new, 37 tests),
`docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`, and a resolution
pointer in `docs/MMIM_NEGATED_COMPARISON_FIX.md` §8. No dataset files, no existing test, and no other source
file changed (§4).
