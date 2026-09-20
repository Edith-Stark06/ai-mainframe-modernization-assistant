# MMIM Validation-Reasoning Extractor Audit & Upgrade

Investigates why `VALIDATION_REASONING` covered only 22/45 (48.9%) sources in the first
`mmim-v2` build, classifies all 23 skipped sources by root cause, implements the smallest
correct fix for the loop/accumulator class, and reports the measured before/after result.

`EXTRACTION_VERSION` bumped `p10-extract-v1` → `p10-extract-v2`
(`app/behavioral/version.py`). `MMIM_GENERATOR_VERSION_V3 = "mmim-gen-v3"` added
(`app/dataset/version.py`) — `dataset_version` stays `mmim-v2` (same corpus, same task
contract); only the deterministic pipeline that produces `VALIDATION_REASONING` ground truth
changed, so `generator_version` bumps instead. See "Versioning decision" below.

---

## 1. How the existing extractor works (read before touching anything)

`app/behavioral/extraction/extractor.py::extract_behavioral_tests` (#129, untouched by this
change) derives every test **exclusively from `bundle.business_rules`** — the deterministic
business-rule engine's output, not the IR or CFG directly. For each rule it calls
`app.behavioral.extraction.conditions.parse_condition(rule["condition"])`, a regex that matches
**only** `[NOT] <identifier> <op> <literal>` — a single comparison against a literal. Rules
sharing a `(paragraph, variable)` pair are grouped (the common `IF/ELSE` shape), boundary values
are generated around the literal, and each boundary is re-evaluated to produce a test asserting
whichever rule fires.

This means: **no `PERFORM UNTIL` loop, and no comparison against another variable, was ever
capable of producing a test** — not because of a bug, but because the original design's scope
was single-comparison IF/ELSE only. `CFG generation` (`app/modernization/flow/generator.py`) and
`IR generation` (`app/ir/builder.py`) were not consulted by the extractor at all before this
change; both already contain everything needed for loops (`IRPerformUntil`/`IREndPerform`,
flat per-paragraph instruction streams with `left`/`right`/`result` operands) — it was simply
never read.

## 2. Classification of the 23 skipped sources

Every classification below is backed by actually running `build_analysis_bundle` +
`extract_behavioral_tests` (pre-upgrade) over each source and inspecting `bundle.ir`,
`bundle.ast`, `bundle.business_rules`, and `bundle.syntax_diagnostics` directly — none of this
is inferred from source code alone.

| # | Category | Source IDs | Count |
|---|---|---|---:|
| 1 | Loop/accumulator limitation | `t_interest_accrue`, `t_loan_balance` | 2 |
| 2 | Missing branch partition (variable-vs-variable comparison) | `t_inventory_reorder` | 1 |
| 3 | Missing arithmetic reasoning (straight-line, non-loop) | `t_temp_convert` | 1 |
| 4 | Parser limitation (decimal literal + compound AND/OR conditions) | `t_account_eligibility`, `t_condition_names_88`, `t_credit_approval`, `t_tax_withhold`, `t_pricing_tier`, `t_payroll_deduct`, `t_shared_state_hazard`, `t_billing_engine`, `t_transitive_fx` | 9 |
| 5 | Unsupported syntax (already-documented SYN100/SYN101/SYN200: FILE I/O, GO TO, OCCURS) | `t_batch_acct_update`, `t_daily_trans_report`, `t_payroll_file_post`, `t_order_hierarchy`, `t_table_indexed`, `t_goto_spaghetti`, `t_inventory_extract` | 7 |
| 6 | Genuinely no derivable behavioral test | `fx_perform_until`, `fx_simple_proc`, `t_dead_code_audit` | 3 |
| 7 | Other | — | 0 |
| | **Total** | | **23** |

### Category 1 — loop/accumulator (fixed by this change)

`t_interest_accrue` (`PERFORM UNTIL WS-DAY >= 30 { ADD 3 TO WS-INTEREST; ADD 1 TO WS-DAY }`) and
`t_loan_balance` (`PERFORM UNTIL WS-BALANCE = 0 { IF ... MOVE/SUBTRACT ...; ADD 1 TO WS-MONTHS }`)
both parse with **zero** diagnostics and have a pure-integer, single-level `PERFORM UNTIL` loop.
Nothing about them is a parser limitation — the extractor simply never looked at loops.

### Category 2 — missing branch partition (documented, not fixed here)

`t_inventory_reorder`'s one real business rule is `CURRENT-STOCK-QTY <= REORDER-POINT-QTY` —
both sides are data names, not a literal. `parse_condition`'s regex requires a literal on the
right-hand side, so this rule (though present in `bundle.business_rules`) is silently excluded
from the "parsed" list and never reaches boundary-value generation. Extending `parse_condition`
/ the boundary generator to resolve a variable-vs-variable RHS against its own statically known
initial value is a well-scoped, low-risk follow-up — but it is not a loop/accumulator pattern,
so it is **out of scope for the priorities (A–D) this task specified** and is left for a future
pass rather than expanding scope here.

### Category 3 — missing arithmetic reasoning (documented, not fixed here)

`t_temp_convert` is pure straight-line arithmetic with no `IF` and no loop
(`MOVE WS-CELSIUS TO WS-FAHRENHEIT; MULTIPLY 9 BY WS-FAHRENHEIT; DIVIDE 5 INTO WS-FAHRENHEIT;
ADD 32 TO WS-FAHRENHEIT`) — fully derivable in principle (25°C → 77°F) but not via a loop
boundary mechanism, since there is no loop or condition to partition around. Explicitly out of
scope: the task's priorities (A/B/C) are all loop-shaped.

### Category 4 — parser limitation (a real bug found; explicitly NOT fixed here)

This was the biggest, and most surprising, finding. Isolated with minimal repro cases (see
below): **any numeric literal containing a decimal point used inside the PROCEDURE DIVISION
(an `IF` condition, a `MOVE`, a `COMPUTE` expression — not just a `DATA DIVISION VALUE` clause,
which is the only place the original corpus-expansion report documented this bug)** causes the
lexer to split the literal at the `.` and desynchronize the token stream from that point on. Two
further, independent gaps compound it:

* **`COMPUTE` is entirely unsupported** (`SYN100`), and
* **compound `IF ... AND ...` / `IF ... OR ...` conditions are not parsed** — even a plain
  `IF WS-A = 'X' AND WS-B = 5` fails with `SYN005 expected statement in IF block`, and `NOT =`
  written as two tokens (`IF WS-A NOT = 'X'`, as opposed to `<>`) fails with
  `SYN005 expected comparison operator in IF condition`.

The parser's error recovery for these three cases does not "skip the bad statement and continue"
(the way `SYN100`/`SYN101` for `OPEN`/`FILE SECTION` cleanly do) — it drops the **entire
remaining paragraph body** silently, often with **zero diagnostics recorded at all** (verified:
`t_account_eligibility`, `t_condition_names_88`, `t_credit_approval`, `t_tax_withhold`,
`t_pricing_tier`, `t_payroll_deduct` all show every non-entry paragraph at exactly **0
statements** in the AST, and 5 of those 6 have `unsupported_codes: []` — no diagnostic hints at
the cause). Minimal reproductions (not shipped as source files, run directly against
`build_analysis_bundle`):

```
IF WS-A NOT = 'CITIZEN'                    -> 0 statements, SYN005 "expected comparison operator in IF condition"
IF WS-A = 'CITIZEN' AND WS-C = 5           -> 0 statements, SYN005 "expected statement in IF block"
IF WS-A <= 11000.00                        -> 0 statements, stray tokens '00'/'10' from the split literal
COMPUTE WS-C = WS-A - WS-B                 -> 0 statements, SYN100 "unsupported statement 'COMPUTE'"
```

Per this task's explicit instruction — **"Do not fix unrelated parser gaps... if parser changes
are required, stop and report them separately rather than expanding scope"** — this is reported
here and left unfixed. It is a lexer/parser change (token boundary rules, `IF` grammar,
`COMPUTE` support, and paragraph-body error recovery), not a behavioral-extractor change, and
touching it would be a materially larger and riskier change than the loop/accumulator work this
task asked for.

### Category 5 — unsupported syntax (already documented, unaffected by this change)

`t_batch_acct_update`, `t_daily_trans_report`, `t_payroll_file_post` (`FILE SECTION` /
`OPEN`/`READ`/`CLOSE`, `SYN100`/`SYN101`), `t_order_hierarchy`, `t_table_indexed` (`OCCURS`,
`SYN200`), `t_goto_spaghetti` (`GO TO`, `SYN100`) — all previously documented in
`docs/MMIM_CORPUS_EXPANSION.md` §D. `t_inventory_extract` additionally has one business rule
with a variable-vs-variable condition (category 2), but its dominant blocker is the
unsupported file-I/O loop that drives it (`PERFORM UNTIL ... READ ... AT END` is not modeled at
all — `SYN001 unexpected token 'UNTIL'`), so fixing the comparison alone would not help.

### Category 6 — genuinely no derivable behavioral test

`fx_perform_until` is DISPLAY-only despite its name (no actual loop in the source).
`fx_simple_proc` performs one unconditional `ADD 1 TO WS-COUNT` with no loop and no condition.
`t_dead_code_audit`'s *reachable* code (`1000-ACTIVE-ENTRY` → `2000-VALID-ROUTINE`) is a single
unconditional `ADD`; its only conditional-shaped content lives in paragraphs
`9000-ORPHAN-OBSOLETE-BLOCK` / `9100-ABANDONED-ERROR-HANDLER`, which are — **by design**, this
being the anti-pattern the source exists to test — never `PERFORM`ed. There is honestly nothing
here for a behavioral test to assert.

---

## 3. Implementation — smallest correct fix

New module: `app/behavioral/extraction/loops.py` (`extract_loop_tests`), wired additively into
`extract_behavioral_tests` (one `tests.extend(loop_tests)` call; nothing else in the #129
extractor was touched). New model fields (both optional, default-preserving, backward
compatible): `BehavioralTestCase.test_type` (`"boundary_partition"` | `"loop_accumulator"`),
`BehavioralTestCase.iteration_count`, and `BehavioralSuite.skipped_loops: tuple[LoopSkipRecord, ...]`.

### What counts as derivable

A `PERFORM UNTIL` loop only produces a test when **all** of the following hold — anything else
is recorded in `skipped_loops` with the exact reason, never guessed at:

1. The loop is not nested inside another `PERFORM UNTIL` (conservatively rejected — "nested
   loop not supported" — rather than approximated).
2. The exit condition's right-hand side is a plain integer literal (no decimal point, no
   variable) — this also means the whole extractor never touches the decimal-literal lexer bug
   from category 4, since it simply never accepts a non-integer boundary.
3. The loop-driving variable has a statically known integer `WORKING-STORAGE VALUE`.
4. Every instruction in the loop body is one of `IRMove`, `IRAdd`, `IRSubtract`, `IRMultiply`,
   `IRDivide`, `IRIf`/`IRElse`/`IREndIf` (at most one level, no nested `IF`), or `IRDisplay`
   (side-effect-free, ignored). A `CALL`, a `PERFORM` of another paragraph, or any other
   instruction type inside the loop body disqualifies it.
5. Every named operand referenced anywhere in the body resolves to a variable with a statically
   known integer initial value (constants like `WS-PAYMENT` that are read but never mutated are
   fine; a reference to a variable with no `VALUE` clause is not).

### How a derivable loop is simulated

This is a **bounded, closed-form simulation over the already-parsed IR** — not execution of
arbitrary COBOL. For each boundary value the existing `app.behavioral.extraction.conditions`
module already generates around the loop's exit-condition literal (the same mechanism #129 uses
for `IF` boundaries — e.g. `n-1, n, n+1`), the loop-driving variable is overridden to that value
and the body is replayed instruction-by-instruction (`_run_body`), honoring at most one level of
`IF`/`ELSE` branching, until the (COBOL-correct, test-before-each-iteration) exit condition
holds — or a `10,000`-iteration safety cap is hit, in which case the whole loop is marked
not-derivable rather than reporting a partial/guessed result.

This naturally produces exactly the three test shapes the task asked for, with **no special-
casing needed for any of them** — they fall out of the boundary values already being `n-1`, `n`,
`n+1`:

* **zero-iteration boundary** — starting value already satisfies the exit condition (`n` and
  `n+1` for a `>=` loop).
* **one-iteration case** — starting value one step before the boundary.
* **accumulator expected-value derivation** — every variable the loop body mutates gets an
  `ExpectedStateChange(from_value, to_value)` from the simulation's actual arithmetic, plus a
  matching `ExpectedOutput`.

### Newly covered sources — full derivation report

**`t_interest_accrue`** (`PERFORM UNTIL WS-DAY >= 30` at line 14, paragraph `ACCRUE-DAILY`) —
`ground_truth_status = deterministic`, `test_type = loop_accumulator` for all 3 tests:

| test_id | input | iterations | WS-DAY: from→to | WS-INTEREST: from→to |
|---|---|---:|---|---|
| `BT-e484d899` | `WS-DAY=31` | 0 | 31→31 | 0→0 |
| `BT-06357ad6` | `WS-DAY=30` | 0 | 30→30 | 0→0 |
| `BT-29f4ccb5` | `WS-DAY=29` | 1 | 29→30 | 0→3 |

`WS-INTEREST` accrues `+3` per iteration from a starting value of `0`; the 1-iteration case
correctly derives `3 = 3 × 1`, not a guess.

**`t_loan_balance`** (`PERFORM UNTIL WS-BALANCE = 0` at line 14, paragraph `AMORTIZE`) —
`ground_truth_status = deterministic`, `test_type = loop_accumulator` for both tests:

| test_id | input | iterations | WS-BALANCE: from→to | WS-MONTHS: from→to |
|---|---|---:|---|---|
| `BT-641f6205` | `WS-BALANCE=0` | 0 | 0→0 | 0→0 |
| `BT-33f63e8c` | `WS-BALANCE=1` | 1 | 1→0 | 0→1 |

The 1-iteration test exercises the `IF WS-BALANCE < WS-PAYMENT` branch (`WS-PAYMENT`'s constant
value `500` is read but never mutated, and correctly not listed as an accumulator): starting at
`WS-BALANCE=1` (< 500), the loop takes the `MOVE 0 TO WS-BALANCE` branch, then unconditionally
`ADD 1 TO WS-MONTHS`, then exits — a genuine, non-fabricated derivation of the "final partial
payment" behavior, not just the simpler `SUBTRACT` branch.

Every test's `source_refs` points at the real `PERFORM UNTIL`/`END-PERFORM` lines in the actual
source file — no fabricated evidence IDs.

### Verification that nothing was fabricated

* `test_accumulator_expected_value_is_correct_not_fabricated` (new) independently recomputes
  `3 × iteration_count` and asserts it matches the simulator's output — not just "some value was
  produced."
* `test_loop_body_with_call_is_skipped_not_guessed` / `test_unresolvable_loop_bound_is_skipped_not_fabricated`
  construct loops that are deliberately *not* derivable (a `PERFORM` inside the loop body; an
  exit boundary referencing a variable with no known value) and assert they land in
  `skipped_loops` with a reason naming the actual blocker, never silently produce a test.
* `test_parser_incomplete_source_never_marked_executable` runs the real, already-parser-limited
  `t_batch_acct_update` source through the upgraded extractor and asserts no loop test is
  produced for it.
* `test_existing_if_else_boundary_extraction_unchanged` / `test_no_loops_means_no_loop_skips_recorded`
  guard that the original #129 extractor's output is byte-for-byte the same shape as before.

---

## 4. Regression run — before/after, measured

Ran `build_mmim_dataset(..., strict_eligibility=True)` over the full 45-source corpus twice: once
with the pre-upgrade extractor (`EXTRACTION_VERSION=p10-extract-v1`, generator `mmim-gen-v2`),
once with the upgraded one (`p10-extract-v2`, generator `mmim-gen-v3`).

| | BEFORE | AFTER |
|---|---:|---:|
| Sources with a `VALIDATION_REASONING` example | 22 / 45 (48.9%) | **24 / 45 (53.3%)** |
| Total dataset examples | 337 | 339 |
| Total behavioral tests across the dataset | 71 | 76 |
| `boundary_partition` tests | 71 | 71 (unchanged) |
| `loop_accumulator` tests | 0 | 5 |
| Newly covered sources | — | `t_interest_accrue`, `t_loan_balance` |
| Sources that regressed (lost coverage) | — | **0** |
| Split counts (train/validation/test) | 217 / 69 / 51 | 218 / 69 / 52 |
| Benchmark leakage | PASS | PASS |
| Split leakage | PASS | PASS |
| `validate_dataset` errors | 0 | 0 |

**Where the +2 came from — not conflated:**

* **Extractor capability**: 100% of the improvement. Both newly covered sources
  (`t_interest_accrue`, `t_loan_balance`) parse with **zero** diagnostics before *and* after —
  nothing about the parser or the corpus changed for them. The only thing that changed is that
  the extractor now looks at `PERFORM UNTIL` loops at all.
* **Corpus characteristics**: 0% — no source was added, removed, or edited.
* **Parser changes**: 0% — no parser or lexer code was touched by this change (the parser gaps
  found in category 4 are reported, not fixed, per this task's scope instruction).

**Split preservation**: source→split assignment is a pure function of `(dataset_version, seed,
source_id)` (`app/dataset/splitting.py::_bucket`) — unaffected by which tasks a source
contributes. Verified directly: `t_interest_accrue` was assigned to `train` and `t_loan_balance`
to `test` in **both** the before and after builds; the count deltas (`train +1`, `test +1`,
`validation +0`) are exactly and only the two newly-added `VALIDATION_REASONING` examples
landing in the splits their sources already belonged to. No source moved splits.

**Remaining skips (21)**: all recorded in `manifest.json["skipped"]` with `reason:
"no_derivable_behavioral_tests"` and a `parser_status` block; see §2 above for the underlying
cause of each. None of them is silently converted into a false pass — quality over coverage,
exactly as instructed.

---

## 5. Versioning decision

`dataset_version` **stays `"mmim-v2"`** — the corpus (45 sources), task taxonomy (8 task types),
and eligibility rules are unchanged; this is still the same dataset contract. What changed is the
deterministic *pipeline* that produces one task's ground truth, so `generator_version` bumps:
`mmim-gen-v2` → **`mmim-gen-v3`** (`MMIM_GENERATOR_VERSION_V3`, `app/dataset/version.py`).
`app/behavioral/version.py::EXTRACTION_VERSION` bumps `p10-extract-v1` → `p10-extract-v2`
correspondingly, and every regenerated example's `metadata.generator_version` reflects it —
nothing is silently left stamped with the old value. The prior `mmim-gen-v2` build of `mmim-v2`
is superseded in place (not kept as a separate snapshot directory); this document is that
supersession's record. `mmim-v1` (`mmim-gen-v1`) is untouched and unaffected either way.

---

## 6. Repository component gap (documented per instruction — not fixed)

`TRANSFORMATION_PLANNING`'s `repositories` field is empty for all 45 sources because
`app.java_modernization.architecture.builder.build_architecture` never emits a
`ComponentType.REPOSITORY` component for *any* input in this corpus — confirmed by direct
inspection of `by_type` totals across the full corpus: `{"DTO": 45, "SERVICE": 76, "DOMAIN": 7,
"INTEGRATION": 12}` — `REPOSITORY` does not appear. This is a **Phase 9 architecture-builder
limitation**, not a dataset-generation limitation: the builder's component classification logic
does not currently have a rule that maps any COBOL shape to `REPOSITORY`, regardless of what the
source looks like.

**COBOL patterns that would legitimately warrant a REPOSITORY component**: `FILE SECTION` +
`OPEN`/`READ`/`WRITE`/`CLOSE` sequential file access (`t_batch_acct_update`,
`t_daily_trans_report`, `t_inventory_extract`, `t_payroll_file_post` — all four already in this
corpus) is the textbook case — a repository is exactly the OO abstraction over that kind of
record-at-a-time file I/O. None of the four currently produce a `REPOSITORY` component, because
(independently of this) their `FILE SECTION`/`OPEN`/`READ` statements are also unsupported syntax
(category 5 above) — the architecture builder has no IR-level evidence of file access to build a
component from in the first place.

Per this task's explicit instruction, `ArchitectureBuilder` was **not** modified to manufacture
`REPOSITORY` examples. This gap is documented, not worked around.

---

## 7. Tests run

```
python -m pytest tests/behavioral/ -q          # 57 passed (46 existing + 11 new loop tests)
python -m pytest tests/dataset/ -q              # 116 passed (mmim-v1: 25 unmodified; mmim-v2: 36; shared dataset infra: 55)
python -m ruff check app/ tests/dataset/ tests/behavioral/     # all checks passed
python -m mypy app/dataset/ app/behavioral/ --ignore-missing-imports   # no issues, 38 files
```

No existing test was weakened, skipped, or deleted. `tests/behavioral/test_extraction.py` (the
original #129 suite) and `tests/dataset/test_mmim_dataset.py` /
`tests/dataset/test_instruction_adapter.py` (mmim-v1) pass unmodified.

---

VALIDATION COVERAGE:
48.9% -> 53.3%

NEWLY COVERED SOURCES:
2

REMAINING SKIPS:
21

EXTRACTOR STATUS:
NEEDS MORE WORK

MMIM V2 STATUS:
READY FOR FURTHER DATA EXPANSION

KAGGLE:
DO NOT START

NEXT STEP:
The dominant remaining blocker (9/21 remaining skips) is the decimal-literal-in-PROCEDURE-DIVISION lexer bug plus missing compound AND/OR condition support in IF statements (category 4) — both genuine parser/lexer gaps, reported here per the "stop and report separately" instruction rather than fixed in this pass. Fixing those two parser gaps (not the extractor) is the highest-leverage next step and would very likely unlock most of category 4's 9 sources for VALIDATION_REASONING (and, as a side effect, BUSINESS_RULE_EXTRACTION density) without any further extractor work.
