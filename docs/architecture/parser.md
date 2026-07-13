# Parser Architecture

## Overview

The `app.parser` package provides a layered, compiler-inspired architecture
for reading, understanding, and analysing IBM Z COBOL source programs.  It is
the core engine of the AI-Powered Mainframe Modernization Assistant's
COBOL Understanding Layer.

The architecture is modelled after production-quality compiler front-ends.
Each layer has a single, clearly defined responsibility and communicates
with adjacent layers through explicit data contracts — no layer reaches
across boundaries to access another layer's internals.

---

## Guiding Principles

| Principle | Application |
|---|---|
| **Immutability** | All shared value types (`Position`, `Token`) are frozen dataclasses. |
| **Protocol-driven design** | Interfaces (e.g. `ILexer`) are `typing.Protocol` — no abstract base classes. |
| **Parser is source of truth** | The LLM augments; it never replaces deterministic parsing. |
| **Separation of concerns** | Each sub-package owns exactly one compiler stage. |
| **Scalability** | Designed for corpora containing thousands of COBOL files. |

---

## Package Structure

```
app/
└── parser/                    ← Parser root namespace
    ├── __init__.py
    │
    ├── lexer/                 ← Lexical analysis (Phase 1)
    │   ├── __init__.py        ← Public API re-exports
    │   ├── position.py        ← Position value type
    │   ├── token.py           ← Token value type
    │   ├── token_types.py     ← TokenType enumeration
    │   └── interfaces.py      ← ILexer protocol
    │
    ├── syntax/                ← Syntax analysis / CST (Phase 2)
    │   └── __init__.py
    │
    ├── ast/                   ← Abstract Syntax Tree (Phase 3)
    │   └── __init__.py
    │
    ├── resolver/              ← COPY-book resolver (Phase 4)
    │   └── __init__.py
    │
    ├── semantic/              ← Semantic analysis (Phase 5)
    │   └── __init__.py
    │
    ├── ir/                    ← Intermediate Representation (Phase 6)
    │   └── __init__.py
    │
    └── diagnostics/           ← Diagnostic collection (cross-cutting)
        └── __init__.py
```

---

## Data Flow

```
COBOL Source Text
      │
      ▼
┌─────────────┐
│    Lexer    │  app.parser.lexer
│  (Phase 1)  │  ILexer.tokenize(source, filename) → list[Token]
└──────┬──────┘
       │  list[Token]
       ▼
┌─────────────┐
│   Syntax    │  app.parser.syntax           (future)
│  (Phase 2)  │  Produces: ConcreteTreeNode
└──────┬──────┘
       │  CST
       ▼
┌─────────────┐
│     AST     │  app.parser.ast              (future)
│  (Phase 3)  │  Produces: ProgramNode
└──────┬──────┘
       │  AST
       ▼
┌─────────────┐
│  Resolver   │  app.parser.resolver         (future)
│  (Phase 4)  │  Expands COPY statements
└──────┬──────┘
       │  Resolved AST
       ▼
┌─────────────┐
│  Semantic   │  app.parser.semantic         (future)
│  (Phase 5)  │  Type-checks, scope-checks
└──────┬──────┘
       │  Annotated AST
       ▼
┌─────────────┐
│     IR      │  app.parser.ir               (future)
│  (Phase 6)  │  Language-neutral graph
└─────────────┘
       │
       ▼
  AI / RAG / API
```

Diagnostics are collected at every stage and accumulated in
`app.parser.diagnostics` rather than raising exceptions, enabling
maximum error recovery.

---

## Core Models (Current Milestone)

### `Position`

```python
@dataclass(frozen=True, slots=True)
class Position:
    line: int       # 1-based line number
    column: int     # 1-based column number
    offset: int     # 0-based byte offset
    filename: str   # originating source file
```

`Position` is the atom of source location information.  Every `Token`
carries one.  Downstream components (diagnostics, IDE hover, cross-reference)
use `Position` to reconstruct precise source ranges.

**Design decisions:**
- `frozen=True` — immutability prevents accidental mutation across stages.
- `slots=True` — reduces per-instance memory footprint for large token streams.
- All four fields required — no optional fields; synthetic tokens use explicit
  placeholder filenames (e.g. the COPY-book member name).

---

### `TokenType`

```python
@unique
class TokenType(Enum):
    IDENTIFIER  = "identifier"
    KEYWORD     = "keyword"
    STRING      = "string"
    NUMBER      = "number"
    LEVEL_NUMBER= "level_number"
    PIC         = "pic"
    PERIOD      = "period"
    COMMA       = "comma"
    LPAREN      = "lparen"
    RPAREN      = "rparen"
    EOF         = "eof"
    UNKNOWN     = "unknown"
```

`TokenType` enumerates the terminal symbol categories recognised by the
lexer.  Only structural categories are defined at this milestone; COBOL
keyword variants (e.g. `MOVE`, `PERFORM`, `COMPUTE`) will be added when
the lexer is implemented in TASK-006.

**Design decisions:**
- `@unique` — the decorator enforces at import time that no two members
  share a value, preventing subtle classification bugs.
- Lowercase string values — used for serialisation in API responses and
  diagnostic messages; member identities are used for all internal
  comparisons.

---

### `Token`

```python
@dataclass(frozen=True, slots=True)
class Token:
    type:     TokenType
    lexeme:   str
    position: Position
```

`Token` binds a classification (`type`), the raw source text (`lexeme`),
and a source location (`position`) into a single, indivisible, hashable
value.  Tokens are the currency exchanged between the lexer and the
parser.

**Design decisions:**
- Three fields only — no metadata, no mutable state.
- `frozen=True` + `slots=True` — identical rationale to `Position`.
- Hashable — tokens may be stored in sets or used as dict keys by
  semantic analysis and cross-reference tables.

---

### `ILexer` Protocol

```python
@runtime_checkable
class ILexer(Protocol):
    def tokenize(self, source: str, filename: str) -> list[Token]: ...
```

`ILexer` is a structural protocol (PEP 544).  Any class that implements
`tokenize` with the correct signature satisfies the protocol without
declaring inheritance.  This decouples the interface from any
implementation and allows lightweight fakes in tests.

**Design decisions:**
- `typing.Protocol` over `abc.ABC` — structural sub-typing avoids
  coupling; easier to mock; idiomatic for modern Python.
- `@runtime_checkable` — enables `isinstance(obj, ILexer)` guards in
  diagnostic and validation code.
- Single method — the lexer has one job: produce tokens.

---

## Roadmap

| Task | Sub-package | Deliverable |
|------|-------------|-------------|
| TASK-006 | `lexer` | COBOL lexer implementation |
| TASK-007 | `syntax` | COBOL grammar and CST parser |
| TASK-008 | `ast` | AST node hierarchy and visitor |
| TASK-009 | `resolver` | COPY-book expansion engine |
| TASK-010 | `semantic` | Semantic analyser and symbol table |
| TASK-011 | `ir` | Intermediate representation and serialiser |
| TASK-012 | `diagnostics` | Diagnostic model and LSP formatter |

---

## Architectural Constraints

1. **No parser component imports from `app.api` or `app.services`.**
   Information flows upward through the architecture only.

2. **The lexer never sends raw COBOL to the LLM.**
   All source understanding happens deterministically first; the LLM
   receives the IR or structured summaries only.

3. **Immutability is non-negotiable for shared value types.**
   `Position` and `Token` must remain frozen.  New parser stages may
   introduce mutable builder types internally, but must produce
   immutable output.

4. **Diagnostics over exceptions for recoverable errors.**
   Parser stages accumulate diagnostics rather than aborting on the
   first error, enabling complete analysis of production COBOL files
   that may contain multiple issues.

5. **Scalability by design.**
   No unnecessary in-memory copies of large source buffers.  Prefer
   offset-based slicing over substring creation.  Prefer streaming
   where possible.

---

## References

- [TASK-005 — Parser Foundation](../../TASK-005.md)
- [ADR-001 — Project Architecture](ADR-001-project-architecture.md)
- [PEP 544 — Protocols: Structural subtyping](https://peps.python.org/pep-0544/)
- [Python `dataclasses` documentation](https://docs.python.org/3/library/dataclasses.html)
- [Python `enum` documentation](https://docs.python.org/3/library/enum.html)
