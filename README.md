<div align="center">

# 🤖 AI-Powered Mainframe Modernization Assistant

### Enterprise AI Platform for Understanding, Analyzing & Modernizing IBM Z Mainframe Applications

<p align="center">
<img src="https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python">
<img src="https://img.shields.io/badge/FastAPI-Enterprise-009688?style=for-the-badge&logo=fastapi">
<img src="https://img.shields.io/badge/License-MIT-success?style=for-the-badge">
<img src="https://img.shields.io/badge/Status-Active%20Development-orange?style=for-the-badge">
<img src="https://img.shields.io/badge/IBM-Z-purple?style=for-the-badge">
</p>

---

### 🚀 Building the Next Generation AI Platform for Mainframe Modernization

Enterprise backend for parsing COBOL, building dependency graphs, extracting business rules, generating Java, and assisting modernization using Large Language Models. JCL files and copybooks are inventoried and cross-referenced; a JCL parser and copybook expansion are not implemented yet (see [Known Limitations](#-known-limitations)).

</div>

---

# 📖 Overview

Modern enterprises still rely on IBM Z mainframe systems that power banking, insurance, aviation, healthcare, retail, and government infrastructure.

Modernizing these systems is difficult because of:

- Millions of lines of COBOL
- Complex JCL workflows
- Deep copybook dependencies
- Business logic accumulated over decades
- Limited documentation
- High modernization risk

This project is an **AI-powered enterprise modernization platform** that understands legacy applications before applying Generative AI.

Unlike traditional AI wrappers around source code, this platform first builds a structured understanding of the application through deterministic analysis, then uses AI for intelligent modernization. The parser is the source of truth; the LLM is an assistant and is never sent raw COBOL.

---

# ✨ Current Features

## Enterprise Backend

- ✅ FastAPI REST API (15 operations under `/api/v1`)
- ✅ Enterprise project architecture
- ✅ Configuration management
- ✅ Structured logging
- ✅ Global exception framework
- ✅ Request correlation middleware

---

## COBOL Analysis & Modernization Pipeline

```text
COBOL → Lexer → Parser → AST → Semantic Analysis → IR
      → Control-Flow Graph → Dependencies / Business Rules / Risk / Strategy
      → Java generation (validated with a real javac)
```

- ✅ COBOL lexer, parser, AST, semantic analyzer and structured IR
- ✅ Syntax diagnostics with a stable code taxonomy (`SYN001`–`SYN005` errors, `SYN1xx` unsupported constructs, `SYN2xx` unmodelled constructs)
- ✅ Dependency analysis (COPY / CALL / PERFORM references, variable reads and writes, conditions)
- ✅ Business-rule extraction, risk assessment and modernization strategy
- ✅ COBOL → Java backend; the 45-program verification corpus compiles with `javac` and runs
- ✅ Retrieval-augmented explanation and documentation services (LangChain / ChromaDB / Ollama providers). When no LLM backend is configured the API reports `LLM_PROVIDER_NOT_CONFIGURED` instead of failing
- ✅ Streamlit UI with Overview, Business Rules, Dependencies, Architecture, COBOL ↔ Java, Java Workspace, Validation Center, Report and Modernization Chat views
- ✅ MMIM training dataset generator (`mmim-gen-v25`, dataset `mmim-v2`): 351 deterministic examples, source-level 226 / 71 / 54 train / validation / test split, leakage and validation reports

---

## Intelligent File Ingestion

- ZIP upload support
- Workspace management
- File validation
- Metadata extraction
- SHA-256 hashing
- Encoding detection
- Supported file types

```
.cbl
.cob
.cpy
.jcl
.txt
.zip
```

---

## Workspace Intelligence

Automatically analyzes uploaded projects and generates:

- Workspace inventory
- File classification
- Project summaries
- Metadata catalog
- File statistics

Example:

```text
Workspace

├── 412 COBOL Programs
├── 218 Copybooks
├── 87 JCL Files
├── 19 PROC Files
└── Project Inventory
```

---

# 🏗 Architecture

```text
                    Upload API
                        │
                        ▼
                Workspace Manager
                        │
                        ▼
                 File Validation
                        │
                        ▼
                Metadata Extraction
                        │
                        ▼
               Workspace Scanner
                        │
                        ▼
                File Classification
                        │
                        ▼
               Project Inventory
                        │
                        ▼
                Project Summary
                        │
                        ▼
      COBOL Lexer → Parser → AST → Semantic Analysis → IR
                        │
                        ▼
      CFG · Dependencies · Business Rules · Risk · Strategy
                        │
                        ▼
        Java Backend · RAG · LLM (assistant only)
                        │
                        ▼
            FastAPI  ←→  Streamlit UI
```

---

# 🛠 Tech Stack

| Category | Technology |
|-----------|------------|
| Backend | FastAPI |
| Language | Python 3.12 |
| Validation | Pydantic v2 |
| Logging | Loguru |
| Frontend | Streamlit |
| Testing | Pytest |
| Formatting | Black |
| Linting | Ruff |
| Type Checking | MyPy |
| AI Framework | LangChain |
| Vector Database | ChromaDB |
| LLM | Ollama (Llama 3.x), optional — not required to run analysis |

---

# 📂 Project Structure

```text
app/
│
├── api/              FastAPI routers and schemas
├── core/             configuration, logging, exceptions
├── ingestion/        upload, ZIP extraction, validation
├── workspace/        scanner, inventory, classification, summary
├── parser/           lexer, syntax parser, AST, semantic analysis, diagnostics
├── ir/               intermediate representation
├── analysis/         analysis service, dependencies, rules, coverage
├── modernization/    business rules, flow, risk, scoring, strategy
├── backend/          Java code generation
├── java_modernization/  Java workspace and validation
├── knowledge/, rag/, ai/, grounded/   retrieval and LLM-assisted explanation
├── advisor/, behavioral/, evaluation/, quality_loop/   quality and evaluation tooling
├── dataset/, benchmark/, training/    MMIM dataset generation and benchmarks
├── frontend/         Streamlit UI
├── compiler.py       standalone COBOL frontend driver
│
tests/
│
docs/                 design notes and per-fix audit reports
│
data/                 verification corpus and generated datasets
│
scripts/              dataset, benchmark, evaluation and training tools
```

---

# 📊 Development Roadmap

## ✅ Phase 1 — Enterprise Foundation

- FastAPI
- Configuration
- Logging
- Exception Handling
- API Schemas

---

## ✅ Phase 2 — Intelligent Ingestion

- Upload API
- ZIP Extraction
- Workspace Manager
- Metadata Extraction
- Validation

---

## ✅ Phase 3 — Workspace Intelligence

- Workspace Scanner
- Inventory
- File Classification
- Project Summary

---

## ✅ Phase 4 — Mainframe Parsing

- ✅ COBOL Lexer
- ✅ COBOL Parser and AST
- ✅ Semantic Analysis and IR
- 🚧 Copybook Resolver (COPY references are detected, not expanded)
- 🚧 JCL Parser (JCL files are inventoried, not parsed)
- ✅ Fixed-format source (sequence area, `*`/`/`/`D` indicator lines, columns 73-80) is detected and normalized in place before lexing, so diagnostic positions stay exact
- 🚧 Continuation lines (`-` in column 7) are not supported

---

## ✅ Phase 5 — Static Analysis

- ✅ Dependency Graph
- ✅ Control-Flow Graph
- ✅ Business Rule Extraction
- ✅ Risk Assessment and Modernization Strategy

---

## ✅ Phase 6 — AI Modernization Engine

- ✅ Retrieval-Augmented Generation (RAG)
- ✅ LLM Integration (optional Ollama backend)
- ✅ Documentation Generation
- ✅ COBOL → Java Generation
- ✅ Code Explanation and Modernization Chat

---

## ✅ Phase 7 — Dashboard & Training Data

- ✅ Streamlit UI
- ✅ MMIM training dataset (`mmim-v2`) with leakage and determinism checks

---

# 📈 Current Status

| Component | Status |
|-----------|--------|
| Enterprise Backend | ✅ |
| File Upload | ✅ |
| Workspace Management | ✅ |
| Workspace Intelligence | ✅ |
| COBOL Lexer / Parser / IR | ✅ (fixed and free format; see limitations) |
| Static Analysis | ✅ |
| Java Generation | ✅ |
| AI Modernization (RAG / LLM) | ✅ (needs a configured LLM backend for generative answers) |
| Streamlit UI | ✅ |
| JCL Parser | 🚧 |
| Copybook Expansion | 🚧 |
| Fixed-format Source Normalization in Pipeline | ✅ |
| Continuous Integration | 🚧 |

---

# 🧪 Testing

Current Quality Metrics

- ✅ 4,863 Automated Tests (full suite passes with no failures or skips when a JDK is installed)
- ✅ MyPy Type Checking
- ✅ Ruff Linting
- ✅ Black Formatting
- ✅ End-to-End Integration Tests

Run locally:

```bash
pytest
ruff check .
black --check .
mypy app
```

Tests are self-contained: git-ignored dataset splits (`train.jsonl`, `validation.jsonl`) are regenerated automatically from the tracked `all.jsonl` and split manifest when missing, and the tests that compile generated Java are skipped when no JDK (`javac`) is on `PATH`. Install a JDK to exercise them.

---

# ⚠️ Known Limitations

- **Fixed-format COBOL.** Format detection and position-preserving normalization run inside `AnalysisService` (see `docs/FIXED_FORMAT_NORMALIZATION.md`). Not covered: continuation lines (`-` in column 7, reported as a lexer error), fixed-format files with fewer than five non-empty lines (the detector cannot decide, so they are analyzed as written), and `>>SOURCE` directives. Files that use lines wider than 80 columns are recognized and never truncated.
- **JCL and copybooks.** JCL is not parsed and `COPY` members are not expanded.
- **Unsupported COBOL constructs.** Constructs the parser does not model are reported as `SYN1xx` / `SYN2xx` diagnostics rather than silently accepted; the generated Java for such programs is not guaranteed to be complete.
- **Generative AI.** Explanation and chat features need a running Ollama (or other configured) backend; without one the API returns `LLM_PROVIDER_NOT_CONFIGURED`.
- **CI.** There is no continuous-integration workflow in the repository yet; run the four commands above locally before committing.

---

# 🚀 Getting Started

Clone the repository

```bash
git clone https://github.com/Edith-Stark06/ai-mainframe-modernization-assistant.git
cd ai-mainframe-modernization-assistant
```

Create a virtual environment

```bash
python -m venv .venv
```

Activate

Windows

```bash
.venv\Scripts\activate
```

Linux / macOS

```bash
source .venv/bin/activate
```

Install dependencies

```bash
pip install -e ".[dev]"
```

Run the API

```bash
uvicorn app.main:app --reload
```

Run the Streamlit UI (in a second terminal; set `API_BASE_URL` if the API is not on the default address)

```bash
streamlit run app/frontend/app.py
```

---

# 🔬 Compiler Driver

The standalone compiler driver executes the complete COBOL frontend pipeline outside the REST API.

## Usage

```bash
python -m app.compiler <source-file>
```

## Example

```bash
python -m app.compiler examples/hello.cbl
python -m app.compiler examples/arithmetic.cbl
python -m app.compiler examples/conditional.cbl
python -m app.compiler examples/subprogram.cbl
```

## Expected Output

```text
Program HELLO

  Module HELLO

    Function __entry__

      entry:
        DISPLAY "HELLO WORLD"
        MOVE "WELCOME" -> WS-GREETING
        DISPLAY WS-GREETING
        MOVE 1 -> WS-COUNT
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Compilation succeeded |
| 1 | Source file not found or unreadable |
| 2 | Compilation completed with errors |

## Pipeline

```
Source File
    ↓
CobolLexer
    ↓
ProgramParser
    ↓
SemanticAnalyzer
    ↓
IRBuilder
    ↓
IR Pretty Printer (stdout)
```

Diagnostics are printed to **stderr**; the IR is printed to **stdout**.

---

API Documentation

```
http://127.0.0.1:8000/docs
```

---

# 🎯 Vision

Our long-term goal is to create an enterprise-grade AI platform capable of:

- Understanding legacy applications
- Extracting business knowledge
- Visualizing dependencies
- Assisting developers during modernization
- Reducing migration risk
- Accelerating digital transformation

---

# 🤝 Contributing

Contributions, discussions, and ideas are welcome.

Please read `CONTRIBUTING.md` before opening issues or pull requests.

---

# 📄 License

MIT License

---

<div align="center">

### ⭐ If you find this project interesting, consider giving it a star!

**Built with ❤️ for the IBM Z & Mainframe Modernization Community**

</div>