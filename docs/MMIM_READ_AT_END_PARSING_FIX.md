# Parser: `READ ... AT END` / `NOT AT END` statement-boundary defect

Branch `feat/mmim-read-at-end-fix` (from `feat/mmim-java-literal-emission`). Follows
`docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md` §6, which reported this as pre-existing and out of
scope. `generator_version` `mmim-gen-v13` -> `mmim-gen-v14`; `dataset_version` stays `mmim-v2`.

## 1. Path traced before any code changed

`READ` has no AST node or parser of its own — it is one of the verbs in
`_UNSUPPORTED_STATEMENT_LEXEMES`, skipped as a single `SYN100` diagnostic like `OPEN`/`CLOSE`/`WRITE`.
Reproduced on the isolated pre-fix tree (`PYTHONPATH` pointing at a byte-copy of it), for
`data/sources/phase6-v2/batch_acct_update.cbl:45-48`:

```
READ ACCT-IN-FILE INTO FD-ACCT-RECORD
    AT END MOVE 'Y' TO WS-EOF-FLAG
    NOT AT END ADD 1 TO WS-RECORDS-READ
END-READ.
```

```
lexer      READ ACCT-IN-FILE INTO FD-ACCT-RECORD AT END MOVE 'Y' TO WS-EOF-FLAG
           NOT AT END ADD 1 TO WS-RECORDS-READ END-READ .
           -- "END-READ" is one IDENTIFIER token (hyphen included); "AT"/"END"/
              "NOT" are each separate, bare IDENTIFIER tokens (not "END-READ").
parser     _skip_unsupported_statement(READ) -- READ has no entry in
           _SCOPE_CLOSE_WORDS (only EVALUATE does), so it fell back to the
           generic "scan to next period, but stop at the first statement-verb
           token" loop. That loop consumes ACCT-IN-FILE, INTO, FD-ACCT-RECORD,
           AT, END -- then hits "MOVE", a real statement-lexeme token, and
           _at_operand_boundary(MOVE) is True -> the skip STOPS right there,
           having consumed only "READ ... AT END".
           The outer statement loop then sees "MOVE" as an ordinary new
           statement and parses it: source='Y', TO, then accumulates TARGET
           tokens with no boundary check on the bare words NOT/AT/END --
           WS-EOF-FLAG, NOT, AT, END are all consumed as target text, stopping
           only at "ADD" (a statement-lexeme boundary) ->
           MoveStatementNode(target="WS-EOF-FLAG NOT AT END")
           "ADD 1 TO WS-RECORDS-READ" is then parsed as its own AddStatementNode,
           whose own target-accumulation loop has the identical defect: nothing
           recognises the standalone "END-READ" token as a boundary, so it is
           absorbed too -> AddStatementNode(target="WS-RECORDS-READ END-READ")
semantic   ReferenceResolverVisitor: undefined variable:
           'WS-EOF-FLAG NOT AT END' (SEM003) -- the corrupted target was never
           declared, because it never was a real COBOL identifier.
Java       _translate_operand("WS-EOF-FLAG NOT AT END") -> to_java_field_name(...)
           -> wsEofFlagnotatend = "Y";  wsRecordsReadendRead += 1;
           two undeclared fields, cannot find symbol at javac.
```

Root cause: the generic unsupported-statement skip is fundamentally incompatible with any verb
whose clauses legitimately contain nested full statements — exactly why `EVALUATE` (whose `WHEN`
clauses have the same shape) was given a dedicated scope-matching skip
(`_skip_to_matching_close_word`, keyed on `END-EVALUATE`) instead of the generic one. `READ`'s
`AT END`/`NOT AT END` clauses needed the identical treatment and never got it.

## 2. Corpus inventory (both real forms, verified before writing any fix)

```
grep -ln "READ " data/sources/phase6-v2/*.cbl
```

Exactly **4** real sources contain an actual `READ` statement (a fifth grep hit,
`t_transitive_fx`, was a false positive — `WS-RECORDS-READ` is a *data name* containing the
substring "READ", not a `READ` verb):

| Source | Form |
|---|---|
| `t_batch_acct_update` | `AT END` + `NOT AT END`, explicit `END-READ.` |
| `t_daily_trans_report` | `AT END` only, explicit `END-READ.` (x2) |
| `t_inventory_extract` | `AT END` only, explicit `END-READ.` (x2) |
| `t_payroll_file_post` | `AT END` only, explicit `END-READ.` (x2) |

A **second, distinct** legal form exists in this repository's own test fixtures —
`tests/fixtures/phase5/file_processing.cbl:22`: `READ CUST-FILE AT END MOVE 'Y' TO WS-EOF.` — no
`END-READ` at all; real COBOL grammar allows `READ`'s `AT END` clause to be closed by the
sentence's own terminating period instead. This fixture is exercised by
`tests/modernization/scoring/test_phase5_regression.py`. **Both forms had to be handled**; a fix
that only recognised `END-READ` (mirroring `EVALUATE` exactly) would have made a period-terminated,
`END-READ`-less `READ` — this exact fixture — hang the skip until EOF or the next division header,
silently swallowing every statement after it (`ADD 1 TO WS-COUNT`, `CLOSE CUST-FILE`, `DISPLAY
WS-COUNT`, `STOP RUN`).

## 3. The fix (`app/parser/syntax/procedure_parser.py` only)

A new dedicated method, `ProcedureDivisionParser._skip_read_statement`, replaces the generic skip
for the `READ` verb only (dispatched before the `EVALUATE`/`SEARCH` scope-opening check, so
`_SCOPE_OPENING_LEXEMES`/`_SCOPE_CLOSE_WORDS`/`_skip_to_matching_close_word` — used by `EVALUATE` —
are **completely untouched**, reverted to their original form after an initial design that would
have shared and complicated them). It tracks whether the bare word `AT` (the only word that
introduces `AT END`/`NOT AT END` in this grammar) has been seen yet:

* **Before** the first `AT`: behaves exactly like the generic skip — a statement-boundary token
  still ends the skip early. This is what preserves every existing period-less-`READ` test (a bare
  `READ F1` with no clause, immediately followed by another statement, is untouched).
* **From** the first `AT` onward: a statement-boundary token no longer ends the skip (it is
  legitimately part of a clause's nested statement) — only `END-READ` or a bare period does.
* `END-READ` is recognised at any point (even before `AT`, for a clause-less `READ F1 END-READ.`);
  a bare period always ends the `READ`, at any point, handling both real forms with one method.
* Stops early at EOF or a division header, matching every other skip path in this class.

**Scope note, disclosed rather than hidden:** only `AT END`/`NOT AT END` are recognised. A `READ`
using `INVALID KEY`/`NOT INVALID KEY` instead (random access) has no `AT` token, so it keeps the
pre-existing generic-skip behavior — not present anywhere in the current corpus or test fixtures,
and deliberately out of this task's scope.

No behavioral extraction, dependency-analysis *logic*, business-rule extraction, Java emission
logic, or unrelated parser code changed — `READ` still produces zero AST nodes and still emits the
same `SYN100` diagnostic it always did. Only what tokens get *consumed as part of that one skip*
changed.

## 4. Tests

`tests/parser/test_read_at_end_parsing_fix.py` — 27 tests, following
`tests/parser/test_statement_boundaries.py`'s exact conventions (parse via `CobolLexer` ->
`ProgramParser`, assert on the AST and diagnostics): a normal/bare `READ` (with and without a
period, matching the two existing pinned shapes); `AT END` alone, with and without `END-READ`;
`NOT AT END` alone and together with `AT END`; multiple `READ`s in one paragraph, each skipped
independently; all 4 real-corpus shapes plus the `file_processing.cbl` fixture shape, reproduced
verbatim; the real corpus itself (parametrized over the 4 sources: no mangled `undefined variable`
diagnostic remains, the specific mangled Java identifiers are gone, `READ` is still `SYN100`); and
5 "ordinary identifiers unaffected" tests (`AT-RISK-FLAG`, a hyphenated data name, is one token and
is never mistaken for the bare word `AT`; a `MOVE`/`IF` after a fully-closed `READ` still parses
correctly; a malformed `READ` with neither `END-READ` nor a period stops safely at EOF/paragraph
boundary rather than hanging). **22 of the 27 fail on the isolated pre-fix tree**; the 5 that pass
are the "unchanged behaviour" guards.

One assertion in the first test draft was too broad (`"undefined variable" in message`, which also
matches `t_payroll_file_post`'s pre-existing, unrelated `FD-*` FILE SECTION diagnostics) and was
narrowed to the specific mangled-clause pattern (`"AT END"`/`"NOT AT"`/`"END-READ"` inside the
message) before being trusted. Every pre-existing test passes unmodified —
`tests/parser/test_statement_boundaries.py`'s `test_consecutive_unsupported_verbs_each_diagnosed`
(`READ F1` with no period, immediately followed by `STOP RUN.`) and
`tests/parser/test_token_type_regressions.py`'s `READ F1.` cases were the two I identified as
directly at risk from an earlier, discarded design (making `READ` share `EVALUATE`'s pure
scope-close mechanism unconditionally, which would have hung on the bare-`READ`-no-clause and
`file_processing.cbl` shapes) — both pass unmodified with the final design, and
`tests/modernization/scoring/test_phase5_regression.py` (which uses the `file_processing.cbl`
fixture directly) passes unmodified too.

## 5. Real-corpus before/after (45 sources, isolated trees, real `javac 25.0.3`)

"Before" = a byte-copy of the pre-fix (`mmim-gen-v13`) `app/` tree in a subprocess with
`PYTHONPATH` pointing at it; "after" = the repository. The snapshot records `app.__file__`, the
parser's SHA-256, and whether `_skip_read_statement` exists; the comparison asserts they differ
(`16abb91e4a98` vs `0393b59cccdc`).

| Measure | Result |
|---|---|
| Sources whose AST/Java changed | **4 / 45** — exactly `t_batch_acct_update`, `t_daily_trans_report`, `t_inventory_extract`, `t_payroll_file_post` |
| Parser diagnostics (count and codes) | 0 sources differ |
| Business-rule counts | 0 sources differ (157 -> 157 total) |
| Java brace balance | 45/45 -> 45/45 (unaffected) |
| `javac` compiles | 41/45 -> 41/45 (unaffected — see §6) |

Per-source AST/IR/Java changes, all exactly the spurious `MOVE`/`ADD` statements disappearing (the
`READ`'s own clause paragraph becomes correctly empty — `READ` is still unsupported, so it still
has *zero* representable statements, same as `OPEN`/`CLOSE`):

| Source | `undefined variable` diagnostics removed | Dependency edges removed | Java lines removed |
|---|---|---|---|
| `t_batch_acct_update` | `'WS-EOF-FLAG NOT AT END'` | `VARIABLE_WRITE:WS-EOF-FLAG NOT AT END`, `VARIABLE_WRITE:WS-RECORDS-READ END-READ`, `VARIABLE_READ:WS-RECORDS-READ END-READ` | `wsEofFlagnotatend = "Y";` `wsRecordsReadendRead += 1;` |
| `t_daily_trans_report` | `'WS-EOF END-READ'` (x2) | `VARIABLE_WRITE:WS-EOF END-READ` (x2) | `wsEofendRead = "Y";` (x2) |
| `t_inventory_extract` | `'WS-INV-EOF END-READ'` (x2) | `VARIABLE_WRITE:WS-INV-EOF END-READ` (x2) | `wsInvEofendRead = "Y";` (x2) |
| `t_payroll_file_post` | `'WS-PAY-EOF END-READ'` (x2) | `VARIABLE_WRITE:WS-PAY-EOF END-READ` (x2) | `wsPayEofendRead = "Y";` (x2) |

`t_batch_acct_update` is the only source with `NOT AT END`; its ADD statement's corrupted target
(`WS-RECORDS-READ END-READ`) produced both a spurious `VARIABLE_READ` (the pre-increment read) and
`VARIABLE_WRITE` dependency edge, one more than the `AT END`-only sources.

**No source moved between `reference` and `deterministic`/`executable_verified`.** `javac` compile
count is unchanged (41/45 before and after): the mangled identifiers were never the *only* reason
these 4 sources failed to compile — all 4 also have undeclared FILE SECTION fields (the separate,
already-documented gap from `docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md` §6), which the fix does not
and was not asked to address.

## 6. New independent gap discovered — reproduced, documented, NOT fixed

**The CFG/flow generator (`app/modernization/flow/generator.py`) treats a `PERFORM` to a real but
statement-empty paragraph as an unresolved *external* target**, the same as a `PERFORM` to a
paragraph that does not exist at all.

Investigating an unexpected diff (`t_batch_acct_update`'s `UNRESOLVED_PERFORM_TARGET` risk finding
went from 1 to 3 occurrences after this fix) traced to this precisely:
`RiskAnalyzer._detect_unresolved_perform_targets` flags a `PERFORM` whose CFG edge target is a
synthetic `EXTERNAL` node. The CFG builder creates that synthetic node whenever a paragraph has **no
statements to build a real entry node from** — it does not check whether the paragraph genuinely
exists in the AST, only whether it produced any CFG nodes. Verified directly:

```
paragraphs: [0000-PROCESS-ACCOUNTS, 1000-OPEN-FILES, 2000-READ-RECORD,
             3000-PROCESS-LOOP, 3100-APPLY-ACCOUNT-RULES, 4000-CLOSE-FILES]
PERFORM -> 1000-OPEN-FILES   resolved (by name) : True   -- flagged EXTERNAL anyway
PERFORM -> 2000-READ-RECORD  resolved (by name) : True   -- flagged EXTERNAL anyway (x2)
```

`1000-OPEN-FILES` was **already** empty before this fix (its own `IF WS-FILE-STATUS NOT = '00' ...`
fails to parse for the separate, already-documented `IF <var> NOT = <literal>` negated-equality
gap — nothing to do with `READ`), so this defect was already producing 1 false
`UNRESOLVED_PERFORM_TARGET` occurrence pre-fix. This fix correctly empties `2000-READ-RECORD` too
(a `READ`, like an `OPEN`, is unsupported and has zero representable statements — that is not new,
it is the honest, intended state), which — through this **pre-existing, independent** CFG defect —
raises the count to 3. The risk/strategy evidence text (`"N unresolved PERFORM target(s)"`) is
therefore currently **overstated** for any source with a real but empty paragraph; it was already
overstated before this task, just by a smaller, less visible amount.

This lives entirely in the CFG/flow-generation and risk-analysis layers, not in `READ` parsing or
statement-boundary handling, and reproducing/fixing it would change RISK_CLASSIFICATION and
MODERNIZATION_STRATEGY ground truth for reasons unrelated to this task's scope. **Not fixed here.**

> **Resolved** in the next task — see `docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md`
> (`mmim-gen-v15`): existence and executable content are now represented separately in the CFG, so an
> existing-but-empty paragraph like `1000-OPEN-FILES`/`2000-READ-RECORD` resolves correctly instead of
> being flagged `UNRESOLVED_PERFORM_TARGET`.
Also traced and confirmed benign: `program_understanding.parser_diagnostics.parse_complete` flips
`False` -> `True` for the same 4 sources — `parse_complete` is `tokens_consumed == tokens_total and
abandoned_construct_count == 0` (`app/analysis/models.py`), and the pre-fix corruption's token
mis-attribution was exactly the kind of thing that signal exists to catch; this is a direct, correct
consequence of the fix, not an independent issue.

## 7. Dataset regeneration (`mmim-gen-v14`)

`app/dataset/version.py::MMIM_GENERATOR_VERSION_V14`. Parser-layer change: touches every task whose
`expected_output` embeds AST-derived dependency/statement data for the 4 affected sources.

| | mmim-gen-v13 | mmim-gen-v14 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 |
| Examples changed | — | **31**, across exactly the 4 sources (7-8 each: BUSINESS_RULE_EXTRACTION, COBOL_TO_JAVA, DEPENDENCY_REASONING, MODERNIZATION_STRATEGY, PROGRAM_UNDERSTANDING, RISK_CLASSIFICATION, TRANSFORMATION_PLANNING for all 4; VALIDATION_REASONING for 3 of 4 — `t_inventory_extract` was already a VALIDATION_REASONING skip, unaffected) |
| Business-rule counts | 157 total | 157 total, unchanged |
| VALIDATION_REASONING coverage / test counts | 36/45; 4/5/3 for the 3 affected sources | unchanged |
| `compiles == True` | 41 | 41, unchanged |
| Ground truth (deterministic / executable_verified / reference) | 345 / 2 / 4 | unchanged |
| Source->split assignment | — | identical |
| Benchmark leakage | 0 | 0 |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |

None of the 31 changed examples altered a *rule*, a *test*, or a *compile* outcome — every change
is the removal of the corrupted dependency edges/statements (and their knock-on text in
strategy/risk evidence and architecture `content_hash`es) from `expected_output`, confirmed example
by example. Two independent full regenerations are byte-identical (`all.jsonl`, split files,
`manifest.json`, `split_manifest.json`, `leakage_report.json`, every `instruction/*` file).
`benchmark-v1` and `mmim-v1` (144 examples) are untouched.

## 8. Exact files changed (this task)

* `app/parser/syntax/procedure_parser.py` (`_skip_read_statement`, dispatched from
  `_skip_unsupported_statement`; `_skip_to_matching_close_word` and `_SCOPE_OPENING_LEXEMES`/
  `_SCOPE_CLOSE_WORDS` are unchanged)
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V14`)
* `tests/parser/test_read_at_end_parsing_fix.py` (new, 27 tests)
* `tests/dataset/test_mmim_v2_dataset.py` (V14 pins + §3m, 5 new tests)
* `tests/dataset/test_instruction_adapter_v2.py` (version bump)
* `docs/MMIM_READ_AT_END_PARSING_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
  `docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md` (resolution note)
* `data/dataset/mmim-v2/**` (regenerated)

Untouched, verified against the pre-task snapshot: behavioral extraction (`app/behavioral/`),
dependency-analysis *logic* (`app/analysis/dependencies/analyzer.py` — only its *input* AST
changed, not its code), business-rule extraction (`app/modernization/business_rules/`), Java
emission logic (`app/backend/java/`), `benchmark-v1`, `mmim-v1`.
