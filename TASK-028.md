# TASK-028 — IR Translation for Arithmetic Statements

## Objective

Extend the AST-to-IR translation pipeline to translate COBOL arithmetic statements into Intermediate Representation instructions.

This task introduces computational IR instructions while preserving the existing separation between semantic analysis, IR generation, and backend code generation.

---

## Background

The compiler currently supports:

- Lexer
- Parser
- AST
- Semantic Analysis
- IR Foundation
- Structural AST-to-IR Translation
- MOVE Translation
- DISPLAY Translation
- ACCEPT Translation

Task-028 introduces executable arithmetic operations into the IR.

---

## Scope

Translate supported COBOL arithmetic statements into IR instructions.

Initially support:

- ADD
- SUBTRACT
- MULTIPLY
- DIVIDE

Only straightforward forms represented by the current AST need to be handled.

---

## Functional Requirements

### 1. Extend IR Instruction Hierarchy

Add instruction types:

- IRAdd
- IRSubtract
- IRMultiply
- IRDivide

All should inherit from `IRInstruction`.

---

### 2. Extend IRBuilder

Modify:

```
app/ir/builder.py
```

Translate supported arithmetic statements into their corresponding IR instructions.

Append generated instructions to the active basic block.

---

### 3. Operand Translation

Reuse the existing operand translation helpers.

Support:

- Variable references
- Numeric literals

Do not duplicate operand construction logic.

---

### 4. Semantic Integration

Use the validated `SemanticContext`.

Assume semantic type checking has already guaranteed numeric compatibility.

Do not repeat semantic validation during IR generation.

---

### 5. Temporary Extensibility

Design the instruction model so future support for:

- expression trees
- temporary values
- constant folding
- optimization passes

can be added without redesign.

---

### 6. Diagnostics

Produce structured IR translation diagnostics for:

- unsupported arithmetic variants
- incomplete operands
- unsupported AST forms

Continue translation where possible.

---

## Testing

Add tests covering:

- ADD
- SUBTRACT
- MULTIPLY
- DIVIDE
- multiple arithmetic statements
- mixed MOVE/DISPLAY/arithmetic ordering
- deterministic IR generation

---

## Documentation

Update:

```
docs/architecture/intermediate-representation.md
```

Describe:

- arithmetic lowering
- instruction hierarchy
- operand reuse
- future optimization compatibility

---

## Acceptance Criteria

- Arithmetic statements generate correct IR instructions
- Instructions appear in program order
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- IF
- PERFORM
- GO TO
- CALL
- Optimizations
- SSA
- Constant folding