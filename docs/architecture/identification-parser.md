# Identification Division Parser Architecture

## Overview

This document describes the design of the COBOL IDENTIFICATION DIVISION
parser — the first grammar-aware component in the parser pipeline.

The Identification Division parser transforms a flat token stream into an
immutable `IdentificationDivisionNode` containing typed clause nodes for
each recognised clause.

---

## COBOL Grammar

The IDENTIFICATION DIVISION has the following structure:

```
IDENTIFICATION DIVISION.
PROGRAM-ID. <program-name> .
[AUTHOR.        <comment-entry> .]
[INSTALLATION.  <comment-entry> .]
[DATE-WRITTEN.  <comment-entry> .]
[DATE-COMPILED. <comment-entry> .]
[SECURITY.      <comment-entry> .]
```

- The `IDENTIFICATION DIVISION .` header is mandatory.
- `PROGRAM-ID` is the only required clause.
- All other clauses are optional and may appear in any order.
- Each clause is terminated by a period (`.`).

---

## Architecture

```
ProgramParser.parse(tokens)
      |
      |  detects IDENTIFICATION DIVISION header
      |
      v
IdentificationDivisionParser.parse(state)
      |
      |  parses header + clauses
      |
      v
IdentificationDivisionNode
  ├── ProgramIdClauseNode
  ├── AuthorClauseNode         (optional)
  ├── InstallationClauseNode   (optional)
  ├── DateWrittenClauseNode    (optional)
  ├── DateCompiledClauseNode   (optional)
  └── SecurityClauseNode       (optional)
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `ProgramParser` | Top-level coordinator; detects division presence via lookahead |
| `IdentificationDivisionParser` | Parses header + all clauses; raises `ParserError` on errors |
| `IdentificationDivisionNode` | Immutable root container for the division |
| `ProgramIdClauseNode` | Immutable carrier for the PROGRAM-ID value |
| `AuthorClauseNode` | Immutable carrier for the AUTHOR value |
| `InstallationClauseNode` | Immutable carrier for INSTALLATION value |
| `DateWrittenClauseNode` | Immutable carrier for DATE-WRITTEN value |
| `DateCompiledClauseNode` | Immutable carrier for DATE-COMPILED value |
| `SecurityClauseNode` | Immutable carrier for SECURITY value |

---

## Recursive Descent Design

### Division Detection

`ProgramParser._is_identification_division()` peeks at the current and
next token **without consuming** either one.  This two-token lookahead is
sufficient to confirm the presence of `IDENTIFICATION DIVISION`:

```python
def _is_identification_division(state: ParserState) -> bool:
    tok = state.stream.current()
    if tok.type is not TokenType.KEYWORD:
        return False
    if tok.lexeme.upper() != "IDENTIFICATION":
        return False
    next_tok = state.stream.peek()
    return (
        next_tok.type is TokenType.KEYWORD
        and next_tok.lexeme.upper() == "DIVISION"
    )
```

### Header Parsing

```python
# IDENTIFICATION DIVISION .
_expect_keyword(stream.advance(), "IDENTIFICATION")
_expect_keyword(stream.advance(), "DIVISION")
stream.expect(TokenType.PERIOD)
```

### Clause Dispatch Loop

After the header the parser enters a loop that inspects the current token:

```
while not stream.eof():
    if next token is a division header  → stop (next division detected)
    if next token is not KEYWORD        → raise ParserError
    if keyword not in known clauses     → raise ParserError
    dispatch to clause-specific method
```

### Clause Parsing Pattern

All optional comment-entry clauses follow the same pattern:

```
KEYWORD . <value-tokens> .
```

The shared `_parse_comment_clause()` method handles this:

```python
stream.advance()          # consume keyword
stream.expect(PERIOD)     # consume .
# collect tokens until PERIOD (or next keyword)
stream.expect(PERIOD)     # consume closing .
```

---

## AST Nodes

### Hierarchy

```
ASTNode (abstract)
└── IdentificationDivisionNode
    ├── ProgramIdClauseNode
    ├── AuthorClauseNode
    ├── InstallationClauseNode
    ├── DateWrittenClauseNode
    ├── DateCompiledClauseNode
    └── SecurityClauseNode
```

All nodes are **frozen dataclasses** (`@dataclass(frozen=True)`):

- Immutable after construction — safe to share across passes.
- Hashable — can be stored in sets or used as dict keys.
- Comparable by value — equality works without custom `__eq__`.

### `IdentificationDivisionNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `IDENTIFICATION` keyword |
| `end_position` | `Position` | Position of the last consumed token |
| `program_id` | `ProgramIdClauseNode \| None` | PROGRAM-ID clause |
| `author` | `AuthorClauseNode \| None` | AUTHOR clause |
| `installation` | `InstallationClauseNode \| None` | INSTALLATION clause |
| `date_written` | `DateWrittenClauseNode \| None` | DATE-WRITTEN clause |
| `date_compiled` | `DateCompiledClauseNode \| None` | DATE-COMPILED clause |
| `security` | `SecurityClauseNode \| None` | SECURITY clause |

### Clause Node Fields

Each clause node inherits `start_position` and `end_position` from
`ASTNode` and adds a single `value: str` field holding the raw parsed text.

---

## Visitor Integration

The clause nodes and `IdentificationDivisionNode` use **getattr-based
dispatch** in `accept()`:

```python
def accept(self, visitor: object) -> object:
    visit = getattr(visitor, "visit_identification_division", None)
    if callable(visit):
        return visit(self)
    return None
```

This means existing `ASTVisitor` subclasses continue to work without
modification — they simply won't receive `visit_identification_division`
calls unless they override that method.

To handle the new nodes, subclass `ASTVisitor` and add methods:

```python
class IdentificationCollector(ASTVisitor):
    def visit_identification_division(
        self, node: IdentificationDivisionNode
    ) -> None:
        if node.program_id:
            print(f"Program: {node.program_id.value}")

    def visit_program_id_clause(self, node: ProgramIdClauseNode) -> None:
        ...
```

---

## Error Handling

All parse errors raise `ParserError` from
`app.parser.syntax.parser_exceptions`.

| Condition | Error Message |
|-----------|---------------|
| Wrong second keyword | `expected 'DIVISION', got <actual>` |
| Missing period after header | `UnexpectedEOFError` / `UnexpectedTokenError` |
| Missing program name | `expected program name after PROGRAM-ID.` |
| Unknown clause keyword | `unknown IDENTIFICATION DIVISION clause: <kw>` |
| Non-keyword in clause position | `expected a clause keyword, got <lexeme>` |
| Missing clause closing period | `missing period after <CLAUSE> value` |

---

## Future Extensions

The following division parsers will be added in subsequent tasks:

```
ProgramParser._parse_program()
├── _is_identification_division()  → IdentificationDivisionParser  ← (this task)
├── _is_environment_division()     → EnvironmentDivisionParser      (future)
├── _is_data_division()            → DataDivisionParser             (future)
└── _is_procedure_division()       → ProcedureDivisionParser        (future)
```

The `ProgramNode.identification_division` field type will be updated from
`DivisionNode | None` to `IdentificationDivisionNode | None` in a follow-up
refactoring task.
