# AI-Powered Mainframe Modernization Assistant

## Mission

Build an enterprise-grade AI platform for analyzing, documenting, understanding, and modernizing IBM Z mainframe applications.

The project must be production-quality and demonstrate enterprise software engineering practices.

---

# Tech Stack

Backend
- Python 3.12+
- FastAPI
- Pydantic v2
- Loguru
- LangChain
- ChromaDB
- Ollama (Llama 3.x)
- Streamlit

Future
- IBM Z Open Tools
- Zowe CLI
- Neo4j (optional)
- Graphviz

---

# Architecture

Presentation
↓
FastAPI API
↓
Application Services
↓
Parser / Analysis / AI
↓
Domain Models

Never violate this architecture.

---

# Coding Standards

- Use Python type hints everywhere.
- Every public function requires a docstring.
- Use absolute imports.
- Never use print().
- Use Loguru for logging.
- Keep API routes thin.
- Business logic belongs in services.
- Domain models must never depend on FastAPI.
- Follow SOLID principles.

---

# Git

Use Conventional Commits.

Examples

feat:
fix:
docs:
test:
refactor:
chore:

---

# Testing

Every feature requires:

- Unit tests
- Type checking
- Ruff lint
- Black formatting

Before committing always run:

black .
ruff check .
mypy app
pytest

---

# Parser Philosophy

Never send raw COBOL directly to the LLM.

Pipeline

COBOL
↓
Lexer
↓
Parser
↓
AST
↓
Intermediate Representation
↓
Static Analysis
↓
Business Rules
↓
RAG
↓
LLM

---

# AI Philosophy

The LLM is an assistant.

The parser is the source of truth.

Never allow AI to replace deterministic parsing.

---

# Performance

Large COBOL systems may contain thousands of files.

Design for scalability.

Avoid unnecessary memory copies.

Prefer streaming where possible.

---

# Documentation

Every module should include:

Purpose

Responsibilities

Dependencies

Examples

---

# Goal

This repository should resemble a production-quality enterprise platform rather than a student project.