# AI-Powered Mainframe Modernization Assistant Roadmap

Status reflects the repository as verified in the release acceptance pass. Detailed per-fix
history lives in `docs/`.

## Phase 1 — Enterprise Bootstrap

- [x] Repository Setup
- [x] GitHub Setup
- [x] Packaging
- [x] Configuration
- [x] Logging
- [x] FastAPI Bootstrap
- [x] Middleware
- [x] Exception Handling
- [x] Testing

---

## Phase 2 — File Ingestion

- [x] Upload API
- [x] Workspace Manager
- [x] Metadata Extraction
- [x] Encoding Detection

---

## Phase 3 — COBOL Parser

- [x] Lexer
- [x] Parser
- [x] AST
- [x] Intermediate Representation
- [x] Fixed-format source normalization wired into the analysis pipeline (position-preserving)
- [x] Continuation lines (`-` in column 7) — nonnumeric literal splicing across a continued line (`CobolLexer._try_resume_continued_string`); unevidenced by the 45-source corpus, covered by synthetic tests
- [x] Copybook (`COPY`) expansion — `app/parser/resolver/copybook.py`'s `CopybookExpander`: resolves `COPY member [OF|IN library] [REPLACING ==old== BY ==new== ...].` against the source file's own directory, recursively expands nested copybooks, detects circular COPY. Diagnostics inside expanded content report a flattened line number, not the copybook's own file/line (documented scope decision — see the module's own docstring). Unevidenced by the 45-source corpus, covered by synthetic tests.
- [x] JCL parser — new `app/jcl/` package (lexer, AST, parser, `JclAnalysisService`): `JOB`/`EXEC`/`DD` statements, continuation lines, comments, in-stream data. `PROC`/`PEND`/conditional JCL captured whole as unsupported, never expanded or fabricated. No real JCL corpus in this repo to validate against; covered by synthetic tests (`tests/jcl/`) against the standard grammar. Exposed over HTTP via `POST /workspaces/{id}/jcl/analyze` (previously only exercised by `tests/jcl/`, with zero API/frontend wiring).

---

## Phase 4 — Static Analysis

- [x] Dependency Graph (COPY / CALL / PERFORM / variable read-write / condition references)
- [x] Control Flow
- [x] Dedicated Call Graph and Data Flow views — the call graph was already surfaced as Overview's "Critical Topology" (`app/frontend/app.py`'s `_render_critical_topology`, built from `generate_flow()`'s control/call-flow graph). New this task (#stage49): a dedicated Data Flow graph — `app/analysis/dependencies/data_flow.py`'s `build_data_flow_graph()` turns the existing per-paragraph `VARIABLE_READ`/`VARIABLE_WRITE` dependencies (previously only exposed as a flat list) into a real graph of paragraph <-> data-item nodes and `READS`/`WRITES` edges, reusing the same `Flow`/`FlowNode`/`FlowEdge` types the call graph uses rather than inventing a new representation. Wired into `/analyze` as `data_flow_graph` and rendered in the Dependencies view alongside the existing dependency graph.

---

## Phase 5 — Business Intelligence

- [x] Business Rule Extraction
- [x] Documentation Generator

---

## Phase 6 — AI

- [x] Embeddings
- [x] ChromaDB
- [x] RAG
- [x] Chat (requires a configured LLM backend for generative answers)

---

## Phase 7 — Modernization

- [x] Java Generation (validated with a real `javac` on the 45-program corpus)
- [x] Java Recommendations and Modernization Strategy
- [x] Migration Report
- [x] Cloud Readiness assessment — `app/modernization/cloud/` (`CloudReadinessAnalyzer`): a four-tier categorical assessment (`CLOUD_READY` / `NEEDS_REFACTORING` / `REQUIRES_REARCHITECTURE` / `NOT_RECOMMENDED`) driven by concrete structural evidence (EXEC SQL/CICS/DLI occurrences, `CALL 'CBLTDLI'` as an equivalent IMS/DL-I signal, VSAM indicators, external CALL count, parser coverage gaps), matching this codebase's existing "no numeric score, every threshold a documented structural count" philosophy (see `ModernizationStrategyAnalyzer`'s own docstring). Every tier cites its evidence with line numbers; never fabricates a tier when signals are absent. Wired into `POST /workspaces/{id}/modernization/intelligence` as `cloud_readiness`, alongside `invoked_by_jobs` — real, honest workspace-level JCL correlation (`app/workspace/jcl_correlation.py`): every `.jcl` job step in the workspace whose `EXEC PGM=` matches this program. True VSAM-DD-statement detection from JCL was deliberately not built — standard JCL syntax has no inline VSAM marker (VSAM-ness is a catalog attribute, not JCL syntax), so claiming that signal would mean fabricating one that doesn't honestly exist.

---

## Phase 8 — Dashboard

- [x] Streamlit UI
- [x] Search — `GET /workspaces/{id}/search` (`app/workspace/search.py`'s `WorkspaceSearcher`): plain, case-insensitive line-based text search across every workspace file, with a real search box wired into the topbar. Deliberately not semantic/embedding search — this project's own RAG stack has no real embedding provider wired in yet (see the module's own docstring).
- [x] Visualization (architecture and dependency views)
- [x] Reporting
- [x] Graphviz DOT export — `GET /workspaces/{id}/export/graph.dot` (`app/analysis/graphviz_export.py`'s `to_dot()`): renders the dependency graph, control/call-flow graph, or data flow graph as standard Graphviz DOT source text, for any Graphviz-compatible viewer/tool. Emits DOT text only (no `graphviz` PyPI dependency, no shelling out to the `dot` binary, which this environment does not have installed) — AGENTS.md's other three Future-stack items (IBM Z Open Tools, Zowe CLI, Neo4j) were left out: the first two need real z/OS/z/OSMF connectivity this environment cannot reach (and could not honestly test), and Neo4j needs a running instance to verify integration code against, which none of this session's other work has ever shipped without.

---

## Phase 9 — Training Data

- [x] MMIM dataset generator (`mmim-gen-v25`, dataset `mmim-v2`, deterministic, leakage-checked)

---

## Next

- [x] Consume `>>SOURCE FREE|FIXED` directives — `CobolLexer` now skips the directive line whole (`_is_source_directive`) instead of letting it corrupt the token stream; detection itself (`FormatDetector`) was already implemented. Unevidenced by the 45-source corpus, covered by synthetic tests.
- [x] Add a continuous-integration workflow running `black --check .`, `ruff check .`, `mypy app` and `pytest` (`.github/workflows/ci.yml`)
- [x] Copybook expansion and JCL parsing — implemented as the two dedicated Phase 3 entries above (`CopybookExpander`, `app/jcl/`); listed here as a leftover duplicate from before those entries carried their own detail.
