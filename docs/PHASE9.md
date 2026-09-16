# Phase 9 — Java Modernization (#125 / #126 / #127 / #128)

```
AnalysisBundle (Phase 1–5, reused — no re-analysis)
   │
   ├─ #125 build_architecture      -> JavaArchitecture   (deterministic, evidence-based, NO LLM)
   │
   ├─ #126 generate_project        -> GeneratedProject   (existing Java backend output + traceability)
   │
   ├─ #127 JavaCompiler.compile    -> CompilationResult  (controlled workspace, timeout, structured diagnostics)
   │
   └─ #128 SelfRepairLoop.run      -> RepairResult       (bounded, grounded, structured attempt history)
```

**Central rule:** Phase 9 produces a modernization **candidate**.
`semantic_equivalence_verified` is `False` everywhere. A compiling Java
program is **not** proof that COBOL behavior was preserved — Phase 10
(#129–#131) owns behavioral equivalence.

## #125 — architecture (`app/java_modernization/architecture/`)

`build_architecture(bundle) -> JavaArchitecture` — deterministic, no LLM.
Content-derived `architecture_id` + `content_hash`.

| output | source of evidence |
|---|---|
| `SERVICE` per rule-bearing paragraph | business rules (referenced by `rule_id`, never duplicated) + paragraph line span |
| `DOMAIN` state component | `SHARED_MUTABLE_STATE` risk |
| `INTEGRATION` + `ExternalInterface` + `Assumption` | each external `CALL` target (`modeled = False`) |
| `DTO` + `data_model` | WORKING-STORAGE fields |
| `primary_strategy` / `alternative_strategies` | Phase 4 strategy engine (not re-chosen) |
| `unsupported_behaviors` | coverage gaps, parser diagnostics, **and the existing generator's `// TODO: implement …` stubs** (surfaced, not hidden) |

Every `ArchitectureComponent` carries `Evidence` and `SourceRef`s. No evidence → nothing invented.

## #126 — generation (`app/java_modernization/generation/`)

`generate_project(bundle, architecture) -> GeneratedProject`. The **translated logic is the existing Java backend's output verbatim** — Phase 9 does not re-translate COBOL. This layer adds:

- `src/<Main>.java` (the real translation) + `src/<Main>State.java` (mechanical `record` from the data model) + `MODERNIZATION_MANIFEST.json`.
- one `GeneratedJavaArtifact` per class / method / record with `source_locations`, `business_rule_ids`, `architecture_component_id`, and `mapping_status` = `mapped` | `unavailable` (never a fabricated line number).
- every `UnsupportedBehavior` and assumption carried forward; `semantic_equivalence_verified = False`.

## #127 — compilation (`app/java_modernization/compilation/`)

`JavaCompiler(workspace_root, timeout_s=30).compile(project) -> CompilationResult`.

- The `javac` command is built by this module — **never from model output**.
- Every project-relative path is validated: no `..`, no absolute, no drive letter, must land under the per-project workspace.
- Timeout + bounded output buffer; the process is killed on timeout → a structured `P9-TIMEOUT` diagnostic.
- `CompilerDiagnostic`: severity (`ERROR` / `WARNING` / `NOTE` — warnings are **not** failures), message, file, line, column, and a best-effort `cobol_source_mapping` (`SourceRef`) + `business_rule_ids` + `architecture_component_id` derived from the #126 artifacts.
- A compile *failure* is a normal result with `success = False`; only an unusable workspace / missing JDK raises.

## #128 — self-repair (`app/java_modernization/repair/`)

`SelfRepairLoop(provider, compiler, max_attempts=3).run(project, bundle) -> RepairResult`.

```
compile -> [ diagnostics -> build_repair_context (Phase 8, targeted, provenance-checked)
             -> LLM structured patch -> validate_patch -> apply_patch -> compile
             -> record RepairAttempt ] x max_attempts
```

- **Targeted context** (`build_repair_context`): only the failing diagnostics, the affected Java window, the COBOL it maps to, the relevant business rules and IR — each a Phase 8 `ContextItem` with a validated `Provenance`. `GroundedContext.validate()` is the hard boundary; nothing without provenance is sent. Never the whole repository.
- **The model proposes a structured patch** (`{files:[{path, changes:[{start_line,end_line,replacement}]}], explanation, source_basis}`) — it never runs a command. The loop validates and applies it.
- **`validate_patch` rejects**: path outside the project, non-`.java`, a file with no compiler error, inverted / out-of-bounds line range, a patch that removes the class/record declaration or empties the file.
- **Loop protection**: `max_attempts`, duplicate-patch detection (patch signature), no-progress detection (compiler diagnostic signature unchanged), unsafe-patch and provider-failure stops. Every attempt is recorded in `RepairResult.attempts` with the proposed patch, whether it was applied, the recompilation result and remaining error count.
- `RepairResult.stopped_reason` ∈ `compiled | max_attempts | no_progress | duplicate_patch | unsafe_patch | provider_failure | not_needed`. Success means **the Java compiled** — not behavioral equivalence.

## Existing backend

Not modified. `tests/backend/` and `tests/golden/` are unchanged and pass. The existing generator's PERFORM/CALL stub gaps are reported as explicit `UnsupportedBehavior` records, not hidden.

## Tests

`tests/java_modernization/` — 36: architecture (10), generation (8), compilation (7), repair (8), end-to-end (3). Compilation/repair tests skip if `javac` is absent. No test uses a live LLM (scripted `LLMProvider` doubles) or the network. Verified against **JDK 24** (`javac 24.0.1`).
