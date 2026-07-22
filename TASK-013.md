# TASK-013 — Recursive Descent Parser Framework

## Milestone

Phase 5 — COBOL Syntax Analysis

---

# Objective

Implement the parser framework that consumes lexer tokens and
produces the root ProgramNode.

This task establishes parser navigation and error handling.

No COBOL grammar parsing shall be implemented.

---

# Scope

Implement

app/parser/syntax/

- parser.py
- token_stream.py
- parser_state.py
- parser_errors.py

---

# Responsibilities

Implement

Parser

TokenStream

ParserState

ParserError hierarchy

---

# TokenStream

Responsible for

- current()
- peek()
- advance()
- eof()
- expect()

The parser shall never access token lists directly.

---

# Parser

Expose

parse()

Return

ProgramNode

Initially the ProgramNode may contain no divisions.

---

# Parser State

Track

- current token
- parser position
- error count

---

# Exceptions

Create

UnexpectedTokenError

UnexpectedEOFError

Both inherit ParserError.

---

# Tests

Create

tests/parser/test_parser_framework.py

Cover

- TokenStream navigation
- peek()
- advance()
- expect()
- eof()
- parser construction
- empty program
- unexpected token
- unexpected EOF

---

# Documentation

Create

docs/architecture/parser-framework.md

Explain

- recursive descent architecture
- token stream abstraction
- parser state
- future grammar parsers

---

# Requirements

Pass

black --check .

ruff check .

mypy app

pytest

---

# Explicitly Out of Scope

Do NOT implement

- Identification Division
- Data Division
- Procedure Division
- Statements
- Expressions
- COPY
- Semantic analysis

---

# Expected Commit

feat(parser): implement parser framework

---

# Expected Pull Request

feat(parser): implement recursive descent parser framework

---

# Definition of Done

✔ TokenStream implemented

✔ Parser framework implemented

✔ Parser state implemented

✔ Error hierarchy implemented

✔ Tests passing

✔ Documentation complete