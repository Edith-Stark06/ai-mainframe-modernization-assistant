# STEP 12 — Level-88 Condition-Name Parser Grammar Fix

## 1. Read before editing

- `docs/MMIM_LEVEL88_CONDITION_AUDIT.md` — the prior task's audit/STOP
  report, which precisely identified both root causes below and
  deliberately made no code change, per its own scope ("if the AST does
  not preserve sufficient information, stop and report... as a separate
  parser task").
- `docs/MMIM_V2_DATASET_AUDIT.md` — dataset state before this task: 349
  examples, 34/45 (75.6%) VALIDATION_REASONING coverage, `mmim-gen-v6`.
- `app/parser/syntax/data_parser.py::_parse_condition_name` — the DATA
  DIVISION level-88 grammar (root cause 1).
- `app/parser/syntax/procedure_parser.py::_parse_simple_condition`,
  `_parse_if_statement` — the PROCEDURE DIVISION IF-condition grammar
  (root cause 2).
- `app/parser/ast/data_items.py::ConditionNameNode`,
  `app/parser/ast/statements.py::ConditionTerm`/`IfStatementNode` — the
  existing AST representations, reused rather than replaced.
- `app/parser/syntax/program_parser.py` — division-parsing orchestration;
  confirmed DATA DIVISION is fully parsed into an AST *before*
  PROCEDURE DIVISION parsing begins, both against the same
  `ParserState`, which is what makes threading condition-name knowledge
  forward possible without a broader architecture change.
- `app/parser/grammar_words.py::matches_grammar_word` — the existing,
  already-used-elsewhere abstraction for "recognise this lexeme
  regardless of whether the lexer classified it as `KEYWORD` or
  `IDENTIFIER`" (COBOL's reserved-word set here is deliberately small;
  most grammar words, including `VALUES`, `AND`, `OR`, and `NOT`, reach
  the parser as `IDENTIFIER`). Reused for both fixes rather than
  inventing new dispatch logic.
- `app/modernization/business_rules/extractor.py` — confirmed it reads
  only `IfStatementNode.condition_left/operator/right` (never
  `extra_conditions`, which is parsed but not yet consumed by any
  downstream code — a pre-existing, unrelated characteristic, not
  something this task changes) and requires all three fields truthy to
  emit a rule. This shaped the AST-representation decision in §4.
- `app/ir/builder.py::build_if_statement`,
  `app/backend/java/control_flow_emitter.py` — confirmed the IR/Java
  backend passes `condition_operator` through opaquely and already has a
  graceful, diagnosed fallback (`BE007`, "IRIf has unsupported operator")
  for any operator string it does not recognise — so a new operator
  sentinel cannot crash or silently fabricate incorrect Java.
- `tests/parser/test_data_parser.py::TestConditionNameDeclaration` — only
  covered the singular `VALUE literal` form and the "no VALUE clause"
  case; zero coverage for `VALUES` (plural), confirming this is a
  genuine, previously-untested gap.
- `tests/parser/test_procedure_parser.py` — zero coverage for a bare
  identifier (of any kind) as an IF condition operand.
- `data/sources/phase6-v2/condition_names_88.cbl` — the one corpus source
  affected; confirmed via `grep -rl "^\s*88\s" data/sources/phase6-v2/`
  that it is the *only* source in the 45-source corpus declaring any
  level-88 item.

## 2. Reproduction — before this fix

Direct parse of the real source (`build_analysis_bundle`):

```
6 syntax diagnostics, including:
  SYN005 line 13  "expected '.' to terminate data item, got 'VALUES'"   <- TX-VALID-KIND
  SYN005 line 20  "expected '.' to terminate data item, got 'VALUES'"   <- ONLINE-CHANNEL
  SYN005 line 21  "expected '.' to terminate data item, got 'VALUES'"   <- PHYSICAL-BRANCH
  SYN005 line 34  "expected comparison operator in IF condition"        <- IF NOT TX-VALID-KIND
  SYN005 line 54  "expected comparison operator in IF condition"        <- IF PHYSICAL-BRANCH AND TX-WITHDRAWAL

business_rules: 0   (entire source)
statements:  0000-PROCESS-TRANSACTION=3, 1000-VALIDATE-TX-TYPE=0, 2000-ROUTE-BY-STATUS=0
```

Isolated minimal reproduction proving root cause 2 is independent of root
cause 1 (a condition-name with a fully correct singular-`VALUE`
declaration, still bare-referenced in an `IF`):

```cobol
01  TX-TYPE-CODE        PIC X(1) VALUE 'D'.
    88  TX-DEPOSIT      VALUE 'D'.
...
MAIN-PARA.
    IF TX-DEPOSIT
        MOVE 'YES' TO WS-OUT
    END-IF
    DISPLAY WS-OUT
    STOP RUN.
```

Result (before this fix): `SYN005 "expected comparison operator in IF
condition"`; `MAIN-PARA` parses with 0 statements — `MOVE`, `DISPLAY`, and
`STOP RUN` all lost to recovery.

## 3. Root causes — exact, independently verified

**Root cause 1 — `data_parser.py::_parse_condition_name` (DATA DIVISION
grammar).** Recognised only `88 name VALUE literal.`
(`tok.type is TokenType.KEYWORD and tok.lexeme.upper() == "VALUE"`). The
plural form `88 name VALUES literal literal ...` was not recognised at
all: `"VALUES"` is not in the lexer's reserved-word set (confirmed via
`grep -n '"VALUE"' app/parser/lexer/keywords.py`, only the singular form
is present), so it lexes as a plain `IDENTIFIER`; the singular-only check
never matched it, `_expect_period` ran immediately and saw `"VALUES"`
where a period must be, and the entire data-item entry was lost to error
recovery. `TX-VALID-KIND`, `ONLINE-CHANNEL`, and `PHYSICAL-BRANCH` — the
three condition-names in the real source using this form — never reached
the AST at all.

**Root cause 2 — `procedure_parser.py::_parse_simple_condition`
(PROCEDURE DIVISION grammar).** Unconditionally required
`<operand> <comparison-operator> <operand>`. There was no code path
anywhere for a bare identifier/condition-name reference (`IF
TX-DEPOSIT`), a negated one (`IF NOT TX-VALID-KIND`), or an `AND`/`OR`-
joined one (`IF PHYSICAL-BRANCH AND TX-WITHDRAWAL`) — every one of these
hit the "expected comparison operator" raise unconditionally, regardless
of whether the referenced name's own DATA DIVISION declaration parsed
correctly. No `IfStatementNode` was ever constructed, and the paragraph's
own error recovery discarded every subsequent statement up to the next
period.

Both were required to fully recover the real source: root cause 1 alone
would still leave `PHYSICAL-BRANCH`/`ONLINE-CHANNEL`/`TX-VALID-KIND`
unreferenceable by root cause 2's grammar (no declared name to recognise
them by); root cause 2 alone would still lose all statement content in
any paragraph guarded by one of those three names, since they would
remain entirely absent from the AST.

## 4. The fix — narrowest additive change, existing abstractions reused

### Root cause 1: `app/parser/ast/data_items.py` + `data_parser.py`

`ConditionNameNode` gained one new field:

```python
value: str | None = None    # unchanged: the single VALUE literal
values: tuple[str, ...] = ()  # new: every VALUE/VALUES literal, in order
```

`value` is set (as before) for the singular form and stays `None` for the
plural form (no single literal is "the" value of a multi-value
condition-name — this mirrors the pre-existing "no VALUE clause" `None`
convention rather than fabricating a canonical first value). `values` is
populated for both forms — `(value,)` for singular, one element per
literal for plural — so a consumer can read `values` uniformly regardless
of which form was used. No existing reader of `.value` exists anywhere in
`app/` (confirmed by grep), so this is purely additive; every existing
test that asserts `.value` continues to pass unchanged.

`_parse_condition_name` now dispatches on the clause keyword via
`matches_grammar_word(tok, {"VALUE"})` /
`matches_grammar_word(tok, {"VALUES"})` — the same helper already used
elsewhere in this file for grammar words the lexer does not reserve. The
singular branch is the original code, byte-for-byte, just relocated
inside an `if`. The new plural branch collects one-or-more literal tokens
(`STRING`/`NUMBER`/`IDENTIFIER`/`KEYWORD`, matching the singular form's
accepted types) in a loop until the terminating period, raising a clear
`ParserError` (not a silent misparse) if a literal is missing or if a
`THRU`/`THROUGH` range is used — a real, standard COBOL form, but one no
corpus source currently uses, so it is explicitly rejected rather than
silently mis-collected as if `THRU` were itself a value.

### Root cause 2: `parser_state.py` + `program_parser.py` + `procedure_parser.py`

`ParserState` gained `known_condition_names: frozenset[str]` (default
empty) and `set_known_condition_names()`. `ProgramParser._parse_program`
collects every `ConditionNameNode.name` from the already-parsed DATA
DIVISION AST (`_collect_condition_names`, a flat walk of
`working_storage.items` — this parser does not nest subordinate items, so
no recursion is needed) and calls
`state.set_known_condition_names(...)` **after** the DATA DIVISION parses
and **before** the PROCEDURE DIVISION does. Every existing direct caller
of `ProcedureDivisionParser.parse(state)` (roughly two dozen unit tests)
is unaffected: the parameter/attribute defaults to empty, so those tests
keep their original behaviour exactly, with zero code changes required on
their part.

`ProcedureDivisionParser` gained `_parse_condition_term`, the new entry
point `_parse_if_statement` calls (for both the leading condition and
every `AND`/`OR`-joined term) in place of calling
`_parse_simple_condition` directly:

```python
def _parse_condition_term(self, state):
    known = state.known_condition_names
    negated = matches_grammar_word(stream.current(), {"NOT"})
    lookahead = 1 if negated else 0
    candidate = stream.peek(lookahead)
    if candidate.type is IDENTIFIER and candidate.lexeme.upper() in known:
        following = stream.peek(lookahead + 1)
        if not _is_comparison_operator_token(following):
            ...  # consume NOT? consume the name; return (name, op, name)
    return self._parse_simple_condition(state)  # unchanged fallback
```

A bare identifier is *only ever* treated as a condition-name reference
when both (a) it is a member of `known_condition_names` — real,
declared evidence, never guessed from syntax alone — and (b) the token
immediately after it is not a comparison operator (so a real, if unusual,
`IF TX-DEPOSIT = 'X'` still takes the ordinary comparison path rather
than being misread). `_parse_simple_condition` itself is untouched except
that its inline operator-recognition check was factored out into a
shared `_is_comparison_operator_token` helper (identical logic, now also
used by the lookahead) — a pure refactor, not a behaviour change.

The resulting condition term is returned as the *same*
`(left, operator, right)` string triple `ConditionTerm`/`IfStatementNode`
already use — no new AST fields for root cause 2 at all. `operator` is
one of two new sentinel strings, `"IS-TRUE"` / `"IS-FALSE"`, chosen so
they can never collide with a real comparison operator symbol; `left` and
`right` both hold the condition-name itself (a condition-name reference
is a unary test, not a two-operand comparison, but keeping both fields
non-empty and identical means the existing, unmodified business-rule
extractor's `if left and op and right` truthy check picks the term up
without any change on its part — see §5).

### What was preserved

- **Integer/decimal/negative comparisons, AND/OR compounds**: untouched —
  `_parse_simple_condition`'s only change is the extracted-but-identical
  operator check; every existing comparison test still passes unchanged
  (verified: full `tests/parser/` suite, no new failures).
- **Operator precedence**: `AND` binds tighter than `OR`, exactly as
  before (`ConditionTerm`'s existing convention) — condition-name terms
  participate in the same flat `extra_conditions` sequence as ordinary
  comparison terms, with no special-casing.
- **No AST consumer broken**: `IfStatementNode`/`ConditionTerm`'s field
  set is unchanged; every existing reader (business-rule extractor, IR
  builder) continues to work without modification, confirmed by the full
  test suite and a direct Java-generation smoke test (§6).
- **Malformed syntax still diagnosed**: an identifier the DATA DIVISION
  never declared as level-88 (`IF NOT-A-REAL-CONDITION-NAME`) still hits
  the original "expected comparison operator" error — never silently
  accepted. `NOT` only ever admits a *known* condition-name; `NOT` before
  an unrecognised identifier is left unconsumed and falls through to the
  same original diagnostic.
- **The unrelated `NOT =` gap is not touched**: `t_account_eligibility`,
  `t_batch_acct_update`, `t_insurance_claim`, `t_payment_gateway` all
  still show their pre-existing "expected comparison operator" diagnostic
  at the exact same lines, unchanged (directly re-verified, §6) — because
  none of them declares any level-88 name, `known_condition_names` is
  empty for all four, and the new dispatch path never activates.
- **`PERFORM UNTIL` and decimal accumulator semantics**: not touched.
- **`app/behavioral/extraction/conditions.py`**: not touched, as
  instructed. It does not yet recognise `IS-TRUE`/`IS-FALSE` as
  comparison operators, so `t_condition_names_88` correctly still
  produces zero behavioral tests (§6) — an honest boundary, not an
  oversight.

## 5. Tests added

`tests/parser/test_data_parser.py` — 8 new tests in
`TestConditionNameDeclaration` (backward-compat: `values` tuple populated
alongside `value` for the singular form and for "no clause") and a new
`TestConditionNameValuesPluralForm` class (two-literal, four-literal
matching the real corpus's exact `TX-VALID-KIND` shape, numeric literals,
"does not disturb the following item," `THRU` explicitly rejected,
missing-literal-at-EOF rejected).

`tests/parser/test_level88_condition_reference_fix.py` — new, 19 tests:

- Minimal reproductions: bare condition-name IF, `NOT` condition-name IF,
  `NOT` of an *undeclared* identifier (still rejected — proves the fix is
  gated on real declared evidence), condition-name `AND` condition-name,
  condition-name `OR` condition-name, condition-name combined with an
  ordinary comparison, an undeclared identifier in a plain IF (still
  rejected), existing integer-comparison and existing compound-AND/OR
  regressions (both unaffected by the new dispatcher), and a
  genuinely-malformed IF (still diagnosed).
- **Critical error-recovery requirement**: statements after a
  condition-name IF survive in the same paragraph, and a later paragraph
  is unaffected either way.
- Downstream business-rule extraction sees a real, non-fabricated
  condition-name-derived rule (`TX-DEPOSIT IS-TRUE TX-DEPOSIT`, real
  action, real source-traced provenance).
- **Real-corpus regression** (`t_condition_names_88.cbl`, the actual file,
  not a synthetic stand-in): all 11 condition-names reach the AST
  (singular and plural alike); both previously-0-statement paragraphs now
  have real statements (1 and 2 respectively — matching the nested-IF
  representation convention every other nested IF already uses); the
  exact `IF PHYSICAL-BRANCH AND TX-WITHDRAWAL` condition from the task's
  own example reaches the AST intact; syntax diagnostics drop from 6 to 1
  (the one remaining is the unrelated `* CATEGORY B: ...` comment-line
  artifact at line 4); business rules go from 0 to 8, every one with real
  source-location provenance; and — the honest-boundary test — behavioral
  extraction is still 0 tests, because `conditions.py` was deliberately
  not touched.

## 6. Real-corpus validation

Methodology: the same precise Edit-based revert-and-restore technique
used in every prior parser-fix cycle in this MMIM effort. Since
`procedure_parser.py` already carried uncommitted changes from an earlier
cycle (the COMPUTE/EVALUATE-in-IF-block fix), a blanket `git stash` would
have reverted that earlier work too — instead, the four files this task
introduced from scratch (`data_items.py`, `data_parser.py`,
`parser_state.py`, `program_parser.py`, all untouched by any prior cycle,
confirmed via `git status` before this task began) were safely
`git stash`-reverted, and `procedure_parser.py`'s *exact* new hunks
(known precisely, having just been written) were reverted by hand via
the same `old_string`/`new_string` pairs in reverse. The revert was
verified to reproduce the documented pre-fix baseline exactly
(`parse_condition("RATE = 0.00")` still works — confirming the *prior*
cycle's decimal fix was undisturbed — while `t_condition_names_88` showed
6 diagnostics / 0 business rules, matching
`docs/MMIM_LEVEL88_CONDITION_AUDIT.md` precisely) before the "before"
corpus scan ran, and the fix was restored and re-verified before the
"after" scan ran.

A full 45-source corpus-wide diff (diagnostic count, business-rule count,
statement count per source) confirmed **exactly one source changed**:

| Metric | Before | After |
|---|---:|---:|
| Syntax diagnostics | 6 | 1 |
| Business rules | 0 | 8 |
| Procedure-division statements | 3 | 6 |

All other 44 sources: byte-identical before and after (not merely
"unaffected in the metrics checked" — a full per-source diff over all 45
sources found zero difference anywhere else). Directly re-confirmed the
4 unrelated `NOT =` sources are untouched (§4).

Spot-verified (not merely counted) `t_condition_names_88`'s 8 business
rules: every one carries `source_locations` with `filename ==
"t_condition_names_88.cbl"` and a real line number; the target example's
condition — `(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND (TX-AMOUNT >
1000.00)`, category `LIMIT_CHECK` — traces to the real nested `IF
TX-AMOUNT > 1000.00` inside the real `IF PHYSICAL-BRANCH AND
TX-WITHDRAWAL` at lines 54–55 of the real source.

Downstream tasks beyond business rules were also checked directly against
the real source (not merely assumed to follow):

- **DEPENDENCY_REASONING**: 12 real dependency edges for this source
  (up from far fewer when both paragraphs were empty), including 6 new
  `CONDITION`-type edges naming the level-88 identifiers themselves
  (`TX-VALID-KIND`, `TX-DEPOSIT`, `TX-WITHDRAWAL`, `TX-TRANSFER`,
  `PHYSICAL-BRANCH`, `ONLINE-CHANNEL`).
- **RISK_CLASSIFICATION**: gains a real, evidence-backed
  `DEEPLY_NESTED_CONDITIONS` (MEDIUM) finding — "deepest nest is in
  paragraph 1000-VALIDATE-TX-TYPE" — now that the nesting is actually
  visible in the AST.
- **COBOL_TO_JAVA**: Java generation runs to completion, produces valid
  Java, `compiles: True`. `IS-TRUE`/`IS-FALSE` reach the IR's `IRIf`
  opaquely and the Java backend's pre-existing `BE007`
  unsupported-operator fallback path exists for exactly this situation
  (confirmed by reading `control_flow_emitter.py` before assuming
  safety) — though in practice, for this specific source, an unrelated,
  pre-existing backend limitation (flat paragraph concatenation treating
  code after an earlier `GOBACK`/`STOP RUN` as unreachable) stubs both
  paragraphs' method bodies before the `IRIf` translation is ever
  reached, exactly as it already stubbed them (for a different reason —
  nothing to translate) before this fix. Net effect on generated Java:
  unchanged (still two `// TODO` stubs), confirmed by inspecting the
  generated output before and after.
- **MODERNIZATION_STRATEGY**: strategy label stays `REHOST` (a
  low-confidence fallback, since no decision rule's thresholds are met by
  this source's facts) — reported here rather than silently accepted:
  the fallback's rationale **string** is a hardcoded, pre-existing
  template ("The analysis found no procedure logic, no business rules,
  and no risks to act on...") that does not actually consult the facts it
  has already computed correctly (its own `evidence` array correctly
  lists "8 business rule(s)"). This is a genuine, independent,
  pre-existing defect in `app/modernization/strategy/analyzer.py::
  _fallback`, newly *exposed* (not caused) by this fix giving the source
  real business rules for the first time — reported in §8, not fixed,
  per this task's explicit scope.

## 7. MMIM dataset regeneration & versioning

`generator_version` incremented deliberately: `mmim-gen-v6` →
`mmim-gen-v7` (`app/dataset/version.py::MMIM_GENERATOR_VERSION_V7`),
documented as touching every AST/business-rule-derived task except
VALIDATION_REASONING (which this cycle does not touch, unlike every prior
parser-recovery cycle). `dataset_version` stays `"mmim-v2"` (same
45-source corpus, same task taxonomy — required by the repository's own
versioning design, unchanged from every prior cycle).

| Metric | mmim-gen-v6 | mmim-gen-v7 (this fix) |
|---|---:|---:|
| Total examples | 349 | 349 |
| Sources | 45/45 | 45/45 |
| VALIDATION_REASONING coverage | 34/45 (75.6%) | 34/45 (75.6%) — unchanged |
| `t_condition_names_88` business rules | 0 | 8 |
| Train / Validation / Test | 226 / 69 / 54 | 226 / 69 / 54 — unchanged |
| Benchmark leakage | 0 | 0 |
| Split leakage errors | 0 | 0 |
| Split leakage warnings | 5 (pre-existing, unrelated) | 5 (unchanged) |

Example count is unchanged (349 → 349) because this fix does not change
*how many* examples any source contributes (VALIDATION_REASONING
eligibility, the only per-example-count-affecting gate, is untouched) —
only the *content* of `t_condition_names_88`'s already-emitted
BUSINESS_RULE_EXTRACTION/DEPENDENCY_REASONING/RISK_CLASSIFICATION/
MODERNIZATION_STRATEGY/TRANSFORMATION_PLANNING/COBOL_TO_JAVA/
PROGRAM_UNDERSTANDING examples changed. Source-grouped split assignment
preserved: `t_condition_names_88` was already assigned to `validation`
and remains there (split assignment is a pure function of
`(dataset_version, seed, source_id)`, independent of example content);
train/validation/test example counts are all unchanged (226/69/54) since
no example was added or removed anywhere.

`data/dataset/mmim-v2/**` regenerated in place via
`build_mmim_dataset(..., generator_version=MMIM_GENERATOR_VERSION_V7,
strict_eligibility=True)` and `build_instruction_dataset`. `benchmark-v1`
and `data/dataset/mmim-v1/**` untouched (not read or written by this
task).

## 8. Tests run

```
python -m pytest tests/parser/test_data_parser.py tests/parser/test_level88_condition_reference_fix.py -q
                                                                                  # 84 passed
python -m pytest tests/parser/ -q   # 956 passed, 9 pre-existing unrelated failures
                                     # (tests/lexer/test_lexer.py x2, test_lexer_regression.py x1,
                                     # test_procedure_parser.py "missing period" x4,
                                     # test_token_types.py x2 -- identical set documented in
                                     # every prior cycle's audit; none touch condition-name
                                     # parsing, VALUES, or IF-condition grammar)
python -m pytest tests/dataset/ tests/behavioral/ tests/modernization/ -q
                                                                                  # 414 passed
python -m pytest tests/ -q   # full-tree baseline: 3764 passed, 12 pre-existing unrelated
                              # failures (tests/ir/test_ir_control_flow.py x3, tests/parser/
                              # test_lexer.py x2, test_lexer_regression.py x1,
                              # test_procedure_parser.py "missing period" x4,
                              # test_token_types.py x2 -- identical set documented in every
                              # prior cycle's audit; none touch level-88/VALUES/condition-name
                              # parsing
.venv\Scripts\black.exe --check .   # 1129 files clean (1 file reformatted before this run --
                                     # tests/parser/test_level88_condition_reference_fix.py --
                                     # then re-verified clean)
.venv\Scripts\ruff.exe check .      # all checks passed
.venv\Scripts\mypy.exe app          # no issues found in 354 source files
```

## 9. Exact files changed

- `app/parser/ast/data_items.py` — `ConditionNameNode.values` field added.
- `app/parser/syntax/data_parser.py` — `_parse_condition_name` recognises
  `VALUES` (plural).
- `app/parser/syntax/parser_state.py` —
  `known_condition_names`/`set_known_condition_names` added.
- `app/parser/syntax/program_parser.py` — `_collect_condition_names`
  helper; wires DATA DIVISION condition-names into `ParserState` before
  PROCEDURE DIVISION parses.
- `app/parser/syntax/procedure_parser.py` — `_is_comparison_operator_token`
  (extracted, unchanged logic), `_CONDITION_NAME_TRUE_OPERATOR`/
  `_CONDITION_NAME_FALSE_OPERATOR` sentinels, new `_parse_condition_term`,
  `_parse_if_statement` calls it instead of `_parse_simple_condition`
  directly.
- `app/dataset/version.py` — `MMIM_GENERATOR_VERSION_V7` added.
- `tests/parser/test_data_parser.py` — 8 new tests (backward-compat +
  `VALUES` plural form, including the real corpus's exact 4-literal
  shape).
- `tests/parser/test_level88_condition_reference_fix.py` — new, 19 tests.
- `tests/dataset/test_mmim_v2_dataset.py` — version bump (V6→V7), new §3f
  regression tests (4 tests).
- `tests/dataset/test_instruction_adapter_v2.py` — version bump (V6→V7).
- `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md` — this document.
- `docs/MMIM_V2_DATASET_AUDIT.md` — updated separately for the v7
  regeneration.
- `data/dataset/mmim-v2/**` — regenerated in place (`manifest.json`,
  `split_manifest.json`, `leakage_report.json`, `validation_report.json`,
  `all.jsonl`/`train.jsonl`/`validation.jsonl`/`test.jsonl`,
  `instruction/**`).

## 10. New independent gaps (not fixed, out of scope)

- **`app/modernization/strategy/analyzer.py::_fallback`'s rationale text
  is inconsistent with its own evidence** when the fallback path fires
  for a source that does have real business rules/risks — the rationale
  string unconditionally says "no procedure logic, no business rules, and
  no risks to act on" while the `evidence` tuple it returns alongside
  correctly lists the real counts (e.g. "8 business rule(s)"). Newly
  *exposed* by this fix (this source's fallback path previously fired
  with genuinely zero rules, so the text happened to be accurate before);
  not caused by it, and not fixed here — reported per this task's stop
  conditions.
- **`app/behavioral/extraction/conditions.py` does not yet recognise
  `IS-TRUE`/`IS-FALSE`** — the natural, now-unblocked next step (real
  business-rule conditions using these operators exist for the first
  time to validate against). Extending it would raise
  `t_condition_names_88`'s and any future level-88 source's
  VALIDATION_REASONING eligibility — deliberately not attempted here,
  per this task's explicit "Do NOT modify conditions.py yet."
- **The unrelated `IF <var> NOT = <literal>` negated-equality gap**
  (`t_account_eligibility`, `t_batch_acct_update`, `t_insurance_claim`,
  `t_payment_gateway`) remains unfixed, confirmed unaffected by this
  task's changes (§4, §6). *(Resolved in Stage 25, `mmim-gen-v23`,
  docs/MMIM_NEGATED_COMPARISON_FIX.md.)*
- **The `PERFORM UNTIL` unsupported-statement recovery gap** remains
  unfixed (out of scope, explicitly excluded by this task).
- **Decimal accumulator arithmetic** in
  `app/behavioral/extraction/extractor.py::_apply_action` remains
  unfixed (out of scope, explicitly excluded by this task).
