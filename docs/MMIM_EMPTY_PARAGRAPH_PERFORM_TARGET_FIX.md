# CFG/flow generator: existing-but-statement-empty `PERFORM`/`GO TO` target defect

Branch `feat/mmim-read-at-end-fix` (continued — no new branch requested for this stage). Follows
`docs/MMIM_READ_AT_END_PARSING_FIX.md` §6, which reported this as pre-existing and out of scope.
`generator_version` `mmim-gen-v14` -> `mmim-gen-v15`; `dataset_version` stays `mmim-v2`.

## 1. Path traced before any code changed

`app/modernization/flow/generator.py::FlowGenerationVisitor` discovers a paragraph's existence and
CFG entry node **purely from IR instructions**:

* `_known_paragraphs` is built from `{i.paragraph for i in block.instructions}` (`visit_basic_block`).
* `_paragraph_entry` is populated only inside `_new_node`, itself only called when an instruction
  produces a node.
* `_maybe_enter_paragraph` fires only per-instruction — never for a paragraph with zero instructions.
* `PERFORM`/`GO TO` edges are queued as `_DeferredEdge`s and resolved in `finish()`'s linear
  post-pass, once every paragraph's entry (if any) is known:

  ```python
  target_entry = self._paragraph_entry.get(deferred.target_paragraph)
  if target_entry is None:
      target_entry = f"ext_{deferred.target_paragraph}"   # EXTERNAL, unconditionally
      ...
  ```

A paragraph whose only statement is one this parser cannot represent (`READ`, `OPEN`, `CLOSE`,
`WRITE`, ...) produces **zero** IR instructions and is therefore entirely invisible to the visitor —
indistinguishable from a paragraph that does not exist in the source at all. `finish()`'s lookup then
falls back to the generic `ext_<name>` `EXTERNAL`-node path for both cases, and
`RiskAnalyzer._detect_unresolved_perform_targets` flags any `PERFORM` reaching an `EXTERNAL` node as
an `UNRESOLVED_PERFORM_TARGET`, whether the target is genuinely external or merely genuinely empty.

Reproduced directly on `t_batch_acct_update` (`data/sources/phase6-v2/batch_acct_update.cbl`) before
any code change, using `RiskAnalyzer().analyze(result, flow)` (the `flow` argument is required — an
earlier repro attempt of mine omitted it and silently produced "no finding" on both before and after,
which I caught and corrected by noticing the node dump still contained `ext_1000-OPEN-FILES`/
`ext_2000-READ-RECORD` `EXTERNAL` nodes, inconsistent with "no finding"):

```
paragraphs: [0000-PROCESS-ACCOUNTS, 1000-OPEN-FILES, 2000-READ-RECORD,
             3000-PROCESS-LOOP, 3100-APPLY-ACCOUNT-RULES, 4000-CLOSE-FILES]
PERFORM -> 1000-OPEN-FILES   exists in AST : True   -- flagged EXTERNAL anyway
PERFORM -> 2000-READ-RECORD  exists in AST : True   -- flagged EXTERNAL anyway (x2 call sites)
UNRESOLVED_PERFORM_TARGET occurrence_count: 3
```

`1000-OPEN-FILES` was already empty before the READ fix (its own `IF WS-FILE-STATUS NOT = '00' ...`
fails to parse, the separate, already-documented `IF <var> NOT = <literal>` negated-equality gap —
unrelated to this task). `2000-READ-RECORD` became correctly empty only after the completed
`docs/MMIM_READ_AT_END_PARSING_FIX.md` fix (a `READ`, like an `OPEN`, is unsupported and has zero
representable statements — that is the honest, intended state, not a new defect). Confirmed via the
isolated pre-fix tree (`PYTHONPATH`, subprocess) that the pre-READ-fix count was 1
(`1000-OPEN-FILES` only); after the READ fix and before this task's fix, 3 (both paragraphs) — the
exact `1 -> 3` regression the task brief describes.

Also traced and confirmed **not the actual resolution mechanism**: `visit_call`'s `is_perform`
classification checks `node.comment == "PERFORM"`, which `IRBuilder.build_perform_statement` always
sets on real IR — so `_known_paragraphs`'s use as a fallback in that check is irrelevant to the real
bug. The true fix point is solely `finish()`'s `_paragraph_entry.get(...)` lookup.

## 2. `PERFORM THRU` and `GO TO` — checked explicitly, not assumed

* **`PERFORM ... THRU ...`** is a separate, pre-existing, out-of-scope parser gap, confirmed by direct
  reproduction with a synthetic source: `_parse_perform_statement`'s simple-`PERFORM` branch reads only
  **one** identifier as `target`; `THRU <paragraph>` is never consumed, producing a
  `SYN001 unexpected token 'THRU'` recovery diagnostic (subsequent statements still parse correctly).
  **Correction (task #stage16):** the claim below this line originally stated `data/sources/phase6-v2`
  has no real `THRU` usage — that was wrong; a corpus-wide search was not actually run for this task,
  only a synthetic repro. `t_fallthrough_flow` does contain one real `PERFORM ... THRU ...`
  (`docs/MMIM_PERFORM_THRU_FIX.md` §5), which is the source of the risk-count discrepancy this fix's
  own real-corpus scan (§5 above) would have shown as unaffected by *this* task's change either way —
  it is orthogonal to and unaffected by that gap — only the single captured target is ever seen by the
  resolution logic — and
  is tested explicitly (§3, category E) rather than assumed to be fine.
* **`GO TO`** is, like `READ`, in `_UNSUPPORTED_STATEMENT_LEXEMES` at the parser level — confirmed
  empirically that a program containing only `GO TO X.` produces **zero** AST statements. The
  `IRJump`/`visit_jump`/`GOES_TO`-edge machinery in the flow generator is present and correctly
  wired, but currently **unreachable** via the real pipeline — a separate, pre-existing,
  out-of-scope gap with no prior test coverage anywhere in `test_control_flow_graph.py`. Not fixed;
  the `GO TO` regression test (§3, category B) drives `FlowGenerationVisitor` directly with hand-built
  IR (`IRJump`/`IRBasicBlock`/`IRFunction`/`IRModule`/`IRProgram`) to prove the *visitor's* `GOES_TO`
  resolution is correct independent of this unrelated parser gap.

## 3. The fix (`app/modernization/flow/generator.py` only)

Threaded the genuinely-real AST paragraph-name set into the visitor so `finish()` can distinguish "no
IR-derived entry, but the paragraph genuinely exists" from "no IR-derived entry because the paragraph
does not exist":

* `generate_flow(analysis)` now computes `real_paragraphs = {p.name for p in
  analysis.ast.procedure_division.paragraphs}` once (empty set if no AST/procedure division) and
  passes it into `FlowGenerationVisitor.__init__` as a new `real_paragraphs: Optional[Set[str]] =
  None` parameter, stored as `self._real_paragraphs`.
* `finish()`'s deferred-edge resolution becomes a three-way branch:
  * **`target_entry` found** (paragraph produced at least one IR node) — unchanged, resolved as
    before.
  * **Not found, but `target_paragraph in self._real_paragraphs`** — the paragraph genuinely exists;
    create (and cache in `_paragraph_entry`, so every call site targeting the same empty paragraph
    shares one node) a single `NodeType.PROCESS` anchor node, id `empty_<module>_<paragraph>`, name
    `"<paragraph> (no representable statements)"`. This is a structural CFG placeholder marking where
    control enters and immediately leaves the paragraph — it asserts nothing about what COBOL
    operation happened, so no executable statement is fabricated, and it is a different `NodeType`
    (`PROCESS`, not `EXTERNAL`) so `RiskAnalyzer._detect_unresolved_perform_targets` no longer flags
    it.
  * **Not found, and not in `real_paragraphs`** — unchanged: the original `ext_<name>` `EXTERNAL`
    fallback, exactly as before.

No other logic changed. `_skip_to_matching_close_word`, `_SCOPE_OPENING_LEXEMES`,
`_SCOPE_CLOSE_WORDS`, `_known_paragraphs`, `_maybe_enter_paragraph`, edge-dedup
(`_seen_logical_edges`), and every non-`PERFORM`/`GO TO` node/edge construction path are untouched.
An unrelated pre-existing accumulated change already on this branch (`visit_if` using
`node.condition_text()` for compound-condition display, from the earlier `extra_conditions`
downstream fix) is visible in the diff but was not touched by this task.

**Design note:** an initial idea to key existence off `_known_paragraphs` instead of a fresh
AST-derived set was rejected — `_known_paragraphs` is itself built from IR instructions, so it has
the identical blind spot for a zero-instruction paragraph; only the AST's own paragraph list is a
source of truth for existence independent of executable content.

## 4. Tests

`tests/modernization/flow/test_empty_paragraph_perform_target_fix.py` — 16 new tests, following
`tests/modernization/flow/test_generator.py` / `tests/modernization/flow/test_control_flow_graph.py`
conventions (`_flow_for(source)`: `CobolLexer` -> `ProgramParser` -> `SemanticAnalyzer` -> `IRBuilder`
-> `AnalysisResult` -> `generate_flow`), covering every category the task specified at minimum:

* **A** — `test_perform_of_a_nonempty_paragraph_is_unaffected`: existing non-empty target remains
  resolved.
* **B** — `TestExistingEmptyTarget` (5 tests): a `READ`-only and an `OPEN`-only paragraph each
  resolve to a `NodeType.PROCESS` node (not `ext_...`); no `UNRESOLVED_PERFORM_TARGET` risk is
  raised; two `PERFORM`s of the same empty paragraph from different call sites share one cached node
  id; `GO TO` an empty paragraph also resolves (hand-built IR, per §2 above).
* **C** — `test_perform_target_not_defined_is_still_external`,
  `test_missing_target_still_raises_unresolved_perform_target_risk`,
  `test_existing_nonempty_and_missing_targets_in_the_same_program`: a genuinely missing target
  remains `EXTERNAL` and still raises the risk, including alongside a resolved empty target in the
  same program.
* **D** — 4 tests against the real `t_batch_acct_update` source (module-scoped fixture): both empty
  targets resolve and share cached nodes across their multiple call sites; no
  `UNRESOLVED_PERFORM_TARGET` risk; non-empty `PERFORM` targets in the same program still resolve
  normally; paragraph/node counts are stable (6 paragraphs, same node/edge counts as before, just a
  node-type reclassification).
* **E** — `test_perform_thru_is_not_specially_parsed_but_the_first_target_still_resolves`: explicitly
  documents and tests the pre-existing `THRU` parsing gap (§2) rather than assuming it does not
  interact with this fix.
* Plus two "existing behaviour re-proven unaffected" tests: a forward-referenced (declared after its
  `PERFORM` site) non-empty target still resolves; a `PERFORM` nested inside a paragraph that itself
  targets an empty paragraph resolves both independently.

Two bugs were found and fixed in the tests themselves via an actual run, not just self-review: (1) the
`GO TO` test originally drove the real parser and asserted a `GO TO` node would exist, but the real
pipeline produces zero AST statements for `GO TO` (§2) — rewritten to hand-build IR directly; (2) the
real-corpus "both empty targets resolve" test used a single-match helper against
`2000-READ-RECORD`, which is actually `PERFORM`ed from **two** distinct call sites
(`0000-PROCESS-ACCOUNTS` and `3000-PROCESS-LOOP`) — added a `_performs_targets` (plural) helper and
asserted all matching call sites resolve to the same cached node id.

**Isolation check:** the 16 new tests were copied into a byte-copy of the pre-fix `app/` tree
(scratchpad `baseline6`, snapshotted before this task's code change) and run as a subprocess with
`cwd` set to that isolated tree (confirmed via `app.__file__` resolving to the isolated copy, not the
repo) — **10 of 16 fail** on the isolated pre-fix tree (the category-B, category-D, category-E, and
"nested empty target" tests); the other 6 are the "existing behaviour unaffected" guards (category A,
C, and the forward-reference test), which correctly pass unchanged on both trees. All 16 pass on the
current (fixed) tree.

## 5. Real-corpus before/after (45 sources)

`snapshot6.py`: for every corpus source, `generate_flow(result)` + `RiskAnalyzer().analyze(result,
flow)`, recording the `UNRESOLVED_PERFORM_TARGET` occurrence count, the sorted `ext_`/`empty_` node
name lists, and node/edge counts and signatures. "Before" = isolated pre-fix tree (subprocess,
`PYTHONPATH`); "after" = the repository; the comparison asserts `app.__file__` and the generator's
SHA-256 differ (`11c20c36ed79` vs `a9e825145e98`) to prove genuine isolation, not an in-process
reload.

| Measure | Result |
|---|---|
| Sources whose CFG/risk output changed | **12 / 45** |
| Node count / edge count, per changed source | **identical** before/after (a pure one-for-one node-type reclassification, not a structural change) |
| Genuinely-external real `CALL` targets (`t_billing_engine`: `DISCENG1`, `TAXENG01`; `t_transitive_fx`: `FEECALC`, `FXRATES`) | still `EXTERNAL` after the fix — proves the fix does not over-resolve genuine unresolved references |

Per-source `UNRESOLVED_PERFORM_TARGET` occurrence count, before -> after:

| Source | Before | After |
|---|---:|---:|
| `t_account_eligibility` | 1 | 0 |
| `t_batch_acct_update` | 3 | 0 |
| `t_billing_engine` | 1 | 0 |
| `t_daily_trans_report` | 1 | 0 |
| `t_insurance_claim` | 1 | 0 |
| `t_inventory_extract` | 1 | 0 |
| `t_inventory_reorder` | 3 | 0 |
| `t_order_hierarchy` | 1 | 0 |
| `t_packed_decimal` | 1 | 0 |
| `t_payroll_file_post` | 1 | 0 |
| `t_pricing_tier` | 1 | 0 |
| `t_transitive_fx` | 1 | 0 |

All other 33 sources: unchanged (0 -> 0, or no `UNRESOLVED_PERFORM_TARGET` risk at all).

## 6. Dataset regeneration (`mmim-gen-v15`)

`app/dataset/version.py::MMIM_GENERATOR_VERSION_V15`. CFG/risk-layer change: touches every task whose
`expected_output` (or top-level `analysis.cfg`, a sibling field of `expected_output`) derives from the
CFG or the `UNRESOLVED_PERFORM_TARGET` risk finding, for the 12 affected sources only.

| | mmim-gen-v14 | mmim-gen-v15 |
|---|---:|---:|
| Examples | 351 | 351 |
| Sources | 45/45 | 45/45 |
| Train / validation / test | 226 / 71 / 54 | 226 / 71 / 54 |
| Examples changed | — | **52**, across `dependency_reasoning` (12), `modernization_strategy` (12), `program_understanding` (12), `risk_classification` (12), `transformation_planning` (4 — only the sources whose strategy-evidence-derived architecture text changed) |
| `business_rule_extraction` / `validation_reasoning` / `cobol_to_java` | unchanged (0 sources) | unchanged |
| Business-rule counts | 157 total | 157 total, unchanged; 0 rule conditions changed |
| VALIDATION_REASONING coverage | 36/45 sources | unchanged |
| Ground truth (deterministic / executable_verified / reference) | 345 / 2 / 4 | unchanged |
| Source -> split assignment | — | identical |
| Benchmark leakage | clean, 0 overlap | clean, 0 overlap |
| Split leakage errors / warnings | 0 / 5 | 0 / 5 |
| Instruction-adapter split counts / per-task shape / max tokens | — | identical (15,010 max) |

Why `dependency_reasoning`/`program_understanding` are affected even though their `expected_output`
top-level keys (`['coupling', 'dependencies', ...]` / `['control_flow', 'divisions', ...]`) do not
themselves contain raw node ids: the raw CFG (with `empty_`/`ext_` node ids) lives in the
`DatasetExample`'s **top-level `analysis.cfg` field**, a sibling of `expected_output`
(`MMIMDatasetBuilder._analysis_block` attaches `cfg` for `PROGRAM_UNDERSTANDING`,
`DEPENDENCY_REASONING`, and `RISK_CLASSIFICATION` only — confirmed by reading the actual
`_analysis_block(bundle, ...)` call sites; `program_understanding`'s own `expected_output` embeds only
`cfg_nodes`/`cfg_edges` *counts*, which the fix leaves unchanged since node/edge counts are stable).
`modernization_strategy`'s `expected_output` is affected through its risk-derived evidence text (`"N
unresolved PERFORM target(s)"`) dropping to 0 for these 12 sources; `transformation_planning` only
where the architecture builder's derived content changed as a result.

Two independent full regenerations are byte-identical: `all.jsonl`, `train.jsonl`, `validation.jsonl`,
`test.jsonl`, `manifest.json`, `split_manifest.json`, `leakage_report.json`, and every file under
`instruction/` (verified by SHA-256 and `diff -rq`). `benchmark-v1` and `mmim-v1` (144 examples,
`mmim-gen-v1`, `dataset_version=mmim-v1`) are untouched — untracked by git, and their manifests were
not regenerated by this task.

## 7. Exact files changed (this task)

* `app/modernization/flow/generator.py` (`FlowGenerationVisitor.__init__`'s new `real_paragraphs`
  parameter/`self._real_paragraphs`; `finish()`'s three-way deferred-edge resolution;
  `generate_flow`'s `real_paragraphs` computation)
* `app/dataset/version.py` (`MMIM_GENERATOR_VERSION_V15`)
* `tests/modernization/flow/test_empty_paragraph_perform_target_fix.py` (new, 16 tests)
* `tests/dataset/test_mmim_v2_dataset.py` (V15 pins + §3n, 5 new tests)
* `tests/dataset/test_instruction_adapter_v2.py` (version bump)
* `docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md` (this file), `docs/MMIM_V2_DATASET_AUDIT.md`,
  `docs/MMIM_READ_AT_END_PARSING_FIX.md` (resolution note on its §6)
* `data/dataset/mmim-v2/**` (regenerated)

Untouched, verified against the pre-task snapshot: `_skip_to_matching_close_word` and
`_SCOPE_OPENING_LEXEMES`/`_SCOPE_CLOSE_WORDS` (EVALUATE's scope-close mechanism), `READ`/`GO TO`
parsing (`app/parser/syntax/procedure_parser.py`), behavioral extraction (`app/behavioral/`),
business-rule extraction (`app/modernization/business_rules/`), Java emission logic
(`app/backend/java/`), `RiskAnalyzer`'s detection logic itself (only its CFG *input* changed, not its
code), `benchmark-v1`, `mmim-v1`.

## 8. New independent gaps discovered — NOT fixed

None new. §2 above re-confirms (rather than re-discovers) the two gaps already flagged as
out-of-scope in the task brief itself (`PERFORM THRU`'s single-target parsing limit, `GO TO`'s
membership in `_UNSUPPORTED_STATEMENT_LEXEMES`) with direct reproduction, since the task explicitly
required testing rather than assuming they were unaffected by this fix. Both are confirmed orthogonal
to this fix and were not touched.

> **`PERFORM THRU` resolved** — see `docs/MMIM_PERFORM_THRU_FIX.md` (`mmim-gen-v16`): `PERFORM A THRU
> C` now parses both endpoints and the CFG resolves the complete ordered paragraph range.
>
> **`GO TO` resolved** — see `docs/MMIM_GO_TO_FIX.md` (`mmim-gen-v17`): real `GO TO paragraph-name`
> now parses and reaches the `IRJump`/`GOES_TO` CFG machinery this doc's §2 confirmed was already
> correctly wired but unreachable.
