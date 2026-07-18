# TASK-017 — Parser Error Recovery

## Objective

Enhance the COBOL recursive-descent parser with robust error recovery, allowing it to continue parsing after encountering syntax errors. This enables multiple syntax errors to be reported in a single parse instead of terminating at the first failure.

The parser should preserve the existing AST whenever possible while collecting diagnostics.

---

## Background

The parser currently supports:

- Identification Division
- Data Division
- Procedure Division

Parsing currently stops on the first unrecoverable syntax error.

This task introduces parser recovery strategies and diagnostic collection.

---

## Scope

### Implement

- Parser synchronization
- Error recovery
- Diagnostic collection
- Recovery helper utilities
- Parser recovery tests
- Architecture documentation

---

## Recovery Strategy

Implement panic-mode recovery.

After detecting a syntax error, synchronize to one of the following recovery points:

- Period (`.`)
- DIVISION keyword
- SECTION keyword
- Paragraph label
- EOF

Once synchronized, continue parsing.

---

## ParserState

Extend ParserState to support:

- collected diagnostics
- recovery mode
- synchronization helpers

---

## Diagnostics

Implement recovery utilities responsible for:

- recording syntax errors
- recording recovery location
- exposing diagnostics

---

## Parser Responsibilities

Update:

- IdentificationDivisionParser
- DataDivisionParser
- ProcedureDivisionParser

to recover rather than immediately abort whenever possible.

Fatal parser state should still raise ParserError.

---

## Out of Scope

Do NOT implement:

- Semantic diagnostics
- Warning diagnostics
- Type checking
- Symbol resolution
- Automatic source correction
- IDE integration

---

## Files to Create

```
app/parser/diagnostics/
    recovery.py

tests/parser/
    test_parser_recovery.py

docs/architecture/
    parser-error-recovery.md
```

---

## Files to Modify

```
app/parser/syntax/parser.py
app/parser/syntax/parser_state.py
app/parser/syntax/parser_errors.py
app/parser/syntax/parser_exceptions.py
app/parser/syntax/identification_parser.py
app/parser/syntax/data_parser.py
app/parser/syntax/procedure_parser.py
```

---

## Tests

Create tests covering:

- Missing period
- Unexpected keyword
- Invalid level number
- Invalid statement
- Multiple syntax errors
- Recovery after paragraph
- Recovery after division
- EOF recovery
- Diagnostics collection
- ParserState recovery mode

---

## Documentation

Create:

```
docs/architecture/parser-error-recovery.md
```

Include:

- Panic-mode recovery
- Synchronization tokens
- Parser flow
- Diagnostic model
- Future enhancements

---

## Quality Gates

Implementation must pass:

- Ruff
- Black
- MyPy
- Pytest

No regression in existing parser functionality.

---

## Acceptance Criteria

- Parser continues after recoverable errors
- Multiple diagnostics collected
- Synchronization implemented
- Tests passing
- Documentation completed