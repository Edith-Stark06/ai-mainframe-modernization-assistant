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
- [ ] Fixed-format source normalization wired into the analysis pipeline
- [ ] Copybook (`COPY`) expansion
- [ ] JCL parser

---

## Phase 4 — Static Analysis

- [x] Dependency Graph (COPY / CALL / PERFORM / variable read-write / condition references)
- [x] Control Flow
- [ ] Dedicated Call Graph and Data Flow views

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
- [ ] Cloud Readiness assessment

---

## Phase 8 — Dashboard

- [x] Streamlit UI
- [ ] Search
- [x] Visualization (architecture and dependency views)
- [x] Reporting

---

## Phase 9 — Training Data

- [x] MMIM dataset generator (`mmim-gen-v24`, dataset `mmim-v2`, deterministic, leakage-checked)

---

## Next

- [ ] Wire `FormatDetector` / `SourceNormalizer` into `AnalysisService` (position-preserving), then re-audit the corpus and regenerate the dataset as its own investigated change
- [ ] Add a continuous-integration workflow running `black --check .`, `ruff check .`, `mypy app` and `pytest`
- [ ] Copybook expansion and JCL parsing
