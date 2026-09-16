# Phase 10 — Behavioral Equivalence (#129 / #130 / #131)

```
AnalysisBundle (Phase 1-5, reused)
   │
   ├─ #129 extract_behavioral_tests()  -> BehavioralSuite  (deterministic, evidence-based, NO LLM)
   │
   ├─ #130 generate_java_tests() + JavaTestRunner -> compile + EXECUTE real Java (javac/java)
   │
   └─ #131 ProgramExecutor (COBOL / Java / scripted) + compare_observation() -> Phase10Report
             PASS / FAIL / INCONCLUSIVE — never inferred, only observed
```

**Central rule:** a compiling Java program, a passing generated-Java
self-test, or matching business rules/AST/IR are never sufficient for
PASS. `compare_observation` only looks at two `ExecutionResult` objects
— nothing else. If the COBOL side was not actually executed, the result
is `INCONCLUSIVE`, never upgraded.

## Audit (before implementation)

`origin/main` at merge of PR #117 (Phase 9). Verified present: parser/AST,
IR, CFG, dependencies, business rules, risk/strategy, coverage/confidence,
`app/java_modernization/` (architecture #125, generation #126, compilation
#127, repair #128), Phase 8 `app.knowledge`/`app.grounded` provenance,
existing Java backend + golden tests (355 passing, untouched).

**Baseline:** `pytest -q` → 3389 passed / 12 failed (pre-existing
parser/lexer/IR set, unrelated). Python 3.12.10. JDK: `javac 24.0.1` /
`java 24.0.1` — real Java compilation and execution are used throughout.
**GnuCOBOL (`cobc`) is NOT on PATH — no COBOL runtime was downloaded to
work around this** (per the task's explicit instruction). Every real-COBOL
comparison in this environment is therefore `INCONCLUSIVE`, and the
report says so explicitly (`real_cobol_execution: false`).

## #129 — behavioral test extraction (`app/behavioral/extraction/`)

`extract_behavioral_tests(bundle) -> BehavioralSuite` — deterministic, no LLM.

- Only business rules with one parseable comparison (`[NOT] <var> <op> <literal>`)
  become tests; rules sharing a paragraph + condition variable (an
  `IF`/`ELSE` pair) are grouped so one boundary value produces one test
  recording whichever rule actually fires — never a fabricated "nothing
  happens" expectation for the other branch.
- Boundary values bracket the threshold (`N-1, N, N+1` for numeric; the
  literal + one deterministic "other" for strings) — not a Cartesian blow-up.
- `executable` / `inconclusive_reason` are computed from **Phase 9's own
  generated Java**: a paragraph with a `// TODO: implement … (BE009)`
  stub, or a paragraph never PERFORMed from the entry point (so it has
  *no* method at all — a distinct, equally-fatal gap this task's audit
  found), or global unsupported-syntax coverage codes, all mark the case
  non-executable with an explicit reason. Nothing is invented.
- `test_id` is a content hash (`source_id`, paragraph, variable, value) —
  stable across runs, never random.

## #130 — Java test generation (`app/behavioral/javatests/`)

No JUnit (or any framework) exists in this Python-first repository.
**Introduced: one reflective, framework-free harness class per source**
(`<Main>BehaviorHarness.java`), driven by a plain `java` invocation per
test case:

```
java <Main>BehaviorHarness age=17 expect:wsResult=DENIED
##EXEC## ok=true
##STDOUT## ...
##FIELD## wsResult=DENIED
##ASSERT## PASS
```

Field names use the **existing** `app.backend.java.naming.to_java_field_name`
convention — never re-derived. Only `suite.executable_tests` get an
artifact; a #129 case already marked non-executable needs no Java test.
`JavaTestRunner` compiles via the #127 `JavaCompiler` (same sandbox) and
executes the harness with a timeout + bounded output buffer, distinguishing
*execution failure* (harness crashed/timed out) from *assertion failure*
(ran fine, self-check against #129's expectation didn't hold).

## #131 — COBOL vs Java behavioral comparison (`app/behavioral/execution/`, `app/behavioral/comparison/`)

- `ProgramExecutor` protocol + three implementations: `JavaExecutor` (real
  `javac`/`java`, reuses the #130 harness), `CobolExecutor` (real GnuCOBOL
  `cobc -x`; **unverified in this environment** since `cobc` is absent —
  documented, not faked), `ScriptedExecutor` (deterministic fake, proves
  the comparator independently of runtime availability, as required).
- `ExecutionResult` distinguishes `executed` (did the runtime run at all)
  from `success` (did the program itself report success).
- `compare_observation`: INCONCLUSIVE if the #129 case is non-executable,
  either side didn't execute, either side failed before producing
  behavior, or a required observation is missing from either side. FAIL
  only when both sides produced the required observation and it differed.
  PASS only when every required observation was present on both sides and
  matched. An "empty" test with nothing to assert is INCONCLUSIVE, never
  a vacuous PASS.
- Normalization (`comparison/normalize.py`, every rule documented): CRLF→LF
  only; numeric comparison as **exact integers** (never float) so `"018"`
  == `"18"` but decimal/scientific text falls back to exact string
  comparison; no case-folding, no padding/whitespace trimming — COBOL
  fixed-width semantics are never blurred away.
- `Phase10Report.overall_status` — `BEHAVIORALLY_VERIFIED` only when
  `pass_count > 0` **and** `fail_count == inconclusive_count == 0` **and**
  both executors were real. A single FAIL forces
  `BEHAVIORAL_DIFFERENCE_FOUND`; any INCONCLUSIVE (or a non-real executor,
  even if every comparison happened to PASS) forces `INCONCLUSIVE`. Counts
  are always reported in full (`PASS: n / FAIL: n / INCONCLUSIVE: n`) —
  never collapsed into a single "equivalence percentage".
- Every `BehavioralComparison` carries `ArtifactVersions` (COBOL source
  hash, Java project hash, architecture hash, test-suite hash) so results
  from different generated versions can never be mixed.

## No automatic repair

Phase 10 only observes. A FAIL is recorded and reported; #128's
`SelfRepairLoop` is never invoked from here.

## Tests

`tests/behavioral/` — 46 tests: extraction (18), Java tests (9),
comparison logic (13), end-to-end (6, `javac`-gated). The end-to-end
suite proves all three outcomes — PASS and FAIL via a scripted COBOL
stand-in against **real** compiled/executed Java, and INCONCLUSIVE via
the actual default pipeline (real Java, real-but-unavailable COBOL) — plus
one complete traceability chain (COBOL source → business rule →
behavioral test → Java test → executions → comparison → status).
