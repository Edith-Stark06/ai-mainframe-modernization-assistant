# STEP 13 — IS-TRUE / IS-FALSE Condition-Operator Extraction Fix

## 1. Read before editing

- `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md` — the prior parser task:
  fixed two upstream grammar gaps so level-88 condition-name references
  reach the AST and business-rule engine, rendered as
  `(name, "IS-TRUE"|"IS-FALSE", name)` — reusing the existing
  `ConditionTerm`/`IfStatementNode` triple shape, no new AST fields.
  Explicitly left `conditions.py` untouched and named extending it as the
  natural next step.
- `docs/MMIM_V2_DATASET_AUDIT.md` — dataset state before this task: 349
  examples, 34/45 (75.6%) VALIDATION_REASONING coverage, `mmim-gen-v7`.
- `app/behavioral/extraction/conditions.py` — `parse_condition`,
  `generate_boundary_values`, the `_NUMERIC`/`_COND_RE` regexes and the
  `Comparison` dataclass.
- `app/behavioral/extraction/extractor.py` — `extract_behavioral_tests`
  (the caller that turns business rules into `BehavioralTestCase`s) and
  `_evaluate` (its own, separate numeric/string-comparison scorer).
- `app/parser/ast/data_items.py::ConditionNameNode` — confirmed
  `.values: tuple[str, ...]` (added in the prior task) is the AST's only
  record of a condition-name's declared domain; nothing in
  `conditions.py`/`extractor.py` read it before this task.
- `app/parser/syntax/procedure_parser.py` — confirmed (re-read, not
  assumed) the exact sentinel strings `_CONDITION_NAME_TRUE_OPERATOR =
  "IS-TRUE"` / `_CONDITION_NAME_FALSE_OPERATOR = "IS-FALSE"` and that
  `_parse_condition_term` always sets both `left` and `right` to the
  condition-name itself.
- `tests/behavioral/` — no existing test exercised `IS-TRUE`/`IS-FALSE`
  at all (confirmed by grep); `test_decimal_condition_extraction_fix.py`
  was the most recent precedent for this module's test conventions.
- `tests/dataset/test_mmim_v2_dataset.py` — confirmed the exact test that
  would need updating once VALIDATION_REASONING coverage changed
  (`test_level88_fix_did_not_change_validation_reasoning_coverage`, which
  asserted `t_condition_names_88` was *not* in `val_sources` — a
  then-correct pin of a boundary this task deliberately moves).

## 2. Data flow traced end to end, before any code was changed

```
COBOL source (t_condition_names_88.cbl)
  -> AST (IfStatementNode.condition_operator = "IS-TRUE" / "IS-FALSE",
          ConditionNameNode.values = ("'D'", "'W'", "'T'", "'F'"), etc.)
  -> business rule (app/modernization/business_rules/extractor.py,
                     UNMODIFIED by this task)
       rule["condition"] = "TX-VALID-KIND IS-FALSE TX-VALID-KIND"
       rule["condition"] = "(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND (TX-AMOUNT > 1000.00)"
       ... (8 rules total, all real, all already correct)
  -> extract_behavioral_tests (app/behavioral/extraction/extractor.py)
       cmp = parse_condition(str(rule["condition"]))   # <-- FAILURE POINT
  -> [nothing further reached; cmp was always None]
  -> VALIDATION_REASONING eligibility: suite.tests == [] -> skipped
```

Direct reproduction, before any code was touched:

```python
>>> rules = bundle.business_rules  # 8 real rules
>>> [parse_condition(r["condition"]) is not None for r in rules]
[False, False, False, False, False, False, False, False]
>>> extract_behavioral_tests(bundle).tests
()
```

`parse_condition` was confirmed as the **sole** rejection point:
`bundle.business_rules[i]["condition"]` already carried correct,
non-fabricated `IS-TRUE`/`IS-FALSE` text — nothing upstream needed to
change. This was verified, not assumed, by printing every one of the 8
real condition strings and confirming each is exactly the shape
`app/parser/syntax/procedure_parser.py`'s own docstring says it produces.

## 3. Root cause — precisely identified

`_COND_RE`'s operator alternation was `>=|<=|<>|=|>|<` (no
`IS-TRUE`/`IS-FALSE`), and its literal alternation was
`'[^']*'|"[^"]*"|-?\d+(?:\.\d+)?` (a quoted string or a number — never a
bare identifier). A condition-name term fails *both* checks
simultaneously: the operator position doesn't match, and even if it did,
the right-hand operand (the condition-name repeated) isn't shaped like
any accepted literal. `parse_condition` returned `None` for the whole
string, not merely with some field unset.

A second, distinct problem was traced by inspecting real corpus data
before writing any fix: of the 8 real business rules, only 2 are a
*single* condition-name term (`TX-VALID-KIND IS-FALSE TX-VALID-KIND`,
`ONLINE-CHANNEL IS-TRUE ONLINE-CHANNEL`); the other 6 are `AND`-compound
conditions (e.g. `(PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH) AND
(TX-AMOUNT > 1000.00)`). `parse_condition` has never represented compound
conditions, for *any* operator — this is a pre-existing, explicitly
documented limitation (the module's own original docstring: "Anything
else (compound AND/OR...) is deliberately left unparsed"), unrelated to
IS-TRUE/IS-FALSE. Recognizing this **before** writing code correctly
scoped the fix to the 2 single-term rules, rather than either
under-fixing (missing the operator gap) or over-fixing (attempting to
also parse compounds, which this task's stop conditions explicitly forbid
as scope creep).

A third fact, load-bearing for the implementation: a condition-name's
*declared domain* (`'D'`, `'W'`, `'T'`, `'F'` for `TX-VALID-KIND`) is
**not present in the condition string at all** — both operands are just
the condition-name, repeated. That information exists only in the DATA
DIVISION AST (`ConditionNameNode.values`, added by the prior parser
task). `parse_condition(text: str)` has no AST access by design (it is a
pure string parser, reused as-is from `app/modernization/business_rules/
extractor.py`'s output) — so boundary-value generation for a
condition-name genuinely needs data from a different layer than the
string alone provides.

## 4. The fix — narrowest additive change

### `app/behavioral/extraction/conditions.py`

A **separate** regex, `_CONDITION_NAME_RE`, tried only after `_COND_RE`
fails to match — never folded into `_COND_RE`'s own literal alternation,
so admitting a bare identifier as an operand can never widen what an
*ordinary* comparison (`=`, `>`, ...) accepts there:

```python
_CONDITION_NAME_RE = re.compile(
    r"^\s*(?P<not>NOT\s*\(\s*)?"
    r"(?P<var>[A-Z0-9][A-Z0-9-]*)\s*"
    r"(?P<op>IS-TRUE|IS-FALSE)\s*"
    r"(?P<var2>[A-Z0-9][A-Z0-9-]*)"
    r"(?(not)\s*\))\s*$",
    re.IGNORECASE,
)
```

`parse_condition` tries `_COND_RE` first (unchanged behavior for every
existing case), then `_CONDITION_NAME_RE`; if the two operands differ
(`var != var2`) the match is rejected rather than guessed at — the
parser's own representation always repeats the same name, so a string
where they differ is not a shape any real caller produces.

`Comparison` gained one derived property, `is_condition_name` (`operator
in ("IS-TRUE", "IS-FALSE")`) — no new stored field, since the existing
`operator` string already distinguishes it unambiguously.
`effective_operator`'s `NOT`-folding dict gained two entries
(`"IS-TRUE": "IS-FALSE"`, `"IS-FALSE": "IS-TRUE"`), symmetric with the
existing six relational-operator entries.

`generate_boundary_values` gained an optional `known_values: tuple[str,
...] = ()` parameter, dispatching to a new
`_generate_condition_name_boundary_values(op, known_values)` when
`cmp.is_condition_name`. Every declared value is a genuine "true" (or
"false", for `IS-FALSE`) boundary point — not just one arbitrary
representative — since the condition-name literally holds for each of
them; one deterministic non-member value (`"OTHER"`, stepping to
`"OTHER1"`, `"OTHER2"`, ... only in the vanishingly unlikely case a real
declared value collides with it) represents everything outside the
domain. **With no declared domain available (`known_values` empty), no
boundary value is invented — an empty list, the same honest "no
derivable test" outcome an unparseable condition already produces
elsewhere in this module.**

A small shared helper, `strip_string_literal`, was factored out of
`parse_condition`'s existing quote-stripping logic (byte-identical
behavior, now callable from outside the module) so a condition-name's
declared `VALUE`/`VALUES` literals (`"'D'"`, quoted, straight off the
AST) can be stripped identically to how a comparison's own literal
already was — one place, one convention, used by both `conditions.py`
itself and `extractor.py`.

### `app/behavioral/extraction/extractor.py`

A new helper, `_collect_condition_name_values(bundle.ast)`, walks the
real DATA DIVISION AST's `WORKING-STORAGE SECTION` (a flat list — this
parser never nests subordinate items, so no recursion is needed, exactly
matching `ProgramParser._collect_condition_names`'s own walk from the
prior task) and returns `{CONDITION-NAME: (declared values...)}`, quote-
stripped via the shared helper above. Called once per source at the top
of `extract_behavioral_tests`; the per-variable `known_values` tuple is
looked up and threaded into both `generate_boundary_values(cmp,
known_values)` and a matching new `known_values` parameter on
`_evaluate` (extractor.py's own, separate comparison-scoring function,
which mirrors `generate_boundary_values`'s membership test:
`(value in known_values) == (op == "IS-TRUE")`, so the two functions can
never disagree about which boundary value satisfies which rule).

### What was preserved

- **Existing comparison operators** (`=`, `!=`/`<>`, `>`, `<`, `>=`,
  `<=`): `_COND_RE` itself is byte-for-byte unchanged; every existing
  test (decimal, integer, negative, compound-AND/OR-comparison) still
  passes unmodified.
- **`_COND_RE`'s literal grammar was not widened**: a variable-vs-variable
  ordinary comparison (`TX-DEPOSIT = TX-WITHDRAWAL`) is still rejected —
  proven by a dedicated regression test — because the bare-identifier
  operand is only ever accepted by the *separate* `_CONDITION_NAME_RE`,
  gated on the `IS-TRUE`/`IS-FALSE` operator literal.
- **No AST/business-rule-layer change**: `app/modernization/business_rules/
  extractor.py` and every parser file from the prior task are untouched.
- **No fabricated evidence**: every "true" boundary value is a real
  declared `VALUE`/`VALUES` literal read from the AST; the one
  synthesized non-member value follows the exact same `"OTHER"`
  convention the module already used for ordinary string comparisons
  (not a new kind of invention); with no declared domain found, zero
  values are produced rather than a guessed one.
- **Compound `AND`/`OR` conditions remain unparseable** — for any
  operator, exactly as before; not something this task's own stop
  conditions permitted touching.
- **The unrelated `NOT =` gap, `PERFORM UNTIL` recovery gap, decimal
  accumulator arithmetic, and the strategy-analyzer rationale-text
  inconsistency**: none of these was directly responsible for the
  IS-TRUE/IS-FALSE extraction failure (confirmed by the root-cause trace
  in §2–3), so none was touched, per this task's explicit stop
  conditions.

## 5. Tests added

`tests/behavioral/test_level88_condition_operator_fix.py` — new, 24
tests:

- **Parsing**: `IS-TRUE`, `IS-FALSE`, `NOT`-wrapped folding in both
  directions, mismatched-operand rejection (not guessed), case
  insensitivity.
- **Existing-operator regression**: integer and decimal comparisons still
  parse; a variable-vs-variable ordinary comparison (`TX-DEPOSIT =
  TX-WITHDRAWAL`) still does not — the single most important regression
  guard, proving `_COND_RE`'s literal grammar was never widened; an
  unrelated compound condition (`A AND B`) still rejected; a compound
  `IS-TRUE` condition still rejected (the pre-existing, out-of-scope
  compound-condition limitation, unaffected).
- **Boundary-value generation**: `IS-TRUE`/`IS-FALSE` use the declared
  domain (both single- and multi-value condition-names — the plural
  `VALUES` form contributes one true-point per declared value, not one
  arbitrary representative); negation flips correctly; no known values
  yields no boundary values (not fabricated); a declared value that
  happens to be `"OTHER"` doesn't collide with (and silently shadow) the
  synthesized non-member sentinel.
- **Real corpus, `t_condition_names_88.cbl` (the actual file)**: the 2
  single-term rules become parseable, the 6 compound ones correctly
  remain unparseable (not a regression); `extract_behavioral_tests`
  produces real, non-zero tests with real conditions; every test with
  evidence (`expected_outputs`/`expected_state_changes`) carries valid
  source provenance tracing to the real file; the true branch
  (`ONLINE-CHANNEL IS-TRUE`) fires for all 3 declared values with the
  real `FEES-LEVIED = 0.00` action from the real source (lines 61–62);
  the false branch (`TX-VALID-KIND IS-FALSE`) fires only for the
  synthesized non-member value with the real `OUTCOME-ACTION`/
  `TX-STATUS-FLAG` actions (lines 34–36); the 4 declared `TX-VALID-KIND`
  values each correctly produce *zero* fabricated outputs (nothing
  fires); a final test confirms `suite.tests` is non-empty, matching
  exactly what `MMIMDatasetBuilder(strict_eligibility=True)` requires for
  VALIDATION_REASONING eligibility.

`tests/parser/test_level88_condition_reference_fix.py` — one test
(`test_real_corpus_behavioral_extraction_still_zero_conditions_py_untouched`)
pinned a boundary this task deliberately moves; updated (not deleted) to
document the parser/AST-layer facts (8 rules, all IS-TRUE/IS-FALSE
shaped, 2 single-term) that were true when it was written and remain
true, without asserting on `conditions.py`'s now-changed behavior — that
assertion moved to the new test file above, where it belongs.

## 6. Real-corpus validation

Methodology: the same precise Edit-based revert-and-restore technique
used in every prior cycle. `conditions.py` had no uncommitted prior-cycle
content (safely restorable via a full-file `Write` back to its exact
STEP-12-end content, verified against this conversation's own earlier
`Read`); `extractor.py` carried the STEP-10 decimal-condition fix, so its
new hunks were reverted by hand via the exact `old_string`/`new_string`
pairs in reverse. The revert was verified against two independent known
values before trusting it — `parse_condition("RATE = 0.00")` still
worked (STEP-10's fix undisturbed) and `parse_condition("TX-VALID-KIND
IS-FALSE TX-VALID-KIND")` returned `None` again (this task's fix
correctly absent) — before the "before" corpus scan ran, and the fix was
restored and re-verified (`is_condition_name` correct, real values
parse) before the "after" scan ran.

A full 45-source corpus-wide scan (behavioral test count per source)
confirmed **exactly one source changed**:

| Source | Before | After |
|---|---:|---:|
| `t_condition_names_88` | 0 | 9 |
| (all other 44 sources) | — | byte-identical |

Spot-verified (not merely counted) the 9 tests: 4 carry real evidence
(`ONLINE-CHANNEL` = `WEB`/`MOB`/`API`, each with expected output
`FEES-LEVIED = "0.00"`; `TX-VALID-KIND` = `OTHER`, with expected outputs
`OUTCOME-ACTION = "REJECT-BAD-KIND"` and `TX-STATUS-FLAG = "R"`), every
one with `source_refs` tracing to the real file and real line numbers
(61–62 and 34–36 respectively, matching the real
`IF ONLINE-CHANNEL MOVE 0.00 TO FEES-LEVIED END-IF` and
`IF NOT TX-VALID-KIND MOVE 'REJECT-BAD-KIND' TO OUTCOME-ACTION MOVE 'R'
TO TX-STATUS-FLAG` in `data/sources/phase6-v2/condition_names_88.cbl`);
the remaining 5 (the 4 `TX-VALID-KIND` declared values plus `ONLINE-
CHANNEL = OTHER`) correctly carry zero outputs — the condition does not
hold for them, so nothing fires, and nothing is fabricated to claim
otherwise.

## 7. MMIM dataset regeneration & versioning

`generator_version` incremented deliberately: `mmim-gen-v7` →
`mmim-gen-v8` (`app/dataset/version.py::MMIM_GENERATOR_VERSION_V8`),
documented as touching VALIDATION_REASONING alone (this cycle's fix lives
entirely in `app/behavioral/extraction/`, never touched by
BUSINESS_RULE_EXTRACTION/DEPENDENCY_REASONING/RISK_CLASSIFICATION/
MODERNIZATION_STRATEGY/TRANSFORMATION_PLANNING/COBOL_TO_JAVA — confirmed
directly: `t_condition_names_88`'s `rule_count` is identical, 8, before
and after). `dataset_version` stays `"mmim-v2"` (same 45-source corpus,
same task taxonomy — no reason to change it).

| Metric | mmim-gen-v7 | mmim-gen-v8 (this fix) |
|---|---:|---:|
| Total examples | 349 | 350 |
| Sources | 45/45 | 45/45 |
| VALIDATION_REASONING coverage | 34/45 (75.6%) | 35/45 (77.8%) |
| `t_condition_names_88` VALIDATION_REASONING tests | skipped | 9 |
| `t_condition_names_88` business rules | 8 | 8 (unchanged) |
| Train / Validation / Test | 226 / 69 / 54 | 226 / 70 / 54 |
| Benchmark leakage | 0 | 0 |
| Split leakage errors | 0 | 0 |
| Split leakage warnings | 5 (pre-existing, unrelated) | 5 (unchanged) |

Source-grouped split assignment preserved: `t_condition_names_88` was
already assigned to `validation` (confirmed directly against the prior
`mmim-gen-v7` split, unchanged since `mmim-gen-v2`) and remains there —
the `validation +1` delta is exactly and only its one new
VALIDATION_REASONING example; `train`/`test` example counts are
unchanged (226/54); no source moved.

`data/dataset/mmim-v2/**` regenerated in place via
`build_mmim_dataset(..., generator_version=MMIM_GENERATOR_VERSION_V8,
strict_eligibility=True)` and `build_instruction_dataset`. `benchmark-v1`
and `data/dataset/mmim-v1/**` untouched (not read or written by this
task; confirmed via `git status`).

## 8. Tests run

```
python -m pytest tests/behavioral/test_level88_condition_operator_fix.py -q   # 24 passed
python -m pytest tests/behavioral/ -q                                         # 106 passed
python -m pytest tests/parser/test_level88_condition_reference_fix.py -q      # 19 passed
python -m pytest tests/parser/ -q            # 956 passed, 9 pre-existing unrelated failures
                                              # (identical set to every prior cycle's baseline)
python -m pytest tests/dataset/test_mmim_v2_dataset.py tests/dataset/test_instruction_adapter_v2.py -q
                                                                                # 51 passed
python -m pytest tests/dataset/ tests/behavioral/ tests/modernization/ -q    # 441 passed
python -m pytest tests/ -q   # full-tree baseline: 3791 passed, 12 pre-existing unrelated
                              # failures (tests/ir/test_ir_control_flow.py x3, tests/parser/
                              # test_lexer.py x2, test_lexer_regression.py x1,
                              # test_procedure_parser.py "missing period" x4,
                              # test_token_types.py x2 -- identical set documented in every
                              # prior cycle's audit; none touch IS-TRUE/IS-FALSE extraction
.venv\Scripts\black.exe --check .   # 1130 files clean
.venv\Scripts\ruff.exe check .      # all checks passed
.venv\Scripts\mypy.exe app          # no issues found in 354 source files
```

## 9. Exact files changed

- `app/behavioral/extraction/conditions.py` — `_CONDITION_NAME_RE`,
  `Comparison.is_condition_name`, `effective_operator`'s two new entries,
  `strip_string_literal` (factored out, exported),
  `generate_boundary_values`'s new `known_values` parameter and
  `_generate_condition_name_boundary_values` helper.
- `app/behavioral/extraction/extractor.py` — `_collect_condition_name_values`
  helper; `extract_behavioral_tests` builds and threads `known_values`;
  `_evaluate`'s new `known_values` parameter and condition-name branch.
- `app/dataset/version.py` — `MMIM_GENERATOR_VERSION_V8` added.
- `tests/behavioral/test_level88_condition_operator_fix.py` — new, 24
  tests.
- `tests/parser/test_level88_condition_reference_fix.py` — one test
  updated to stop asserting on `conditions.py`'s now-changed behavior.
- `tests/dataset/test_mmim_v2_dataset.py` — version bump (V7→V8), 35/45
  coverage, new §3g regression tests (4 tests), removed the now-obsolete
  "did not change coverage" pin from §3f.
- `tests/dataset/test_instruction_adapter_v2.py` — version bump (V7→V8),
  example count 349→350.
- `docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md` — this document.
- `docs/MMIM_V2_DATASET_AUDIT.md` — updated separately for the v8
  regeneration.
- `data/dataset/mmim-v2/**` — regenerated in place (`manifest.json`,
  `split_manifest.json`, `leakage_report.json`, `validation_report.json`,
  `all.jsonl`/`train.jsonl`/`validation.jsonl`/`test.jsonl`,
  `instruction/**`).

## 10. New independent gaps (not fixed, out of scope)

None newly discovered by this task. The gaps already reported by the
prior cycle remain unfixed and unaffected:

- Compound `AND`/`OR` conditions remain unparseable by `parse_condition`
  for any operator (pre-existing, unrelated to IS-TRUE/IS-FALSE) — this
  is why 6 of `t_condition_names_88`'s 8 business rules still do not
  produce behavioral tests; a genuine further limitation, not a defect
  introduced or hidden by this fix.
- `app/modernization/strategy/analyzer.py::_fallback`'s rationale-text
  inconsistency (§10 of the prior fix doc) — confirmed not responsible
  for the IS-TRUE/IS-FALSE extraction failure, so not touched here.
- The unrelated `IF <var> NOT = <literal>` gap, the `PERFORM UNTIL`
  unsupported-statement recovery gap, and decimal accumulator arithmetic
  — all confirmed unaffected, none touched.
