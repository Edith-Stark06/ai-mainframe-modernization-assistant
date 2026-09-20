# MMIM — negated relational operators (`NOT =`, `<>`) in `IF`/`PERFORM UNTIL` (Stage 25, `mmim-gen-v23`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v23`

Stage 24's own remaining-gaps list (`docs/MMIM_STRING_COMPARISON_FIX.md` §8) named this exactly: `IF X NOT =
'A'` and `IF X <> 'A'` are not parsed at all. This document is the investigation and the fix.

## 1. Scope, established from the docs

COBOL's own relational-operator grammar is

```
relation-condition ::= subject relational-operator object
relational-operator ::= [NOT] { = | > | < | >= | <= | <> }
```

`NOT` sits *between* the two operands and negates the operator that follows it — `IF WS-CODE NOT = 'AUTO'`,
not `IF NOT WS-CODE = 'AUTO'`. The latter is a different, broader grammar rule (`condition ::= [NOT]
simple-condition`, negating an entire condition), which `_parse_condition_term`'s own docstring already
names and explicitly puts out of scope ("the unrelated, out-of-scope `NOT <comparison>` gap") for a
non-condition-name operand. `!=` — this project's own extra spelling — already parsed and was already fully
translated by Stage 24 (`_cobolEquals` for text, `!=` for numbers). Only `NOT =` (and, by the same
production, `NOT >`/`NOT <`/`NOT >=`/`NOT <=`) and `<>` were missing.

## 2. Reproduction and root cause (measured before editing)

`IF WS-CODE NOT = 'AUTO' …`: `_parse_simple_condition` consumes `left = WS-CODE`, then requires the *next*
token to be a comparison operator (`_is_comparison_operator_token`). That token is `NOT` — not an operator —
so it raised `ParserError("expected comparison operator in IF condition")`, and panic-mode recovery dropped
the whole `IF` (present nowhere in the AST, IR, business rules, or generated Java).

`IF WS-CODE <> 'AUTO' …`: the lexer's operator dispatch already combines `<=`, `>=`, `==` and `!=` from two
adjacent characters, but had no `<` + `>` branch — so `<>` tokenized as two independent tokens,
`OPERATOR_LT('<')` then `OPERATOR_GT('>')`. `_parse_simple_condition` took `<` as the operator and then found
`>` where an operand was expected: `ParserError("expected operand for IF condition")` — same outcome, whole
`IF` dropped.

## 3. The fix

**Lexer** (`app/parser/lexer/lexer.py`): one new branch, `ch == "<" and next_ch == ">"` → `OPERATOR_NEQ`
lexeme `"<>"`, inserted alongside the existing `<=`/`>=`/`==`/`!=` branches — the identical adjacency-required
pattern (`scanner.peek()`, no whitespace skip), so a detached `< >` is unaffected. `<` and `>` are dedicated
relational-operator characters with no other meaning to protect (unlike `+`/`-`, which are also arithmetic
operators and needed the sign-gluing decision of task #stage21 to stay in the *parser*, not the lexer) — so
combining them in the lexer, symmetrically with its siblings, is the smaller and more consistent change.

**Parser** (`app/parser/syntax/procedure_parser.py`, `_parse_simple_condition` only): after the left operand,
an optional `NOT` (recognised the same way every other grammar word in this parser is, via
`matches_grammar_word`) is consumed and remembered; the operator token that follows is then required exactly
as before, and — only if `NOT` was present — replaced by its negation from a small involutive table,
`_NEGATED_OPERATOR` (`=`↔`<>`, `==`↔`!=`, `>`↔`<=`, `<`↔`>=`). The result is always one of the operator
spellings this grammar already accepted, so nothing downstream needs a new case. `_parse_condition_term`'s
own leading-`NOT` handling (for a level-88 condition-name, and its documented decision to leave a
non-condition-name leading `NOT` unconsumed) is untouched — my method is only reached *after* that decision
already fell through to the ordinary comparison grammar.

**Backend** (`app/backend/java/control_flow_emitter.py`): `OPERATOR_ALIASES` gains `"<>": "!="`, exactly the
existing `"="`→`"=="` pattern. `NOT =` and `<>` both surface as the AST-level operator `<>` (chosen over
`!=` so a rule's human-readable condition text stays faithful to the COBOL source spelling — `<>`, not a
re-invented `!=`), and reach `_build_condition` exactly like any other alias: aliased to Java `!=` *before*
`translate_comparison` runs, so a text `<>` becomes `_cobolEquals(...)`/`!_cobolEquals(...)` (Stage 24) and a
numeric one stays plain `!=`. No IR change, no new backend case.

## 4. Corpus exposure (measured before editing)

Searched every source (code columns, comments excluded) for `NOT\s*=` and `<>`: **exactly 4 sources**, 5
occurrences — `account_eligibility.cbl:33` (a compound `AND` of *two* `NOT =` terms), `batch_acct_update.cbl:40`,
`insurance_claim.cbl:48`, `payment_gateway.cbl:36`. No `<>`, no `NOT >`/`NOT <`/`NOT >=`/`NOT <=` anywhere in
the corpus.

All 4 occurrences sit in a paragraph other than the entry paragraph (`1000-*`/`2000-*`), which this backend's
flat, single-block lowering turns into an empty `PERFORM` stub *unless* the entry paragraph's own flow falls
through into it (no `STOP RUN`/`GOBACK` first). 3 of the 4 entry paragraphs correctly end in an unconditional
`GOBACK`, so their (now-parseable) `IF`s sit in code the backend's existing reachability tracking correctly
marks dead (`BE011`) — same honest, already-existing mechanism, now simply seeing real instructions that
previously did not exist. The 4th, `batch_acct_update.cbl`'s `0000-PROCESS-ACCOUNTS`, has a *different*,
pre-existing, unrelated parser gap: `PERFORM 3000-PROCESS-LOOP UNTIL WS-EOF-FLAG = 'Y'` (the out-of-line
`PERFORM <paragraph> UNTIL <condition>` form) is not parsed (`SYN001 "unexpected token 'UNTIL'"`), and
recovery — synchronising to the next period — swallows the rest of that one COBOL sentence, including the
paragraph's own `GOBACK`. With no `GOBACK`, the flat block falls straight through into `1000-OPEN-FILES`,
making its `IF WS-FILE-STATUS NOT = '00'` genuinely reachable. This is why only **1** of the 4 affected
sources changes its generated Java.

## 5. Verification

**Isolated pre-fix proof.** The new tests were run on a byte-copy of the pre-edit tree, `cwd` rooted there
(`app.__file__` confirmed inside the copy; the fix confirmed absent in all three files). Of the **53** new
tests, **32 fail**: every lexer/AST/executed-Java/real-corpus test that depends on the fix. The **21** that
pass on both trees are the intended guards — plain `=`/`!=`/ordering unchanged, detached `< >` still two
tokens, the other two-char operators untouched, the out-of-scope leading-`NOT` case still fails the same way,
`IF NOT <condition-name>` (Stage 24) untouched, the `BE007` rejection of a genuinely unsupported operator, the
corpus survey itself, and (by coincidence — the seed values happen to make every check `False` under both the
broken "condition never existed" pre-fix behaviour and the correct post-fix logic) 2 of the 5 executed-Java
seed combinations.

**Executed Java** (real `javac`/`java`): a synthetic program with `NOT =`, `<>`, field-vs-field, and a
compound `AND` of two `NOT =` terms, checked against an independent Python oracle across 5 seed combinations
including trailing-space-insensitivity. `t_batch_acct_update`'s whole class does not compile (§4's unrelated
FILE SECTION gap, pre-existing and unchanged — confirmed by comparing its `javac_ok` before and after: `False`
both times); its *real* `IRIf` for `WS-FILE-STATUS NOT = '00'` was extracted from its own IR and translated
with the real `emit_if`, then embedded in a small class carrying only the two fields it needs, compiled, and
executed across 4 statuses (unpadded match, padded match, mismatch, never-set) — all matching COBOL.

**Real corpus before/after (45 sources, per-source fingerprint: AST, IR, CFG, dependencies, business rules,
risks, strategy, every diagnostic, Java text, `javac`; "before" from the isolated baseline tree):** exactly
**4** sources change on every non-Java dimension (`account_eligibility`, `batch_acct_update`, `insurance_claim`,
`payment_gateway`); only **1** (`batch_acct_update`) changes its Java text (one new comparison plus the
`_cobolEquals` helper). `javac` **41/45 → 41/45** (unchanged, including `batch_acct_update`'s own pre-existing
failure). The other 41 sources are fingerprint-identical. (`t_policy_redefines`'s semantic-diagnostics hash
also moves between *any* two runs, pre-fix or post-fix — an already-documented artifact, Stage 24 §6: its
`SEM001` duplicate-`FILLER` message embeds a random temp-dir path.)

## 6. Existing tests updated (all direct, traceable consequences; none deleted or weakened)

* `test_java_if_emission_fix.py` (2): `OPERATOR_ALIASES` gained `"<>"`; `<>` removed from the
  "still-unsupported" parametrisation (replaced by `"~="`, a spelling no grammar here produces, to keep the
  same test intent and count).
* `test_syntax_diagnostic_model.py` (2): `IF A NOT = B` was the chosen example of "malformed grammar ->
  `SYNTAX_ERROR`"; it no longer is one. Swapped for `IF A(1) = B` — a subscripted operand, a different,
  still-genuinely-unsupported construct (confirmed to remain a single `SYNTAX_ERROR`/`ERROR` diagnostic).
* `test_cobol_comparison_semantics.py` (Stage 24, 1): its real-corpus "only `t_policy_redefines` uses the
  helper" assumption is now "these two" (`t_batch_acct_update` joins it).
* `test_extra_conditions_ir_fix.py` (1): the self-verifying `ir_terms == ast_terms` check already re-derives
  both sides from the current tree; only the final hard-coded total moved, 11 → 12
  (`account_eligibility.cbl`'s compound term, previously nonexistent on both sides).
* `test_unsupported_syntax_reporting.py` (1) and `test_intelligence_pipeline.py` (1): the shared
  `workspace/…/complex_acctbatch.cbl` fixture has 9 `NOT =` occurrences (not part of the 45-source corpus);
  7 now parse. Syntax diagnostics 45 → 47 (7 fewer `SYN005`s, but +2 net: fixing them lets the parser walk
  past line 317 for the first time and reveals a *different*, pre-existing, unrelated `SYN005` at line 323 —
  `IF WA-STATUS(WS-IDX) = 'C'`, a subscripted operand — that recovery had always swallowed silently until now,
  the same "more honest, not less" pattern this test's own docstring already documents for its 44→45 history.
  Business rules 13 → 18 (5 new rules for the newly-parseable conditions, all prior rules renumbered only,
  content unchanged); risk categories and strategy assertions (relative, not exact-count) are unaffected.
* `test_empty_paragraph_perform_target_fix.py` (2): `t_batch_acct_update`'s `1000-OPEN-FILES` is the one real
  corpus paragraph whose newly-real `IF` reaches actual Java (§4) — it is genuinely no longer an "empty"
  paragraph (`PROCESS` anchor node → real `DECISION` node); the empty-node list and PERFORM-target-resolution
  checks are updated to match.

## 7. Independent defect found (documented, NOT fixed)

`app/modernization/business_rules/extractor.py::_operand_bucket` (Phase 4, commit `02f7838` — long before and
unrelated to any comparison-operator work) classifies a raw operand as one literal-or-variable unit and never
splits a *multi-token* one. A COBOL multi-operand `DISPLAY 'literal' identifier` is stored by the parser as
one joined string; since that string is not a *bare* quoted literal, `_operand_bucket` falls through to
"variable", and the whole compound string — literal prefix included — becomes a business rule's
`dependencies` entry, which is not an identifier at all. This was always latent in
`workspace/…/complex_acctbatch.cbl`'s `1000-INITIALIZE` (`DISPLAY 'CUSTOMER OPEN ERROR: ' WS-CUST-STATUS` and
3 siblings); it was never exercised by `test_complex_fixture_rules_are_evidence_backed` because that
paragraph's guarding `IF WS-CUST-STATUS NOT = '00'` failed to parse at all before this stage, so no rule, and
no dependency, ever existed for it. Left unfixed — out of scope for a comparison-operator parsing task — and
called out with a narrow, fully-documented, 4-value exception in that one test (never a blanket weakening: the
test still fails on any *other* literal dependency, from any other source).

## 8. Remaining gaps (reproduced, NOT fixed)

1. The *leading* `NOT` before an entire condition (`IF NOT WS-CODE = 'AUTO'`) remains unhandled for anything
   other than a known level-88 condition-name — deliberately out of scope, per `_parse_condition_term`'s own
   documented boundary (§1).
2. A subscripted operand (`IF WA-STATUS(WS-IDX) = 'C'`) is not accepted by the comparison grammar at all,
   with or without `NOT`/`<>` — confirmed independently present in both the real corpus (§4, `batch_acct_update`'s
   `3100-APPLY-ACCOUNT-RULES`) and the shared workspace fixture (§6).
3. A figurative-constant operand (`IF X NOT = SPACES`) is rejected outright: the comparison grammar's operand
   check only accepts `STRING`/`NUMBER`/`IDENTIFIER` token types, and `SPACES` lexes as `KEYWORD`. **Resolved
   in Stage 26** (no version bump — zero real-corpus impact; `docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md`).
4. The independent business-rule-dependency defect, §7.
5. `MOVE 09`, `MOVE SPACES`, `DataModelElement.initial_value`, PERFORM semantics, `GO TO … DEPENDING ON`,
   unsupported IF headers, FILE SECTION declarations, `COMPUTE`, `COMP`/`COMP-3` — as recorded before.

## 9. Files

`app/parser/lexer/lexer.py`, `app/parser/syntax/procedure_parser.py`, `app/backend/java/control_flow_emitter.py`,
`app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V23`), `tests/parser/test_negated_comparison_operators.py`
(new, 33 tests), `tests/backend/test_negated_comparison_java.py` (new, 20 tests),
`tests/dataset/test_mmim_v2_dataset.py` (V23 pins), `tests/dataset/test_instruction_adapter_v2.py`,
`tests/backend/test_java_if_emission_fix.py`, `tests/parser/test_syntax_diagnostic_model.py`,
`tests/backend/test_cobol_comparison_semantics.py`, `tests/ir/test_extra_conditions_ir_fix.py`,
`tests/parser/test_unsupported_syntax_reporting.py`, `tests/modernization/test_intelligence_pipeline.py`,
`tests/modernization/business_rules/test_extractor.py`,
`tests/modernization/flow/test_empty_paragraph_perform_target_fix.py`, `data/dataset/mmim-v2/**` (regenerated
v23), `docs/MMIM_NEGATED_COMPARISON_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`, and a resolution
pointer in `docs/MMIM_STRING_COMPARISON_FIX.md`.
