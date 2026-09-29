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

- [x] Embeddings — `app/rag/embeddings/provider.py`'s `SentenceTransformerProvider` (`all-MiniLM-L6-v2`, 384-dim, runs entirely on-device): the production default via `app/api/dependencies/rag.py`'s `get_embedding_provider`, replacing the previously-always-used `DeterministicFakeProvider`. Verified against real semantic similarity (related sentences embed closer together than unrelated ones), not just "does not crash" — see `tests/rag/test_sentence_transformer_provider.py`.
- [x] ChromaDB
- [x] RAG — closed the loop that left `/chat` always querying an empty index regardless of embedding quality: `POST /chat/index` (`app/api/routers/chat.py`) runs the existing, previously-unwired `KnowledgeIngestor` (task #122) over a real analyzed file, bridges its chunks into the RAG layer's own chunk shape (`app/rag/knowledge_bridge.py` — the two `KnowledgeChunk` classes in `app.knowledge.chunk`/`app.rag.models` have incompatible fields, which is exactly why this was never wired before), embeds them for real, and writes them to the same `ChromaIndex` retrieval reads from. Verified with a real index-then-chat round trip (`tests/api/test_chat_index.py`), not two independently-mocked halves.
- [x] Chat — real LLM backend: `app/ai/providers/ollama.py`'s `OllamaProvider`, an opt-in production `LLMProvider` (`LLM_PROVIDER=ollama` in `.env`; defaults to `none`, since Ollama may not be installed/running in every deployment — never assumed on). Verified against a real, locally-running Ollama server and a real pulled model (`tests/ai/test_ollama_provider.py`, `tests/api/test_ai_dependencies.py`), including real generation, `max_tokens` truncation, usage stats, and the unreachable-server/unknown-model error paths mapping to the correct provider-neutral exception.

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
- [x] Container deployment — `Dockerfile`, `docker-compose.yml`, `.dockerignore`: API and Streamlit UI as two services from one image, workspace data in a named volume, health-gated startup. Verified by actually running it (not just building it): both services healthy, frontend reaches the API over the Docker network, and a full upload → analyze → index → retrieve → real-LLM-answer loop works inside the containers. The verification found and fixed real problems a passing build would have hidden: torch's default wheel pulled ~1GB of unusable CUDA libraries (image now uses the CPU wheel); the embedding model was downloaded at runtime (3m 26s on the first request, repeated on every container recreation, and impossible without internet) — now baked into the image and run offline; the remaining load time exceeded the UI's 30s timeout, so an opt-in `WARM_EMBEDDINGS` background warm-up brings the first request to ~9s; and `lru_cache` alone let a request during warm-up start a duplicate model load (8 concurrent callers built 8 copies), now serialized with a lock. Not tested on native Linux Docker (see README).
- [x] Copybook expansion and JCL parsing — implemented as the two dedicated Phase 3 entries above (`CopybookExpander`, `app/jcl/`); listed here as a leftover duplicate from before those entries carried their own detail.
