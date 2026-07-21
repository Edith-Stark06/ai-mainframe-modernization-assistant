# TASK-021 — Semantic Validation Visitor

## Objective

Implement the third semantic analysis pass that validates COBOL semantic rules after symbol collection and reference resolution.

This pass enforces semantic correctness while producing structured diagnostics and allowing compilation to continue after errors.

---

## Background

The compiler currently performs:

1. Symbol collection
2. Reference resolution

This task adds semantic validation rules that operate on resolved symbols.

---

## Scope

Implement a `SemanticValidationVisitor` that traverses the AST and validates COBOL semantic constraints.

Initially support:

- Duplicate PROGRAM-ID declarations
- Empty Procedure Division detection
- Invalid paragraph placement
- Invalid section ordering (where represented)
- Reserved-word misuse as identifiers
- Invalid CALL target (when statically known)

Validation should emit diagnostics without stopping traversal.

---

## Functional Requirements

### 1. SemanticValidationVisitor

Create:

app/parser/semantic/validation.py

Responsibilities:

- Traverse the AST
- Validate semantic rules
- Emit diagnostics
- Continue after errors

---

### 2. SemanticAnalyzer Integration

Execute semantic passes in this order:

1. SymbolCollectorVisitor
2. ReferenceResolverVisitor
3. SemanticValidationVisitor

All passes share the same SemanticContext.

---

### 3. Validation Rules

Implement checks for:

- Duplicate PROGRAM-ID
- Empty Procedure Division
- Reserved keyword used as an identifier
- Paragraph declared outside Procedure Division (if representable)
- Invalid static CALL target

Design the visitor so new rules can be added independently.

---

### 4. Diagnostics

Emit structured diagnostics containing:

- Diagnostic code
- Severity
- Source location
- Helpful message

Use the existing diagnostics infrastructure.

---

## Testing

Add tests covering:

- Valid programs
- Duplicate PROGRAM-ID
- Empty Procedure Division
- Reserved identifier
- Invalid CALL target
- Multiple validation errors in one program
- Integration with previous semantic passes

---

## Documentation

Update:

docs/architecture/semantic-analyzer.md

Document:

- Validation pass
- Semantic pipeline
- Validation rule categories

---

## Acceptance Criteria

- Validation visitor executes after reference resolution
- Semantic diagnostics are produced correctly
- Traversal continues after errors
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Data type checking
- Numeric compatibility
- Constant folding
- Control-flow analysis
- Optimization