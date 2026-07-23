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

Enterprise backend for parsing COBOL, JCL, Copybooks, building dependency graphs, extracting business rules, and assisting modernization using Large Language Models.

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

This project aims to build an **AI-powered enterprise modernization platform** capable of understanding legacy applications before applying Generative AI.

Unlike traditional AI wrappers around source code, this platform first builds a structured understanding of the application through deterministic analysis, then uses AI for intelligent modernization.

---

# ✨ Current Features

## Enterprise Backend

- ✅ FastAPI REST API
- ✅ Enterprise project architecture
- ✅ Configuration management
- ✅ Structured logging
- ✅ Global exception framework
- ✅ Request correlation middleware

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
             (Upcoming COBOL Parser)
```

---

# 🛠 Tech Stack

| Category | Technology |
|-----------|------------|
| Backend | FastAPI |
| Language | Python 3.12 |
| Validation | Pydantic v2 |
| Logging | Loguru |
| Testing | Pytest |
| Formatting | Black |
| Linting | Ruff |
| Type Checking | MyPy |
| AI Framework | LangChain *(planned)* |
| Vector Database | ChromaDB *(planned)* |
| LLM | Llama 3 *(planned)* |

---

# 📂 Project Structure

```text
app/
│
├── api/
├── core/
├── ingestion/
├── workspace/
│
tests/
│
docs/
│
scripts/
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

## 🚧 Phase 4 — Mainframe Parsing

- COBOL Lexer
- COBOL Parser
- Copybook Resolver
- JCL Parser
- AST Generation

---

## 🚧 Phase 5 — Static Analysis

- Dependency Graph
- Call Graph
- Business Rule Extraction
- Data Flow Analysis

---

## 🚧 Phase 6 — AI Modernization Engine

- Retrieval-Augmented Generation (RAG)
- LLM Integration
- Documentation Generation
- Modernization Recommendations
- Code Explanation

---

# 📈 Current Status

| Component | Status |
|-----------|--------|
| Enterprise Backend | ✅ |
| File Upload | ✅ |
| Workspace Management | ✅ |
| Workspace Intelligence | ✅ |
| COBOL Lexer | 🚧 |
| COBOL Parser | 🚧 |
| Static Analysis | 🚧 |
| AI Modernization | 🚧 |

---

# 🧪 Testing

Current Quality Metrics

- ✅ 265 Automated Tests
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

Run

```bash
uvicorn app.main:app --reload
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