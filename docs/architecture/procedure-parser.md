# Procedure Division Parser Architecture

## Overview

This document describes the design of the COBOL PROCEDURE DIVISION
parser — the third grammar-aware division parser in the pipeline.

The Procedure Division parser transforms a flat token stream into an
immutable `ProcedureDivisionNode` containing an ordered tuple of
`ParagraphNode` instances, each of which holds an ordered tuple of
`StatementNode` instances.

---

## Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `ProgramParser` | Top-level coordinator; detects PROCEDURE DIVISION via two-token lookahead and delegates |
| `ProcedureDivisionParser` | Parses header + paragraphs + supported statements; raises `ParserError` on errors |
| `ProcedureDivisionNode` | Immutable root container for the division |
| `ParagraphNode` | Immutable container for a named paragraph and its statements |
| `DisplayStatementNode` | Immutable carrier for a `DISPLAY` statement |
| `MoveStatementNode` | Immutable carrier for a `MOVE ... TO ...` statement |
| `StopRunStatementNode` | Immutable carrier for a `STOP RUN` statement |
| `GobackStatementNode` | Immutable carrier for a `GOBACK` statement |

---

## Supported Grammar

```
PROCEDURE DIVISION.

paragraph-label.
    DISPLAY operand.
    MOVE source TO target.
    STOP RUN.
    GOBACK.

paragraph-label.
    ...
```

### Supported Statements

| Statement | Grammar Rule |
|-----------|-------------|
| `DISPLAY` | `DISPLAY operand .` |
| `MOVE` | `MOVE source TO target .` |
| `STOP RUN` | `STOP RUN .` |
| `GOBACK` | `GOBACK .` |

---

## Unsupported Grammar (Out of Scope)

| Construct | Reason |
|-----------|--------|
| `IF` / `EVALUATE` | Future milestone |
| `PERFORM` | Future milestone |
| `GO TO` | Future milestone |
| `CALL` | Future milestone |
| `COMPUTE` | Future milestone |
| Arithmetic verbs (`ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE`) | Future milestone |
| `STRING` / `UNSTRING` | Future milestone |
| `SEARCH` / `INSPECT` | Future milestone |
| `SECTION` headers | Future milestone |
| `DECLARATIVES` | Future milestone |
| Nested programs | Future milestone |
| `COPY` expansion | Resolver layer (future) |
| Semantic analysis | Semantic layer (future) |

---

## Lexer Notes

The COBOL lexer emits tokens as either `KEYWORD` or `IDENTIFIER` based
on the registered keyword set.  Two keywords used in the PROCEDURE
DIVISION are **not** registered in the current keyword set and are
therefore emitted as `IDENTIFIER` tokens:

| Token | Emitted As | Reason |
|-------|-----------|--------|
| `GOBACK` | `IDENTIFIER` | Not in keyword set |
| `TO` | `IDENTIFIER` | Not in keyword set |

The parser handles both transparently by comparing uppercased `lexeme`
values regardless of token type.

---

## Parser Flow

```
ProgramParser.parse(tokens)
      |
      |  _is_procedure_division(): two-token lookahead (PROCEDURE DIVISION)
      |
      v
ProcedureDivisionParser.parse(state)
      |
      |  consume: PROCEDURE DIVISION .
      |
      +── _parse_paragraphs(state)
            |
            while current is IDENTIFIER/KEYWORD followed by PERIOD
            (and not a statement lexeme):
            |
            +── _parse_paragraph(state)
                  |
                  consume: label .
                  |
                  +── _parse_statements(state)
                        |
                        while current is a statement lexeme:
                        |
                        +── _parse_statement(state)
                              |
                     ┌────────┴──────────────────────────────────┐
                     │ DISPLAY   │ MOVE      │ STOP RUN │ GOBACK  │
                     ▼           ▼           ▼          ▼
               _parse_display  _parse_move  _parse_stop_run  _parse_goback
                     │           │           │               │
                     ▼           ▼           ▼               ▼
               DisplayStatement MoveStatement StopRun Goback
               Node             Node          Node    Node
```

---

## Division Detection

`ProgramParser._is_procedure_division()` peeks at the current and
next token **without consuming** either one:

```python
def _is_procedure_division(state: ParserState) -> bool:
    tok = state.stream.current()
    if tok.type is not TokenType.KEYWORD:
        return False
    if tok.lexeme.upper() != "PROCEDURE":
        return False
    next_tok = state.stream.peek()
    return (
        next_tok.type is TokenType.KEYWORD
        and next_tok.lexeme.upper() == "DIVISION"
    )
```

---

## Paragraph Detection

A paragraph label is detected by the lookahead pattern:

```
current: IDENTIFIER or KEYWORD
next:    PERIOD
```

**and** the current token lexeme is **not** in the set of statement
lexemes (`DISPLAY`, `MOVE`, `STOP`, `GOBACK`).  This distinguishes
a paragraph label from a statement that ends with a period.

---

## AST Hierarchy

```
ASTNode (abstract)
└── ProcedureDivisionNode
      └── paragraphs: tuple[ParagraphNode, ...]
            └── ParagraphNode
                  ├── name: str
                  └── statements: tuple[StatementNode, ...]
                        ├── DisplayStatementNode
                        │     └── operand: str
                        ├── MoveStatementNode
                        │     ├── source: str
                        │     └── target: str
                        ├── StopRunStatementNode
                        └── GobackStatementNode
```

All nodes are **frozen dataclasses** (`@dataclass(frozen=True)`):

- Immutable after construction — safe to share across analysis passes.
- Hashable — can be stored in sets or used as dict keys.
- Comparable by value — equality works without a custom `__eq__`.

### `ProcedureDivisionNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `PROCEDURE` keyword |
| `end_position` | `Position` | Position of the last consumed token |
| `paragraphs` | `tuple[ParagraphNode, ...]` | Ordered paragraphs |

### `ParagraphNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the paragraph label token |
| `end_position` | `Position` | Position of the last token consumed |
| `name` | `str` | Paragraph label (uppercased) |
| `statements` | `tuple[StatementNode, ...]` | Ordered statements |

### `DisplayStatementNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `DISPLAY` keyword |
| `end_position` | `Position` | Position of the terminating period |
| `operand` | `str` | Operand tokens joined with a space |

### `MoveStatementNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `MOVE` keyword |
| `end_position` | `Position` | Position of the terminating period |
| `source` | `str` | Source operand tokens joined with a space |
| `target` | `str` | Target operand tokens joined with a space |

### `StopRunStatementNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `STOP` keyword |
| `end_position` | `Position` | Position of the terminating period |

### `GobackStatementNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `GOBACK` token |
| `end_position` | `Position` | Position of the terminating period |

---

## Visitor Integration

All new AST nodes use **getattr-based dispatch** in `accept()`:

```python
def accept(self, visitor: object) -> object:
    visit = getattr(visitor, "visit_procedure_division", None)
    if callable(visit):
        return visit(self)
    return None
```

This preserves backward-compatibility with existing `ASTVisitor` subclasses.

To handle the new nodes, add methods to a visitor subclass:

```python
class ProcedureAnalyser(ASTVisitor):
    def visit_procedure_division(
        self, node: ProcedureDivisionNode
    ) -> None:
        for para in node.paragraphs:
            para.accept(self)

    def visit_paragraph(self, node: ParagraphNode) -> None:
        print(f"Paragraph: {node.name}")
        for stmt in node.statements:
            stmt.accept(self)

    def visit_display_statement(
        self, node: DisplayStatementNode
    ) -> None:
        print(f"  DISPLAY {node.operand}")

    def visit_move_statement(self, node: MoveStatementNode) -> None:
        print(f"  MOVE {node.source} TO {node.target}")

    def visit_stop_run_statement(
        self, node: StopRunStatementNode
    ) -> None:
        print("  STOP RUN")

    def visit_goback_statement(
        self, node: GobackStatementNode
    ) -> None:
        print("  GOBACK")
```

---

## Error Handling

All parse errors raise `ParserError` from
`app.parser.syntax.parser_exceptions`.

| Condition | Error Message |
|-----------|---------------|
| Wrong second keyword (not `DIVISION`) | `expected 'DIVISION', got <actual>` |
| Missing period after `PROCEDURE DIVISION` | `UnexpectedEOFError` / `UnexpectedTokenError` |
| Missing period after paragraph label | `expected '.' after paragraph label '<name>', got <actual>` |
| `STOP` not followed by `RUN` | `expected 'RUN' after STOP, got <actual>` |
| `MOVE` missing source operand | `expected source operand after MOVE` |
| `MOVE` missing `TO` keyword | `expected 'TO' in MOVE statement, got <actual>` |
| `MOVE` missing target operand | `expected target operand after TO in MOVE statement` |
| `DISPLAY` missing operand | `expected operand after DISPLAY` |
| Missing period after any statement | `expected '.' after <context>, got EOF` |

---

## Future Enhancements

```
ProcedureDivisionParser._parse_statements()
├── _parse_display()       ← (this task)
├── _parse_move()          ← (this task)
├── _parse_stop_run()      ← (this task)
├── _parse_goback()        ← (this task)
├── _parse_if()            (future)
├── _parse_evaluate()      (future)
├── _parse_perform()       (future)
├── _parse_go_to()         (future)
├── _parse_call()          (future)
├── _parse_compute()       (future)
└── _parse_arithmetic()    (future)
```

SECTION parsing:

```
ProcedureDivisionParser._parse_sections()   (future)
├── SectionNode
│     └── paragraphs: tuple[ParagraphNode, ...]
```
