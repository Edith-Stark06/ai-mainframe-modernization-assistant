# TASK-012 — AST Foundation

## Milestone

Phase 5 — COBOL Syntax Analysis

---

# Objective

Create the Abstract Syntax Tree (AST) model used by the COBOL parser.

This task introduces the immutable node hierarchy that will represent COBOL programs.

No parsing logic shall be implemented.

---

# Scope

Implement

app/parser/ast/

- node.py
- program.py
- division.py
- visitor.py

app/parser/syntax/

- parser_interfaces.py
- parser_exceptions.py

---

# AST Design

Create a common base class

ASTNode

Properties

- start_position
- end_position

All AST nodes shall inherit from ASTNode.

---

# Program Node

Represent an entire COBOL program.

Initially contain

- Identification Division
- Environment Division
- Data Division
- Procedure Division

Divisions may be optional.

---

# Division Node

Represent a COBOL division.

Contain

- division name
- child nodes

---

# Visitor Pattern

Create

ASTVisitor

Expose

visit_program()

visit_division()

Additional methods will be added later.

---

# Parser Interfaces

Create

ParserProtocol

Responsible for

parse()

No implementation.

---

# Exceptions

Create

ParserError

Used by future parser tasks.

---

# Tests

Create

tests/parser/test_ast_models.py

Test

- node construction
- inheritance
- immutability
- visitor dispatch
- program node
- division node

---

# Documentation

Create

docs/architecture/ast.md

Describe

- AST philosophy
- immutable nodes
- visitor pattern
- parser pipeline

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

- parser
- recursive descent
- statements
- expressions
- COPY
- diagnostics

---

# Expected Commit

feat(parser): implement AST foundation

---

# Expected Pull Request

feat(parser): implement AST foundation

---

# Definition of Done

✔ AST model implemented

✔ Visitor interface implemented

✔ Parser protocol implemented

✔ Tests passing

✔ Documentation complete