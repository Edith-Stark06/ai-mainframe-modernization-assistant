# TASK-015 — COBOL Data Division Parser

## Objective

Extend the COBOL recursive-descent parser to support the **DATA DIVISION** by implementing a dedicated DataDivisionParser, integrating it into ProgramParser, adding parser tests, and documenting the architecture.

> **Note:** The AST foundation (`data.py`, `working_storage.py`, and `data_items.py`) already exists and should be used. Do not recreate or replace those files.

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

This task extends the parser to recognize COBOL data definitions.

---

## Existing AST

The following files already exist:

```
app/parser/ast/
    data.py
    working_storage.py
    data_items.py
```

Use these existing AST nodes. Only modify them if required for correctness or integration.

---

## Scope

### Implement

- DataDivisionParser
- DATA DIVISION parsing
- WORKING-STORAGE SECTION parsing
- Basic data item parsing
- ProgramParser integration
- Parser tests
- Architecture documentation

---

## Supported Grammar

Support parsing:

```cobol
DATA DIVISION.

WORKING-STORAGE SECTION.

01 CUSTOMER-REC.
   05 CUSTOMER-ID     PIC 9(5).
   05 CUSTOMER-NAME   PIC X(30).

77 WS-COUNT           PIC 9(4).

88 END-OF-FILE        VALUE 'Y'.
```

Supported level numbers:

- 01
- 05
- 77
- 88

Support:

- PIC clause
- Simple VALUE clause (88-level conditions)

---

## Out of Scope

Do NOT implement:

- FILE SECTION
- LINKAGE SECTION
- LOCAL-STORAGE
- SCREEN SECTION
- REPORT SECTION
- OCCURS
- REDEFINES
- COMP
- COMP-3
- RENAMES (66)
- INDEXED BY
- JUSTIFIED
- SYNCHRONIZED
- COPY expansion
- Semantic analysis

---

## Files to Create

```
app/parser/syntax/
    data_parser.py

tests/parser/
    test_data_parser.py

docs/architecture/
    data-parser.md
```

---

## Files to Modify

```
app/parser/syntax/program_parser.py

app/parser/ast/program.py
```

Modify the existing AST files only if additional fields or helper methods are required.

---

## Parser Responsibilities

Implement a dedicated `DataDivisionParser`.

Responsibilities:

- Parse DATA DIVISION
- Parse WORKING-STORAGE SECTION
- Parse supported data declarations
- Construct the existing AST nodes
- Return a DataDivisionNode

ProgramParser should delegate DATA DIVISION parsing to this parser.

---

## Tests

Create comprehensive parser tests covering:

- Empty DATA DIVISION
- Empty WORKING-STORAGE SECTION
- Single 01 declaration
- Nested 01/05 declarations
- 77-level declaration
- 88-level condition
- Missing terminating period
- Invalid level number

---

## Documentation

Create:

```
docs/architecture/data-parser.md
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

All must pass:

- Ruff
- Black
- MyPy
- Pytest

No regression in existing parser functionality.

---

## Acceptance Criteria

- Existing AST integrated successfully
- DataDivisionParser implemented
- ProgramParser delegates DATA DIVISION parsing
- DataDivisionNode populated correctly
- Tests passing
- Documentation completed