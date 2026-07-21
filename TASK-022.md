# TASK-022 — COBOL Data Type Model

## Objective

Introduce a COBOL semantic type system that models Data Division declarations and associates type information with variable symbols.

This task establishes the foundation for future type checking, IR generation, storage layout, and Java type mapping.

---

## Background

The semantic analyzer currently:

- Collects symbols
- Resolves references
- Performs semantic validation

However, variables currently lack semantic type information.

Task-022 introduces a semantic type model independent of the parser.

---

## Scope

Implement semantic representations for COBOL data types.

Support:

- PIC clauses
- Level numbers
- USAGE clause
- DISPLAY usage
- COMP usage
- COMP-3 usage
- Alphanumeric types
- Numeric types

The parser AST should remain unchanged.

---

## Functional Requirements

### 1. Type Model

Create:

app/parser/semantic/types.py

Implement semantic type classes including:

- CobolType
- NumericType
- AlphanumericType
- GroupType
- UsageType (enum)

Design for future extension.

---

### 2. Variable Symbol Enhancement

Extend VariableSymbol to include:

- semantic type
- PIC string
- usage
- level number
- signed flag
- length metadata

---

### 3. Type Builder

Create:

app/parser/semantic/type_builder.py

Responsibilities:

- Traverse Data Division declarations
- Interpret PIC clauses
- Build semantic type objects
- Attach types to VariableSymbols

---

### 4. Semantic Analyzer

Update SemanticAnalyzer execution order:

1. SymbolCollectorVisitor
2. ReferenceResolverVisitor
3. SemanticValidationVisitor
4. TypeBuilder

---

### 5. Extensibility

Design the model for future support of:

- OCCURS
- REDEFINES
- INDEXED BY
- RENAMES
- POINTER
- NATIONAL
- UTF-8

without redesigning the hierarchy.

---

## Testing

Add tests covering:

- PIC X
- PIC 9
- PIC S9
- COMP
- COMP-3
- Group items
- Mixed declarations
- Type attachment to symbols

---

## Documentation

Update:

docs/architecture/semantic-analyzer.md

Describe:

- Semantic type system
- Type builder pass
- Relationship between parser AST and semantic types

---

## Acceptance Criteria

- Semantic type hierarchy implemented
- Variable symbols receive semantic types
- Existing tests continue to pass
- New tests added
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Type compatibility rules
- Expression typing
- Arithmetic validation
- Storage offset calculation
- Java type mapping