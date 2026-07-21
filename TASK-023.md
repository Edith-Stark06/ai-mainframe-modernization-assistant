# TASK-023 — Semantic Type Checking

## Objective

Implement the first semantic type-checking pass for COBOL programs.

This pass validates that statements operate on compatible data types using the semantic type information built during Task-022.

The implementation should produce diagnostics while allowing analysis to continue.

---

## Background

The semantic pipeline currently performs:

1. Symbol collection
2. Reference resolution
3. Semantic validation
4. Type building

Task-023 introduces semantic type checking using the previously constructed semantic type model.

---

## Scope

Implement a `TypeCheckerVisitor` responsible for validating type compatibility in COBOL statements.

Initially support:

- MOVE statements
- DISPLAY statements
- ACCEPT statements (where represented)
- Simple arithmetic statements (if represented)

---

## Functional Requirements

### 1. TypeCheckerVisitor

Create:

app/parser/semantic/type_checker.py

Responsibilities:

- Traverse the AST
- Inspect resolved symbols
- Compare semantic types
- Emit diagnostics for incompatible operations
- Continue after errors

---

### 2. SemanticAnalyzer Integration

Execute semantic passes in this order:

1. SymbolCollectorVisitor
2. ReferenceResolverVisitor
3. SemanticValidationVisitor
4. TypeBuilder
5. TypeCheckerVisitor

---

### 3. Compatibility Rules

Implement initial rules for:

MOVE

- numeric → numeric
- alphanumeric → alphanumeric
- numeric → alphanumeric (allowed)
- alphanumeric → numeric (diagnostic)

DISPLAY

- any built semantic type is valid

ACCEPT

- destination must exist
- destination must have semantic type

Arithmetic

- operands must be numeric

---

### 4. Diagnostics

Add structured diagnostics for:

- incompatible MOVE
- invalid arithmetic operand
- missing semantic type
- unsupported operation

Diagnostics should include:

- code
- severity
- location
- message

---

### 5. Extensibility

Design compatibility logic so future rules can support:

- edited PIC clauses
- NATIONAL
- UTF-8
- floating-point
- decimal scaling
- OCCURS items

without redesign.

---

## Testing

Add tests covering:

- valid MOVE
- invalid MOVE
- numeric assignments
- DISPLAY
- arithmetic compatibility
- representative COBOL programs
- multiple diagnostics in one program

---

## Documentation

Update:

docs/architecture/semantic-analyzer.md

Describe:

- TypeCheckerVisitor
- compatibility rules
- semantic pipeline

---

## Acceptance Criteria

- Type checker executes after TypeBuilder
- Diagnostics emitted correctly
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- implicit conversions
- storage layout
- optimization
- constant folding
- code generation