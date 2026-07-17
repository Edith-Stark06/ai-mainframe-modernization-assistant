# TASK-016 — COBOL Procedure Division Parser

## Objective

Extend the COBOL recursive-descent parser to support the PROCEDURE DIVISION by implementing a dedicated ProcedureDivisionParser, integrating it into ProgramParser, adding parser tests, and documenting the parser architecture.

The parser should construct an AST representing paragraphs and a limited subset of executable statements while preserving the project's existing parser architecture.

---

## Background

The parser currently supports:

- Source Reader
- Format Detection
- Source Normalization
- Character Scanner
- Lexer
- AST Foundation
- Parser Framework
- Identification Division Parser
- Data Division Parser

This task introduces parsing of executable COBOL code.

---

## Scope

### Implement

- PROCEDURE DIVISION recognition
- Paragraph parsing
- Basic statement parsing
- Procedure Division AST
- ProgramParser integration
- Parser tests
- Architecture documentation

---

## Supported Grammar

Support parsing:

```cobol
PROCEDURE DIVISION.

MAIN-PARA.

DISPLAY "HELLO".

MOVE 1 TO WS-COUNT.

STOP RUN.
```

Support statements:

- DISPLAY
- MOVE
- STOP RUN
- GOBACK

Support paragraph labels:

```cobol
MAIN-PARA.
```

---

## Out of Scope

Do NOT implement:

- IF
- EVALUATE
- PERFORM
- GO TO
- CALL
- COMPUTE
- ADD
- SUBTRACT
- MULTIPLY
- DIVIDE
- STRING
- UNSTRING
- SEARCH
- INSPECT
- DECLARATIVES
- SECTION headers
- Nested programs
- COPY expansion
- Semantic analysis

---

## Files to Create

### AST

```
app/parser/ast/
    procedure.py
    paragraphs.py
    statements.py
```

### Syntax

```
app/parser/syntax/
    procedure_parser.py
```

### Tests

```
tests/parser/
    test_procedure_parser.py
```

### Documentation

```
docs/architecture/
    procedure-parser.md
```

---

## Files to Modify

```
app/parser/syntax/program_parser.py

app/parser/ast/program.py
```

---

## AST Requirements

Implement immutable dataclasses representing:

```
ProgramNode
│
├── IdentificationDivisionNode
├── DataDivisionNode
└── ProcedureDivisionNode
        │
        ├── ParagraphNode
        │      └── StatementNode
        │
        └── ...
```

Statement hierarchy should initially include:

- DisplayStatementNode
- MoveStatementNode
- StopRunStatementNode
- GobackStatementNode

---

## Parser Responsibilities

Implement ProcedureDivisionParser.

Responsibilities:

- Parse PROCEDURE DIVISION.
- Parse paragraph labels.
- Parse supported statements.
- Construct the ProcedureDivision AST.
- Return a ProcedureDivisionNode.

ProgramParser must remain an orchestrator and delegate PROCEDURE DIVISION parsing.

---

## Tests

Create comprehensive pytest coverage including:

- Empty PROCEDURE DIVISION
- Single paragraph
- Multiple paragraphs
- DISPLAY statement
- MOVE statement
- STOP RUN
- GOBACK
- Multiple statements
- Invalid statement
- Missing terminating period
- ProgramParser integration
- AST immutability
- Visitor dispatch

---

## Documentation

Create:

```
docs/architecture/procedure-parser.md
```

Document:

- Responsibilities
- Parser flow
- AST hierarchy
- Supported grammar
- Unsupported grammar
- Future enhancements

---

## Quality Gates

The implementation must pass:

- Ruff
- Black
- MyPy
- Pytest

No regression in existing functionality.

---

## Acceptance Criteria

- ProcedureDivisionNode implemented
- ParagraphNode implemented
- Statement nodes implemented
- ProcedureDivisionParser implemented
- ProgramParser delegates PROCEDURE DIVISION parsing
- Tests passing
- Documentation completed