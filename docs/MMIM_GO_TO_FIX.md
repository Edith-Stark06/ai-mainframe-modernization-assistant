# Parser: real COBOL `GO TO` support

Branch `feat/mmim-read-at-end-fix` (continued — no new branch requested for this stage). Follows
`docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md` §2/§8, which flagged `GO TO`'s parser-level
unsupported-statement gap as a confirmed, orthogonal, out-of-scope gap discovered while fixing PERFORM
target resolution. `generator_version` `mmim-gen-v16` -> `mmim-gen-v17`; `dataset_version` stays
`mmim-v2`.

## 1. Path traced before any code changed

`"GO"` was in `ProcedureDivisionParser._UNSUPPORTED_STATEMENT_LEXEMES` (`app/parser/syntax/
procedure_parser.py`) since this parser's inception — a real `GO TO paragraph-name` statement never
reached `_parse_statement`'s per-verb dispatch table at all; it was routed to the generic
`_skip_unsupported_statement` path, producing a single `SYN100` diagnostic and zero AST nodes.

Everything **downstream** of the parser already existed and was already correctly wired, confirmed
directly before any code changed:

* `app/parser/ast/statements.py::GoToStatementNode` — already defined, `target: str`, single-target
  shape, `accept()` dispatching to `visit_go_to_statement`.
* `app/ir/builder.py::IRBuilder.build_go_to_statement` — already lowers a `GoToStatementNode` into an
  `IRJump(target=stmt.target)`; already registered in `_translate_statement`'s `isinstance` dispatch
  table (`if isinstance(stmt, GoToStatementNode): self.build_go_to_statement(stmt)`).
* `app/modernization/flow/generator.py::FlowGenerationVisitor.visit_jump` — already creates a
  `"GO TO <target>"` `NodeType.PROCESS` node, links pending edges to it, appends a
  `_DeferredEdge(node_id, node.target, EdgeType.GOES_TO)`, and sets `self._pending = []` (terminal —
  no accidental fallthrough after an unconditional jump).
* `finish()`'s deferred-edge resolution (`_resolve_target_entry`, extracted in
  `docs/MMIM_PERFORM_THRU_FIX.md`) already treats `GOES_TO` and `PERFORMS` edges identically: existing
  non-empty paragraph resolves to its real entry; existing-but-empty paragraph resolves to the Stage
  15 cached `empty_<module>_<paragraph>` anchor; genuinely missing paragraph resolves to `ext_<name>`
  `EXTERNAL` — the function takes only a target name, not an edge type, so it needed zero changes.
* `app/modernization/risk/analyzer.py::_detect_complex_control_flow` — already counts
  `EdgeType.GOES_TO` edges generically (`goto_edges = [e for e in flow.edges if e.edge_type is
  EdgeType.GOES_TO]`), already folds them into `occurrence_count` and severity
  (`MEDIUM` when any exist) — confirmed unmodified since task #110, simply never exercised by real
  input before now.

This was already directly confirmed, before this task, by
`tests/ir/test_ir_ast_node_coverage.py::TestGoToAndAcceptUnreachableFromParser` (hand-built
`GoToStatementNode` -> `IRJump` proven correct) and by
`tests/modernization/flow/test_empty_paragraph_perform_target_fix.py::test_go_to_an_empty_paragraph_also_resolves`
(hand-built IR proving the generator's own `GOES_TO` resolution correct). **No IR/CFG/risk code
changed in this task** — tracing confirmed the existing `IRJump`/`GOES_TO` design was already
sufficient, exactly as the task anticipated should be checked before redesigning anything.

## 2. Scope: what the real corpus actually contains

```
grep -n '\bGO\s+TO\b' data/sources/phase6-v2/*.cbl   # (multi-line-safe regex, case-insensitive)
```

Exactly **one** source, `t_goto_spaghetti.cbl`, contains real `GO TO` usage — **7** occurrences (one
grep hit is a comment line, `* CATEGORY D: ... GO TO CONTROL FLOW`, correctly excluded from the
statement count):

```cobol
1000-ENTRY-POINT.
    MOVE 'STARTED' TO TERMINAL-STATE
    IF STEP-INDEX = 1
        GO TO 2000-STAGE-ALPHA        [1] -- inside IF's THEN branch
    ELSE
        GO TO 3000-STAGE-BETA         [2] -- inside IF's ELSE branch
    END-IF.

2000-STAGE-ALPHA.
    ADD 10 TO ACCUMULATOR
    ADD 1 TO STEP-INDEX
    IF ACCUMULATOR < 30
        GO TO 4000-LOOP-BACK          [3] -- inside IF, no ELSE
    END-IF
    GO TO 5000-FINAL-STAGE.           [4] -- unconditional, paragraph's last statement

3000-STAGE-BETA.
    ADD 50 TO ACCUMULATOR
    GO TO 5000-FINAL-STAGE.           [5]

4000-LOOP-BACK.
    ADD 1 TO RETRY-COUNTER
    IF RETRY-COUNTER > 5
        GO TO 5000-FINAL-STAGE        [6]
    END-IF
    GO TO 2000-STAGE-ALPHA.           [7] -- the loop-back
```

All 7 are the **single-target** `GO TO paragraph-name` form. A separate search confirmed **zero**
occurrences of `DEPENDING` anywhere in the corpus, so `GO TO A B C DEPENDING ON identifier`
(a computed multi-way jump) is deliberately **not implemented** — see §3.

This is also a rich real-world shape worth noting explicitly: 4 of the 7 occurrences (lines 17, 19, 26,
37) are **nested inside an `IF`'s THEN or ELSE branch**, not only at a paragraph's top level (the other
3 — lines 28, 32, 39 — are unconditional, each the last statement of its paragraph). *(Correction,
Stage 19: this paragraph originally said "5 of the 7 … the other 2"; that miscounted. Re-derived from
the IR: 4 nested, 3 top-level, 6 forward jumps and 1 backward — line 39.)* This exercises both the paragraph-level
statement loop and `_parse_if_statement`'s THEN/ELSE statement loops, which already dispatch through
the same `_parse_statement`/`_STATEMENT_LEXEMES` mechanism (confirmed by reading `_parse_if_statement`
directly: its THEN/ELSE loops check `tok.lexeme.upper() in _STATEMENT_LEXEMES` and call
`self._parse_statement(state)`, identically to the paragraph-level loop).

## 3. The fix (`app/parser/syntax/procedure_parser.py` only)

* `"GO"` moved from `_UNSUPPORTED_STATEMENT_LEXEMES` to `_STATEMENT_LEXEMES`.
* `_parse_statement` gained one dispatch line: `if upper == "GO": return
  self._parse_go_to_statement(state)`.
* New method `_parse_go_to_statement`: consumes `GO`, requires the next token's lexeme to be `TO`
  (neither `GO` nor `TO` is a reserved word in this lexer — both arrive as plain `IDENTIFIER` tokens,
  so `TO` is recognised by lexeme, the same way `PERFORM`'s `THRU`/`THROUGH` markers and `READ`'s `AT`
  marker already are), then requires and consumes one `IDENTIFIER` as `target`, then calls
  `_consume_optional_period` (the same explicit-period pattern `DISPLAY`/`MOVE` use). Raises
  `ParserError` if `TO` or the target is missing — a malformed `GO TO` is diagnosed, not silently
  accepted.
* **Multi-target `DEPENDING ON` is not implemented** (§2: zero real usage). If encountered, the method
  still captures the first name as `target` and returns; the leftover tokens (`B C DEPENDING ON X`)
  are left on the stream for the paragraph-level statement loop's existing unexpected-token recovery
  (`SYN001`, panic-mode `synchronise()`) to report and safely skip — exactly the same disclosed
  behavior `docs/MMIM_PERFORM_THRU_FIX.md` §1 already established as the safe, honest response to an
  unimplemented clause extension, rather than silently narrowing a runtime-computed multi-way jump down
  to "always go to the first name". Proven, not assumed, by
  `test_go_to_depending_on_is_not_silently_narrowed_to_the_first_target`.

`PERFORM UNTIL` parsing, `_skip_to_matching_close_word`/`_SCOPE_OPENING_LEXEMES` (EVALUATE's scope
mechanism), `READ`'s `_skip_read_statement`, and every other statement parser are untouched.

## 4. Tests

34 new tests across two files, plus the Stage 15 hand-built-IR test's docstring updated (not its
assertions or behavior):

* **`tests/parser/test_go_to_parsing_fix.py`** (new, 9 tests) — simple `GO TO` (with and without a
  trailing period); malformed `GO` without `TO`, and `GO TO` without a target, both diagnosed;
  `GO TO` nested inside an IF's THEN branch, and inside both THEN and ELSE branches (the real corpus's
  actual shape); a statement following a nested `GO TO` still parses intact; `GO TO A B DEPENDING ON
  X` is not silently narrowed (§3); the real `t_goto_spaghetti` source's all 7 occurrences captured
  with exact targets.
* **`tests/modernization/flow/test_go_to_fix.py`** (new, 16 tests) — every category the task
  specified: (A) simple `GO TO` creates a `GOES_TO` node/edge; (B) existing non-empty / missing /
  empty / repeated targets, including a repeated empty target sharing the Stage 15 cached anchor; (C)
  CFG semantics — a `GO TO` is terminal (no `FALLTHROUGH` edge is fabricated after it), both branches
  of an IF ending in `GO TO` leave nothing pending, an IF with `GO TO` only in THEN still correctly
  falls through on the FALSE path (Stage-15-era logic, proven unaffected); (D) the target string
  survives AST -> IR unchanged; (E) a program without any `GO TO` is completely unaffected (no
  `GO TO`-named node, no `GOES_TO` edge, no spurious risk); (F) real-corpus regression against
  `t_goto_spaghetti` — all 7 targets resolve, the loop-back target (`2000-STAGE-ALPHA`, reached from
  two different call sites) shares one cached node, no `FALLTHROUGH` edge exists anywhere in this
  all-GO-TO/GOBACK-terminated program, no `UNRESOLVED_PERFORM_TARGET` risk, and
  `COMPLEX_CONTROL_FLOW`'s evidence correctly reports "7 GO TO transfer(s)".
* `tests/modernization/flow/test_empty_paragraph_perform_target_fix.py::test_go_to_an_empty_paragraph_also_resolves`
  — docstring updated to note the parser gap it documented is now fixed; kept as a lower-level
  `FlowGenerationVisitor` unit test (its hand-built-IR assertions are unaffected, since
  `FlowGenerationVisitor` itself was never touched).

**Isolation check:** a byte-copy of the pre-Stage-17 tree was reconstructed precisely (the single
changed source file's pre-edit content, reconstructed by reversing this task's five specific edits —
import, `_STATEMENT_LEXEMES`, `_UNSUPPORTED_STATEMENT_LEXEMES`, the dispatch line, and the new method
— against the current file), scratchpad `baseline8`. The 25 new/updated GO-TO-specific tests were
copied into it and run as a subprocess with `cwd` rooted there (`app.__file__` confirmed to resolve
inside `baseline8`, not the repo, and the parser's SHA-256 confirmed to differ:
`8a03772cd4b8` before vs `94bbe53f180c` after). **21 of 41** tests in the two new files fail on the
isolated pre-fix tree (every test exercising real `GO TO` parsing or CFG resolution — including tests
whose assertions merely reference a `GoToStatementNode`/`target` field, since the parser could not
produce one at all); the rest (malformed-input diagnostics that pass either way, and the
program-without-GO-TO regression guards) correctly pass on both trees. All 41 pass on the current
(fixed) tree.

## 5. Real-corpus before/after (45 sources)

Isolation for this scan: `app.__file__`/parser SHA-256 confirmed to differ between the two runs
(matching §4's values).

| Measure | Before | After |
|---|---:|---:|
| Sources with real `GO TO` usage | 1 (`t_goto_spaghetti`) | 1 (unchanged — the corpus itself is untouched) |
| `t_goto_spaghetti` AST statement count | 10 | 17 (+7, exactly the 7 recovered `GoToStatementNode`s) |
| `t_goto_spaghetti` `IRJump` count | 0 | 7 |
| `t_goto_spaghetti` CFG node count / edge count | 11 / 12 | 18 / 19 (+7 / +7 — one new `GO TO <target>` node and one new `GOES_TO` edge per statement) |
| `t_goto_spaghetti` syntax diagnostic codes | `SYN003`, `SYN100` (×7) | `SYN003` only (pre-existing, unrelated comment-line issue) |
| `t_goto_spaghetti` `UNSUPPORTED_SYNTAX` risk | 7 occurrences | **gone** (0 — correctly, since `GO`/`GO TO` is no longer unsupported syntax) |
| `t_goto_spaghetti` `COMPLEX_CONTROL_FLOW` risk | 3 occurrences (`3 decision point(s)`, `0 loop back-edge(s)`, `0 GO TO transfer(s)`), severity LOW | 10 occurrences (`3 decision point(s)`, `0 loop back-edge(s)`, `7 GO TO transfer(s)`), severity **MEDIUM** — the pre-existing, unmodified detector's evidence becomes accurate for the first time |
| `t_goto_spaghetti` `SHARED_MUTABLE_STATE` / `SYNTAX_ERROR` risks | 2 objects / 1 | unchanged (unrelated to GO TO) |
| `t_goto_spaghetti` generated Java | empty `if` bodies, ELSE branch silently absent | each `IRJump` site emits the Java backend's pre-existing `// TODO: translate IRJump` placeholder (previously dead code — nothing had ever produced an `IRJump` from real source before); `compiles` stays `True` -> `True`, verified directly with real `javac 25.0.3` on both versions |
| All other 44 sources | unchanged | unchanged (identical AST/IR/CFG/risk snapshots) |
| Genuinely external `CALL`/`PERFORM`/`GO TO` targets elsewhere in the corpus | `EXTERNAL` | `EXTERNAL`, unaffected |

## 6. Dataset regeneration (`mmim-gen-v17`)

`app/dataset/version.py::MMIM_GENERATOR_VERSION_V17`.

| | mmim-gen-v16 | mmim-gen-v17 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 (source -> split assignment identical) |
| Examples changed | — | **7**, all for `t_goto_spaghetti`: PROGRAM_UNDERSTANDING, DEPENDENCY_REASONING, RISK_CLASSIFICATION, BUSINESS_RULE_EXTRACTION, MODERNIZATION_STRATEGY, TRANSFORMATION_PLANNING, COBOL_TO_JAVA |
| `business_rule_extraction` rule counts | 157 total | 157 total, unchanged (0 rule conditions changed; `t_goto_spaghetti`'s own `rule_count` stays 0 — none of its logic yields an extractable business rule) |
| VALIDATION_REASONING | — | `t_goto_spaghetti` has no example in either version (skipped, `no_derivable_behavioral_tests`, in both) — confirmed identical skip reason/decision; only that skip record's own `parser_status.unsupported_codes` field drops `["SYN100"]` -> `[]`, which is not itself a ground-truth change. Coverage stays 36/45 sources |
| `compiles == True` count | 41 | 41, unchanged (`t_goto_spaghetti` stays `True` -> `True`; its generated Java *text* changes — §5 — but still compiles) |
| Ground truth (deterministic / executable_verified / reference) | 345 / 2 / 4 | unchanged |
| Benchmark leakage | clean, 0 overlap | clean, 0 overlap |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |
| Instruction-adapter split counts / per-task shape / max tokens | — | identical (15,010 max) |

Two independent full regenerations are byte-identical (`all.jsonl`, `train.jsonl`, `validation.jsonl`,
`test.jsonl`, `manifest.json`, `split_manifest.json`, `leakage_report.json`, and every file under
`instruction/`, verified with `cmp`/`diff -rq`). `benchmark-v1` and `mmim-v1` (144 examples,
`mmim-gen-v1`) are untouched.

## 7. New independent gaps discovered — reproduced, documented, NOT fixed

None new, and none required for GO TO's own correctness. Confirmed, not fixed, per this task's own
§13 boundary:

* **`GO TO A B C DEPENDING ON X`** remains unimplemented — §3, with an explicit regression test proving
  the leftover tokens are safely diagnosed rather than silently mis-narrowed. Not present anywhere in
  the real corpus.
* **`RiskAnalyzer._detect_unresolved_perform_targets` only checks `EdgeType.PERFORMS` edges, not
  `EdgeType.GOES_TO`.** A `GO TO` to a genuinely nonexistent paragraph is correctly represented as an
  `EXTERNAL` CFG node (verified directly: `ext_<name>`, never fabricated), but is not currently
  surfaced as any risk finding — this detector's narrower-than-`GOES_TO` scope pre-dates this task and
  was simply unreachable before (a missing `GO TO` target could previously only be constructed via
  hand-built IR). Not exercised by the real corpus (all 7 real `GO TO` targets resolve). Extending this
  detector is a risk-analysis enhancement, not required for `GO TO` parsing/CFG correctness itself, so
  it is documented here rather than fixed.
  **Resolved in Stage 18 — see §9.** (No generator bump: the real corpus has no missing GO TO target.)
* **The Java backend's flat-paragraph-concatenation architecture** (already documented,
  `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md` §6, `docs/MMIM_PERFORM_THRU_FIX.md` §7) does not give
  `IRJump` any real Java control-flow translation — it already had a `// TODO: translate IRJump`
  placeholder (dead code before this task), which is honest and safe (no fabricated `goto`, no removed
  statement) but does not produce behaviorally-equivalent Java. Not fixed here — outside this task's
  scope (Java generation). **Resolved for `GO TO` in Stage 19 — see §10** (PERFORM's flat/stub
  translation is unchanged and remains a separate gap).

Explicitly **not touched**, per the task's own §13 list and confirmed unaffected: Java `String ==`
semantics, FILE SECTION field declarations, the `NOT ((a) AND (b))` behavioral-parser limitation,
`PERFORM UNTIL` recovery, `IF <var> NOT = <literal>`, the Java `PERFORM THRU` architecture gap, and
`READ`/`AT END` (already resolved, not revisited).

## 8. Exact files changed (this task)

* `app/parser/syntax/procedure_parser.py` (`"GO"` moved from `_UNSUPPORTED_STATEMENT_LEXEMES` to
  `_STATEMENT_LEXEMES`; new `_parse_go_to_statement`; one new dispatch line in `_parse_statement`)
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V17`)
* `tests/parser/test_go_to_parsing_fix.py` (new, 9 tests)
* `tests/modernization/flow/test_go_to_fix.py` (new, 16 tests)
* `tests/modernization/flow/test_empty_paragraph_perform_target_fix.py` (1 test's docstring updated;
  no assertion changed; 15 others untouched)
* `tests/ir/test_ir_ast_node_coverage.py` (module docstring split GO TO out from ACCEPT;
  `EXPECTED_IR_MAPPING`'s `GoToStatementNode` entry `None` -> `(IRJump,)`; the class/test documenting
  "GO TO unreachable from real source" renamed and inverted to document it now IS reachable — ACCEPT's
  own, separate, still-true "unreachable" status is untouched)
* `tests/dataset/test_mmim_v2_dataset.py` (V17 pins + §3p, 6 new tests)
* `tests/dataset/test_instruction_adapter_v2.py` (version bump)
* `tests/analysis/coverage/test_analyzer.py` (2 tests' "unsupported statement" example changed from
  `GO TO` to `OPEN`, which remains genuinely unsupported — preserving each test's actual intent)
* `tests/api/test_modernization_phase5.py` (the `_UNSUPPORTED` fixture's statement changed from
  `GO TO` to `OPEN`, for the same reason)
* `tests/modernization/scoring/test_phase5_regression.py` (2 tests' "unsupported statement" example
  changed from `GO TO` to `OPEN`, for the same reason)
* `docs/MMIM_GO_TO_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
  `docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md` (§8 resolution note)
* `data/dataset/mmim-v2/**` (regenerated)

Untouched, verified against the pre-task snapshot: `GoToStatementNode`, `IRJump`,
`IRBuilder.build_go_to_statement`, `FlowGenerationVisitor` (including `visit_jump`,
`_resolve_target_entry`, `finish()`), `RiskAnalyzer._detect_complex_control_flow`, `PERFORM`/`PERFORM
UNTIL`/`PERFORM THRU` parsing, `READ` parsing, the Java backend, `benchmark-v1`, `mmim-v1`.

## 9. Stage 18 — `UNRESOLVED_GO_TO_TARGET` risk (resolves the §7 risk-detector gap)

**Investigated before changing anything.** On the Stage 17 tree, a `GO TO` to a nonexistent paragraph
produced an `EXTERNAL` node (`ext_<name>`) and a `GOES_TO` edge — correct, never fabricated — but *no*
unresolved-target risk: only `COMPLEX_CONTROL_FLOW` counted the edge, and in a program with both a
missing `PERFORM` and a missing `GO TO` only the `PERFORM` appeared in any risk evidence. Existing
non-empty and existing-but-empty targets (Stage 15 `empty_<module>_<paragraph>` anchor) raised nothing,
as intended. The gap was real, but **synthetic-only**: a direct AST + regex cross-check of all 45 sources
found the same 7 `GO TO` statements (all in `t_goto_spaghetti`), and all 7 targets are real paragraphs —
0 `GOES_TO` edges into an `EXTERNAL` node anywhere in the corpus.

**Fix (risk layer only).** A dedicated category, not a reuse of `UNRESOLVED_PERFORM_TARGET`: that
category's title/explanation/evidence/mitigation are PERFORM-specific and the strategy analyzer sums it as
"unresolved PERFORM target(s)" (reusing it would mislabel GO TO sites there). There is no generic
control-flow category in the taxonomy, so `RiskCategory.UNRESOLVED_GO_TO_TARGET` follows the existing
naming and the "one detector per category" convention, with `_detect_unresolved_go_to_targets` mirroring
the PERFORM detector (same MEDIUM severity, confidence 1.0, one aggregated risk with per-target
`GO TO 'X' (unresolved) — N site(s)` evidence, `occurrence_count` = number of sites, id
`RISK-unresolved-go-to-target-NNN`). It is driven by the **edge type**: only a `GOES_TO` edge whose target
is `EXTERNAL`. A `GOES_TO` target is always resolved *as a paragraph* by the flow generator, so this means
the paragraph does not exist; an `EXTERNAL` node reached by `CALLS`/`PERFORMS` (a real external `CALL`, an
unresolved `PERFORM`) never triggers it — including when a `CALL 'X'` and a `GO TO X` share the same
`ext_X` node id (tested). Not changed: Stage 15 target resolution, Stage 16 PERFORM THRU, the flow
generator, the strategy analyzer (its `unresolved_perform_count` stays PERFORM-only), the PERFORM
detector.

**Files:** `app/modernization/risk/models.py`, `app/modernization/risk/analyzer.py`,
`tests/modernization/risk/test_unresolved_go_to_target.py` (new, 24 tests).

**Isolation.** The 24 tests were run on a byte-copy of the pre-edit tree with `cwd` rooted there
(`app.__file__` confirmed inside the copy; the new category confirmed absent): **7 fail** — each asserts
a GO TO risk exists, and fails behaviorally (the risk list contains no such entry), not with an
`AttributeError` (category values are compared as strings on purpose) — and the other 17 (existing /
empty target, PERFORM, external CALL, CFG termination, no fabricated `FALLTHROUGH`, whole-corpus guard,
negative edge-type cases) pass on both trees. All 24 pass on the fixed tree.

**Real corpus before/after (45 sources, snapshot before any edit vs after):** 0 sources changed in any
recorded field — GO TO AST count 7→7, `IRJump` 7→7, `GOES_TO` edges 7→7, `GOES_TO`→`EXTERNAL` 0→0,
`EXTERNAL` nodes 14→14, CFG nodes/edges 646/692→646/692, risk objects 131→131, per-category risk
occurrence totals identical, every Java text hash identical, brace balance 45/45.

**Dataset: unchanged, generator stays `mmim-gen-v17` (no bump).** Two independent regenerations were
compared against the on-disk v17 dataset by SHA-256: `all/train/validation/test.jsonl`, both manifests,
`leakage_report.json` and all of `instruction/` are byte-identical across all three. The one file that
differs, `validation_report.json`, differs *only* in its embedded `path` field (it records the directory
it was written to); every content field is identical. `data/dataset/mmim-v2` was not touched.

**Remaining (unchanged, out of scope):** `GO TO ... DEPENDING ON`; Java behavioral translation of
`IRJump`; the strategy analyzer does not read the new category (a design decision for a later stage — a
missing GO TO target would still count toward its generic "≥2 MEDIUM-or-higher risks" threshold).

## 10. Stage 19 — Java translation of `GO TO` / `IRJump` (`mmim-gen-v18`)

**Investigated before editing.** The Java backend lowers only `modules[0].functions[0].blocks[0]` — one
flat instruction list with every paragraph concatenated — into a single `run()`. It has no paragraph
labels, no paragraph methods, no dispatcher; PERFORM targets become *empty stub methods* (paragraph
bodies are not carried), and `IRJump` reached the generic "unsupported instruction" fallback
(`// TODO: translate IRJump` + `BE005`). Java has no `goto`. Two facts made a correct translation
possible without touching the IR, parser, or emitters: **every** IR instruction — including the
`IRElse`/`IREndIf` markers — carries `.paragraph`, so paragraph regions are recoverable inside the
backend; and the single call site (`AnalysisService`) has the AST in hand. One fact is a genuine
blocker for a pure-IR backend: **the IR has no record of a paragraph with no statements**, so a
`GO TO` to an empty paragraph is indistinguishable from a `GO TO` to a missing one.

**Pre-fix behavior, executed (not assumed).** `t_goto_spaghetti`'s Java compiled and ran, but every jump
was ignored and every paragraph fell through (`accumulator=60, retryCounter=1, stepIndex=1`).

**Verified facts about the 7 real GO TOs** (re-derived from the IR): 6 forward, 1 backward (line 39 →
`2000-STAGE-ALPHA`); 4 inside IF branches (lines 17 THEN, 19 ELSE, 26 THEN, 37 THEN), 3 top-level
unconditional (28, 32, 39); targets repeat (`5000-FINAL-STAGE` ×3, `2000-STAGE-ALPHA` ×2).

**Fix (Java backend only + one call-site argument).** When — and only when — the entry block contains an
`IRJump` whose target is a known paragraph, `_collect_statements` lowers the body as a dispatcher:

```java
int _paragraph = 0;
_dispatch:
while (true) {
    switch (_paragraph) {
        case 0: // 1000-ENTRY-POINT
            ...
            if (true) { _paragraph = 1; continue _dispatch; } // GO TO 2000-STAGE-ALPHA
        case 1: // 2000-STAGE-ALPHA
            ...
    }
    break _dispatch;
}
```

Every paragraph is a `case`; Java `switch` fall-through *is* COBOL's sequential paragraph fall-through, so
ordinary flow needs no extra code. A jump is a labeled `continue`, valid forward or backward, from any
IF depth, and out of an inline `PERFORM UNTIL` loop. Design decisions that matter:

* **`if (true) { … }` around each jump** — javac treats an `if` as able to complete normally whatever its
  condition, so dead code after an unconditional GO TO (dead in COBOL too), or after an IF/ELSE whose
  branches *both* jump, never becomes an "unreachable statement" compile error. (The pre-existing
  reachability tracking deliberately does not model "both branches return"; a plain `continue` would have
  made the very common spaghetti shape uncompilable.)
* **`_paragraph` / `_dispatch`** contain an underscore, which `to_java_field_name` can never produce (it
  splits on every `-`/`_`), so they cannot shadow a COBOL-derived name — a plain `pc` would shadow a COBOL
  item named `PC` (tested).
* **Reachability** — a `STOP RUN`/`GOBACK` still ends its own `case`, but the next `case` label makes code
  reachable again, so the dead-region tracker is reset there (otherwise a paragraph reachable only by
  `GO TO` after a `STOP RUN` would be silently dropped).
* **Empty paragraphs** — `AnalysisService` passes the AST's paragraph *names* (not the AST; the module's
  "IR only" design is preserved) as an optional `paragraph_order`; every paragraph, empty ones included,
  gets a `case`, so a jump to an empty paragraph falls through to the next real one. It is used only if it
  covers every paragraph the IR mentions.
* **Unresolvable target** — left as `// TODO: GO TO 'X' cannot be translated (BE012)` + a `BE012` WARNING,
  never guessed. A program whose *only* jumps are unresolvable takes the flat path unchanged (still the old
  TODO + `BE005`), byte for byte.
* **Isolation** — no translatable jump ⇒ identical flat lowering.

Not changed: parser, AST, IR, CFG, flow generator, risk analyzer (including Stage 18's category),
`statement_emitter.py`, `control_flow_emitter.py`, PERFORM handling.

**Files:** `app/backend/java/generator.py`, `app/analysis/service.py` (one argument),
`app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V18`), `tests/backend/test_java_go_to_translation.py`
(new, 28 tests), `tests/dataset/test_mmim_v2_dataset.py` (V18 pins + §3q, 5 tests),
`tests/dataset/test_instruction_adapter_v2.py`, `data/dataset/mmim-v2/**`.

**Behavioral validation.** Each executable test compiles the generated Java with real `javac`, *runs* it
via a reflection harness, and compares every field with an independent interpreter of the same IR under
COBOL semantics (paragraph fall-through, `GO TO`, `STOP RUN`, IF/ELSE, `PERFORM UNTIL`); the oracle never
reads the Java text. Both sides are seeded identically. Covered: the task's skip-a-paragraph example,
forward, backward, GO TO in THEN and in ELSE (each condition outcome), an if/else whose branches both jump
followed by dead code, repeated targets sharing one label, multi-statement target with fall-through after
it, a paragraph reachable only by jump after a `STOP RUN`, a jump out of an inline `PERFORM UNTIL`, the
`PC` name-collision case, empty and trailing-empty targets, and `t_goto_spaghetti` from three initial
states — including the program's real `VALUE` state, which drives `2000→4000→2000→4000→2000→5000` and ends
`ACCUMULATOR=30, STEP-INDEX=4, RETRY-COUNTER=2, TERMINAL-STATE=COMPLETED` in both the oracle and the Java.
Fallback rules are tested on hand-built IR (unresolvable-only stays flat; missing target beside a
resolvable one; `paragraph_order` given / not given / not covering; `STOP RUN` reachability).

**Pre-fix proof.** The 28 tests were run on a byte-copy of the pre-edit tree with `cwd` rooted there
(`app.__file__` inside the copy): **21 fail, 7 pass**. Causes: behavioral (the pre-fix Java leaves e.g.
`wsY=2` where the oracle says `0`, i.e. it executes a paragraph the GO TO skips), text assertions, and 2
`TypeError: unexpected keyword 'paragraph_order'` (that parameter does not exist pre-fix). The 7 passing on
both trees are the intended guards: no-GO-TO stays flat, an unresolvable-only jump keeps today's TODO,
PERFORM unchanged, brace balance, and the two not-taken IF outcomes (where fall-through legitimately equals
the oracle).

**Real corpus before/after (45 sources):** Java text changed for **exactly 1** source
(`t_goto_spaghetti`, 39 → 51 lines); the other 44 are hash-identical. `javac` 41/45 → 41/45 (same 4 FILE
SECTION failures), braces 45/45, IRJump 7→7, `GOES_TO` 7→7, `// TODO: translate IRJump` 7→0, all
`// TODO` 118→111, backend diagnostics 571→564 (the 7 `BE005` gone; no `BE012` anywhere).

**Dataset (`mmim-gen-v18`):** 1 example changed — `t_goto_spaghetti` `cobol_to_java`, `expected_output.java`
only (`compiles` `True`→`True`, status `deterministic`, TODO 7→0). 351 examples, 226/71/54, source→split
assignment, leakage report (0 errors / 5 warnings), 157 rules, 41 compiling, 345/2/4 statuses all
unchanged. Two independent regenerations are byte-identical to each other and to the on-disk dataset
(SHA-256), except `validation_report.json`, which differs only in its embedded `path` field.

**Newly found independent gap (NOT fixed): COBOL `VALUE` clauses never become Java field initializers.**
`build_fields_from_symbols` hardcodes `initial_value=None`, so `STEP-INDEX ... VALUE 01` is `private int
stepIndex;` (Java default 0). Consequently the *generated Java of `t_goto_spaghetti`, run as-is, takes the
ELSE path* (`STEP-INDEX = 1` is false) and ends `accumulator=50` — correct jump logic applied to a wrong
initial state. This is why the tests seed initial state explicitly. It affects every program, not just GO TO.

> **Resolved in Stage 20** (`mmim-gen-v19`, docs/MMIM_VALUE_INITIALIZER_FIX.md): `VALUE` clauses are now Java
> field initializers; `t_goto_spaghetti`, run unseeded, ends `accumulator=30, stepIndex=4, retryCounter=2,
> terminalState=COMPLETED`.

**Remaining:** `GO TO … DEPENDING ON` (unimplemented; not in the corpus); PERFORM still lowers to an empty
stub call with the paragraph body inlined (so a program mixing PERFORM and GO TO is faithful for its jumps
but not for its PERFORMs); an IF whose header is untranslatable still omits its whole construct —
including any GO TO inside it — with the existing `BE007` TODO.
