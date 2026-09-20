# CFG/flow pipeline: `PERFORM A THRU C` target resolution

Branch `feat/mmim-read-at-end-fix` (continued — no new branch requested for this stage). Follows
`docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md` §8, which flagged `PERFORM THRU`'s single-target
parsing limit as a confirmed, orthogonal, out-of-scope gap. `generator_version` `mmim-gen-v15` ->
`mmim-gen-v16`; `dataset_version` stays `mmim-v2`.

## 1. Path traced before any code changed

`PerformStatementNode` (`app/parser/ast/statements.py`) had a single `target: str` field — no way to
represent a range end at all. `ProcedureDivisionParser._parse_perform_statement`'s inline-PERFORM
branch (`app/parser/syntax/procedure_parser.py`) read exactly one `IDENTIFIER` as `target` and
returned immediately, never checking for a following clause:

```python
target = tok.lexeme
stream.advance()
return PerformStatementNode(start_position=start, end_position=stream.current().position, target=target)
```

Neither `THRU` nor `THROUGH` is a reserved word in this lexer (confirmed: `grep -n "THRU" lexer.py`
finds nothing), so for `PERFORM A THRU C`, the leftover `THRU C` tokens reach the paragraph's
statement loop as ordinary, unrecognised tokens, which reports a `SYN001` "unexpected token 'THRU'"
diagnostic and calls `synchronise()` (`app/parser/diagnostics/recovery.py`) — panic-mode recovery
that discards tokens until a period, a division/section boundary, or an identifier-immediately-
followed-by-period ("paragraph label") pattern.

Reproduced on the isolated pre-fix tree for the one real corpus occurrence,
`data/sources/phase6-v2/fallthrough_flow.cbl`:

```cobol
0000-MAIN-CONTROL.
    PERFORM 1000-STAGE-ALPHA THRU 3000-STAGE-GAMMA
    MOVE 'COMPLETED' TO PASS-THRU-STATUS
    GOBACK.
```

This paragraph has **no period** until the very end (a single COBOL sentence spanning three
statements, relying on keyword-based statement-boundary detection rather than periods — the same
period-less-statement pattern this parser already supports elsewhere). Before the fix:
`PerformStatementNode(target="1000-STAGE-ALPHA")` is captured; the `THRU 3000-STAGE-GAMMA` recovery
then keeps scanning for its next anchor and — because there is no period before it — **also consumes
`MOVE`, `'COMPLETED'`, `TO`, `PASS-THRU-STATUS`, and `GOBACK`** (the last one only because it happens
to be immediately followed by the sentence's one period, which the synchroniser's "paragraph label"
heuristic mistakes for a label boundary and eats as well). Directly verified on the isolated tree:

```
0000-MAIN-CONTROL ['PerformStatementNode']          # MOVE and GOBACK are entirely gone
1000-STAGE-ALPHA  ['AddStatementNode']
2000-STAGE-BETA   ['AddStatementNode', 'IfStatementNode']
3000-STAGE-GAMMA  ['AddStatementNode']
diagnostics: [SYN003 (pre-existing, unrelated comment-line issue), SYN001 "unexpected token 'THRU'"]
```

So the damage was never just "the THRU target is lost" — for this specific source's sentence
structure, the recovery's forward scan for a period swallowed two entire subsequent statements too.
This is a direct, mechanical consequence of the *same* defect (the statement loop never terminating
the PERFORM's own token consumption at the correct point), not a second, independent bug: fixing where
the PERFORM statement stops consuming tokens is what stops the runaway recovery.

## 2. `PERFORM SECTION` / other preservation checks (verified, not assumed)

* **`PERFORM SECTION`**: this parser has no PROCEDURE DIVISION `SECTION` header support at all
  (`grep -n "SECTION" procedure_parser.py` finds only a docstring listing it as unimplemented), and a
  section name is syntactically identical to a paragraph name at the PERFORM-statement level
  (`PERFORM <identifier>`). Confirmed **zero** `SECTION` headers exist in the PROCEDURE DIVISION of
  any of the 45 corpus sources (`re.finditer` scoped to text after `PROCEDURE DIVISION` in each
  source). Nothing SECTION-specific exists to preserve or break.
* **Missing/external targets**: unaffected — see §3, §5 below; a genuinely nonexistent name in either
  THRU position still resolves `EXTERNAL`/unresolved, independently per-endpoint.
* **Nested PERFORM / paragraph and section boundaries / existing CFG edges / risk semantics**: none of
  `_skip_to_matching_close_word`, `_SCOPE_OPENING_LEXEMES`/`_SCOPE_CLOSE_WORDS` (EVALUATE's mechanism),
  `_known_paragraphs`, `_maybe_enter_paragraph`, `_seen_logical_edges` dedup, or
  `RiskAnalyzer._detect_unresolved_perform_targets`'s own detection logic were touched.

## 3. The fix

**`app/parser/ast/statements.py`** — `PerformStatementNode` gains `thru_target: str = field(default="",
metadata={"omit_if_empty": True})`; an ordinary `PERFORM A` (no THRU) has `thru_target == ""` and
serializes byte-identically to before (the same `omit_if_empty` mechanism already used by
`IRIf.extra_terms`).

**`app/parser/syntax/procedure_parser.py`** — the inline-PERFORM branch, after consuming `target`,
peeks the next token; if its uppercased lexeme is `"THRU"` or `"THROUGH"` (recognised by lexeme, like
`READ`'s `"AT"` marker in `_skip_read_statement`, since neither is a reserved word), it is consumed and
the following `IDENTIFIER` becomes `thru_target` (a `ParserError` if no identifier follows, exactly as
strict as the existing missing-target check). `PERFORM UNTIL` is untouched.

**`app/ir/instructions.py`** / **`app/ir/builder.py`** — `IRCall` gains the identical
`thru_target: str = field(default="", metadata={"omit_if_empty": True})`; `build_perform_statement`
passes `stmt.thru_target` through verbatim.

**`app/modernization/flow/generator.py`** (the primary fix):

* `FlowGenerationVisitor.__init__` gains `real_paragraph_order: Optional[List[str]] = None`, stored as
  `self._real_paragraph_order` — the same paragraph names as Stage 15's `real_paragraphs` set, but in
  genuine PROCEDURE DIVISION source order (falls back to `list(real_paragraphs)` — arbitrary order —
  for this module's hand-built-IR unit tests, none of which exercise THRU).
* `generate_flow()` computes this ordered list once, from `analysis.ast.procedure_division.paragraphs`
  (the same source `real_paragraphs` already came from in Stage 15), and passes both into the visitor.
* `_DeferredEdge` gains `thru_target: str = ""`; `visit_call`'s PERFORM branch labels the node
  `f"PERFORM {target} THRU {thru_target}"` when set (else unchanged `f"PERFORM {target}"`), and passes
  `node.thru_target` into the deferred edge.
* `finish()`'s single-target resolution logic is extracted, unchanged, into a new
  `_resolve_target_entry(name) -> str` helper (IR-derived entry / cached `empty_<module>_<name>` /
  `ext_<name>` — Stage 15's exact three-way logic, reused verbatim).
* A new `_resolve_thru_edges(deferred)` handles a THRU deferred edge: it looks up `target_paragraph`'s
  and `thru_target`'s indices in `_real_paragraph_order`. If **both** are found and the range is not
  reversed, it resolves **every** paragraph name in the inclusive slice `order[start:end+1]` — COBOL
  defines a THRU range by *physical source position*, not by paragraph naming, so this walks whatever
  is physically between the two names, regardless of name similarity. If **either** endpoint is
  missing, or the range is reversed (not legal COBOL, not fabricated a route for), each endpoint is
  resolved **independently** instead — a missing one still resolves `EXTERNAL`, never silently
  upgraded. One `PERFORMS` edge is added from the PERFORM statement's own node **directly to each**
  resolved paragraph entry (not just the two endpoints, and not relying on paragraph-to-paragraph
  `FALLTHROUGH`, which does not reach a paragraph that was never itself directly visited/targeted and
  has no statements of its own).

**Design note:** an explicit range walk (rather than only a start-edge plus relying on fallthrough) was
chosen because `_paragraph_order`/fallthrough only connects paragraphs that produced at least one IR
node in the normal forward pass — an empty paragraph *in the middle* of a THRU range that is never
independently PERFORMed would otherwise be silently skipped by the fallthrough chain, violating the
"complete ordered range" requirement.

## 4. Tests

44 tests across three files (43 pre-existing-behavior-preserving + updated ones; see below for the
exact count breakdown):

* **`tests/parser/test_perform_thru_parsing_fix.py`** (new, 8 tests) — AST/parser-level: ordinary
  PERFORM has `thru_target == ""` (with and without a trailing period); `PERFORM A THRU C` captures
  both names, with no leftover `SYN001`; `THROUGH` is recognised identically to `THRU`; the statement
  immediately following a THRU clause still parses intact; `PERFORM A THRU A` (degenerate, legal
  COBOL) is captured; a malformed `PERFORM A THRU.` (no identifier after THRU) is diagnosed, not
  silently accepted; the real `t_fallthrough_flow` occurrence is captured exactly
  (`target="1000-STAGE-ALPHA"`, `thru_target="3000-STAGE-GAMMA"`).
* **`tests/modernization/flow/test_perform_thru_fix.py`** (new, 19 tests) — every category the task
  specified: (1) `PERFORM A THRU C` resolves both endpoints; (2) 5-paragraph range all resolve, and a
  paragraph physically outside `[A, C]` does not receive an edge; (3) an empty paragraph inside the
  range resolves via the Stage 15 anchor, not as unresolved; (4)/(5) missing end / missing start /
  both-missing, each endpoint resolved independently; (6) an ordinary PERFORM (with or without a
  missing target) is completely unaffected; (7) real-corpus regression against
  `t_fallthrough_flow` (all 3 stages resolve, no risk, node/edge counts sane); (8) source-order
  preservation — a THRU range whose start/end names would *reverse* under alphabetical sort still
  resolves both by *physical* position, and a middle paragraph named to sort outside `[A, C]` is still
  included because it is physically between them; (9) two `PERFORM A THRU C` call sites share every
  target node, including a shared empty-paragraph anchor — no duplicates; (10) risk analysis reports
  nothing when the whole range resolves, reports only the genuinely-missing endpoint when one is
  missing, and correctly coexists with an unrelated genuinely-missing plain PERFORM in the same
  program.
* **`tests/modernization/flow/test_empty_paragraph_perform_target_fix.py`** (updated, 16 tests, 1
  changed) — the Stage 15 THRU test (which had documented THRU-dropping as a deliberately-preserved,
  out-of-scope gap) is updated in place to the new behavior: both `EMPTY-PARA`/`OTHER-PARA` now
  resolve, the empty one via the same Stage 15 anchor.

**Isolation check:** a byte-copy of the pre-Stage-16 tree was reconstructed precisely (the 5 changed
source files' pre-edit content, taken from what was read before any edit this stage — `generator.py`
in full, the other four as their exact pre-edit regions), scratchpad `baseline7`. The 43 new/updated
tests were copied into it and run as a subprocess with `cwd` rooted there (`app.__file__` confirmed to
resolve inside `baseline7`, not the repo). **23 of 43 fail** on the isolated pre-fix tree — every test
that exercises THRU-specific behavior, including all 8 parser tests (even the "ordinary PERFORM"
ones, since `.thru_target` does not exist as an attribute at all pre-fix) and 14 of 19 flow tests; the
remaining 20 are the deliberately-unaffected-behavior guards (ordinary PERFORM, genuinely-missing
plain PERFORM, Stage 15's other 15 tests), which correctly pass on both trees. All 43 pass on the
current (fixed) tree.

## 5. Real-corpus before/after (45 sources)

```
python -c "import re,glob; pat=re.compile(r'PERFORM\s+[A-Za-z0-9-]+\s+(THRU|THROUGH)\s+[A-Za-z0-9-]+', re.I); ..."
```
over all 45 sources (multi-line-safe) finds **exactly 1** real occurrence: `t_fallthrough_flow`
(`PERFORM 1000-STAGE-ALPHA THRU 3000-STAGE-GAMMA`).

| Measure | Before | After |
|---|---:|---:|
| Sources with a `PERFORM ... THRU ...` node in their CFG | 0 | **1** (`t_fallthrough_flow`) |
| `t_fallthrough_flow` `UNRESOLVED_PERFORM_TARGET` occurrence count | 0 | 0 (unaffected — the pre-fix single captured target already resolved fine; the gap was silent range/statement loss, not a false risk) |
| `t_fallthrough_flow` node count / edge count | 7 / 7 | **9 / 10** (+2 nodes: the recovered `MOVE`/`GOBACK`; +3 edges: 2 more `PERFORMS`, minus the 1 `FALLTHROUGH` that is no longer needed since the paragraph is now correctly terminal) |
| `t_fallthrough_flow` `PROCEDURE DIVISION` syntax diagnostics | `SYN001`, `SYN003` | `SYN003` only (pre-existing, unrelated comment-line issue) |
| All other 44 sources | unchanged | unchanged (identical node/edge-id signatures, confirmed via SHA-256 of the sorted id lists) |
| Genuinely external `CALL` targets elsewhere in the corpus (`t_billing_engine`, `t_transitive_fx`, ...) | `EXTERNAL` | `EXTERNAL`, unaffected |

Isolation for this scan: `app.__file__`/generator SHA-256 confirmed to differ between the two runs
(`53b6882c02ba` before, `0a3237e921a8` after).

**Risk-level consequence (verified, not assumed):** with `MOVE`/`GOBACK` now correctly present,
`RiskAnalyzer` newly detects a genuine `SHARED_MUTABLE_STATE` finding — `PASS-THRU-STATUS` is written
from both `0000-MAIN-CONTROL` (the recovered `MOVE`) and `2000-STAGE-BETA` — a real risk the tool was
previously blind to purely because of the parsing bug, not a false positive introduced by this fix.
The pre-existing `SYNTAX_ERROR` risk's `occurrence_count` correspondingly drops `2 -> 1` (only the
unrelated `SYN003` remains).

## 6. Dataset regeneration (`mmim-gen-v16`)

`app/dataset/version.py::MMIM_GENERATOR_VERSION_V16`.

| | mmim-gen-v15 | mmim-gen-v16 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 (source -> split assignment identical) |
| Examples changed | — | **8**, all for `t_fallthrough_flow`: PROGRAM_UNDERSTANDING, DEPENDENCY_REASONING, RISK_CLASSIFICATION, BUSINESS_RULE_EXTRACTION, MODERNIZATION_STRATEGY, TRANSFORMATION_PLANNING, COBOL_TO_JAVA, and VALIDATION_REASONING's *embedded raw `analysis` block only* |
| `business_rule_extraction` rule counts | 157 total | 157 total, unchanged (0 rule conditions changed; `t_fallthrough_flow`'s own `rule_count` stays 1 — MOVE/GOBACK are not conditional rules) |
| VALIDATION_REASONING **expected_output** (test suite/hash) | — | byte-identical for every source, including `t_fallthrough_flow` (confirmed directly) |
| `compiles == True` count | 41 | 41, unchanged (`t_fallthrough_flow` stays `True` -> `True`; its generated Java *text* changes — see §7 — but still compiles) |
| Ground truth (deterministic / executable_verified / reference) | 345 / 2 / 4 | unchanged |
| Benchmark leakage | clean, 0 overlap | clean, 0 overlap |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |
| Instruction-adapter split counts / per-task shape / max tokens | — | identical (15,010 max) |

Two independent full regenerations are byte-identical (`all.jsonl`, `train.jsonl`, `validation.jsonl`,
`test.jsonl`, `manifest.json`, `split_manifest.json`, `leakage_report.json`, and every file under
`instruction/`, verified with `cmp`/`diff -rq` — an initial `sha256sum`-based check falsely reported a
difference, traced to GNU coreutils' filename-escaping convention prepending a literal backslash to the
hash line for a path containing backslashes; the 64-hex-character hashes themselves were identical).
`benchmark-v1` and `mmim-v1` (144 examples, `mmim-gen-v1`) are untouched.

**Serialization pitfall caught before trusting the diff:** the first regeneration attempt (before
`PerformStatementNode.thru_target` had `omit_if_empty` metadata) showed **247** examples "changed"
across 41 sources — a false signal: every `PerformStatementNode` anywhere in the corpus (not just
`t_fallthrough_flow`'s) gained a serialized `"thru_target": ""` in its embedded AST. Adding the same
`omit_if_empty` field metadata already used by `IRCall.thru_target` (and, before it,
`IRIf.extra_terms`) to the AST node too corrected this; the dataset was regenerated a second time,
after which only the genuinely-affected 8 examples for 1 source remained.

## 7. New independent gaps discovered — reproduced, documented, NOT fixed

**The Java backend does not read `IRCall.thru_target` at all**, and its pre-existing, already-
documented "flat paragraph concatenation" architecture (statements are emitted into `run()` in
IR-instruction order, not scoped by the paragraph a `PERFORM` actually invokes) means fixing the
parser/CFG defect changes `t_fallthrough_flow`'s generated Java in a way that is visible but was not
asked for and is not fixed here:

* **Before**, because `GOBACK` was silently dropped from the AST, the backend's flat concatenation
  never found a `return` to stop at, so it happened to include `1000-STAGE-ALPHA`/`2000-STAGE-BETA`/
  `3000-STAGE-GAMMA`'s `ADD`/`IF` statements in `run()` anyway (by accident, attributed to the wrong
  conceptual scope) alongside an unreachable `f1000StageAlpha()` stub.
* **After**, `GOBACK` is correctly present and terminates the flat concatenation after
  `passThruStatus = "COMPLETED";` — so the actual logic the `PERFORM ... THRU ...` was supposed to
  invoke is now **absent** from `run()` entirely, replaced by only the unreachable stub method call.

Both versions compile (`javac 25.0.3`, exit 0 for each); neither is behaviorally correct Java, and
this was already true before this task (the flat-concatenation limitation itself is not new — see
`docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md` §6). This fix only changes *which* statements the
backend's pre-existing limitation happens to include/exclude for this one source; it does not
introduce the limitation, and per this task's explicit scope ("Do not modify... Java generation"),
the Java backend was not touched.

`PERFORM THRU`'s interaction with the dependency serializer's `internal_performs` list
(`app/dataset/mmim_builder.py::_perform_targets`) was checked and found unaffected: it still lists only
`target` (`['1000-STAGE-ALPHA']`), never `thru_target` — out of this task's CFG/flow scope, not
modified.

## 8. Exact files changed (this task)

* `app/parser/ast/statements.py` (`PerformStatementNode.thru_target`)
* `app/parser/syntax/procedure_parser.py` (inline-PERFORM `THRU`/`THROUGH` clause; `PERFORM UNTIL`
  untouched)
* `app/ir/instructions.py` (`IRCall.thru_target`)
* `app/ir/builder.py` (`build_perform_statement` passes `thru_target` through)
* `app/modernization/flow/generator.py` (`_real_paragraph_order`; `_DeferredEdge.thru_target`;
  `visit_call`'s THRU label/deferred-edge; `_resolve_target_entry` extracted; new
  `_resolve_thru_edges`; `generate_flow`'s ordered-paragraph-list computation)
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V16`)
* `tests/parser/test_perform_thru_parsing_fix.py` (new, 8 tests)
* `tests/modernization/flow/test_perform_thru_fix.py` (new, 19 tests)
* `tests/modernization/flow/test_empty_paragraph_perform_target_fix.py` (1 test updated to the new
  THRU behavior; 15 unchanged)
* `tests/dataset/test_mmim_v2_dataset.py` (V16 pins + §3o, 6 new tests; 2 pre-existing pinned
  assertions on `t_fallthrough_flow`'s generated Java corrected to the new, legitimately-changed text)
* `tests/dataset/test_instruction_adapter_v2.py` (version bump)
* `tests/backend/test_java_literal_emission_fix.py` (1 pre-existing pinned real-corpus literal
  assertion for `fallthrough_flow.cbl` corrected from `"SKIPPED-ALPHA"` — no longer reachable in the
  generated Java, see §7 — to `"COMPLETED"`, the literal from the now-recovered `MOVE`; found by the
  full suite, not the focused runs, since this test lives outside `tests/modernization`/`tests/parser`/
  `tests/dataset`)
* `docs/MMIM_PERFORM_THRU_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
  `docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md` (§8 resolution note)
* `data/dataset/mmim-v2/**` (regenerated)

Untouched, verified against the pre-task snapshot: `PERFORM UNTIL` parsing, `_skip_to_matching_close_word`
and EVALUATE's scope mechanism, `READ`/`GO TO` handling, `RiskAnalyzer`'s detection logic itself (only
its CFG *input* changed), behavioral extraction, business-rule *extraction logic* (only its AST *input*
changed for the one affected source), the Java backend, `benchmark-v1`, `mmim-v1`.
