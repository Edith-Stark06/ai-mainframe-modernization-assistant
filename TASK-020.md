# TASK-020 — Reference Resolution Visitor

## Objective

Implement the second semantic analysis pass that resolves identifier references against the populated symbol table.

This pass verifies that every referenced symbol has been declared and records semantic diagnostics for unresolved references.

---

## Background

Task-018 established the semantic analysis infrastructure.

Task-019 implemented declaration collection into the SemanticContext symbol table.

This task introduces reference resolution, allowing the compiler to validate identifier usage independently of parsing.

---

## Scope

Implement a `ReferenceResolverVisitor` that traverses the AST and resolves references to symbols collected during the symbol collection pass.

Initially support resolution of:

- Variables
- Paragraph references
- Section references (if represented in the AST)

---

## Functional Requirements

### 1. ReferenceResolverVisitor

Create:

app/parser/semantic/reference_resolver.py

Responsibilities:

- Traverse the AST
- Resolve identifier references
- Query the SymbolTable
- Record semantic diagnostics for unresolved references
- Continue traversal after errors

---

### 2. SemanticAnalyzer Integration

Update `SemanticAnalyzer` to execute semantic passes in order:

1. SymbolCollectorVisitor
2. ReferenceResolverVisitor

The populated SemanticContext should be shared between passes.

---

### 3. Name Resolution

For every identifier reference:

- Search the appropriate symbol scope
- Associate the AST node with the resolved symbol (where supported)
- Produce diagnostics if resolution fails

---

### 4. Diagnostics

Emit structured diagnostics for:

- Undefined variable
- Undefined paragraph
- Undefined section

Diagnostics should include:

- Identifier name
- Source location
- Diagnostic code
- Helpful message

---

### 5. Extensibility

Design the resolver so future work can introduce:

- Nested scopes
- Qualified names
- COPYBOOK symbols
- External program references

without redesigning the visitor.

---

## Testing

Add tests covering:

- Successful variable resolution
- Successful paragraph resolution
- Successful section resolution (if applicable)
- Undefined variable
- Undefined paragraph
- Multiple references
- Empty program
- Large representative AST

All existing semantic tests must continue to pass.

---

## Documentation

Update:

docs/architecture/semantic-analyzer.md

Document:

- Multi-pass semantic pipeline
- Reference resolution responsibilities
- Interaction with SymbolCollectorVisitor

---

## Acceptance Criteria

- Identifier references resolve correctly
- Undefined references generate diagnostics
- SemanticAnalyzer executes passes in the correct order
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Type checking
- Scope hierarchy beyond current symbol table
- Constant evaluation
- Data flow analysis
- Control flow analysis