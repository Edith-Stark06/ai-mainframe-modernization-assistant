# TASK-029 — IR Translation for Control Flow Statements

## Objective

Extend the AST-to-IR translation pipeline to translate COBOL control flow statements into Intermediate Representation.

This task introduces branching and control flow into the IR by translating supported IF, PERFORM, and GO TO statements into interconnected basic blocks.

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
- Arithmetic Translation

Task-029 introduces control-flow graph construction.

---

## Scope

Translate supported:

- IF
- PERFORM
- GO TO

statements into IR control-flow instructions and multiple basic blocks.

Only the AST forms currently supported by the parser need to be handled.

---

## Functional Requirements

### 1. Extend IR Instruction Hierarchy

Add:

- IRConditionalBranch
- IRJump

Reuse IRReturn where appropriate.

---

### 2. Basic Block Management

Extend IRBuilder to create and connect basic blocks.

Support:

- Entry block
- Then block
- Else block (when present)
- Continuation block

Every generated block must have a unique identifier.

---

### 3. IF Translation

Translate:

```
IF condition
    statements
END-IF
```

into:

```
entry
  │
  ▼
IRConditionalBranch
 ├──► then
 └──► merge
```

Translate IF/ELSE similarly:

```
entry
  │
  ▼
IRConditionalBranch
 ├──► then
 └──► else

then ──► merge
else ──► merge
```

---

### 4. PERFORM Translation

Support the currently represented AST forms.

Generate:

- IRJump
- additional basic blocks

as needed.

---

### 5. GO TO Translation

Generate unconditional jumps between blocks using IRJump.

---

### 6. Semantic Integration

Consume resolved semantic information.

Do not perform semantic validation during IR generation.

---

### 7. Diagnostics

Produce structured diagnostics for:

- unsupported control-flow variants
- incomplete IF nodes
- unresolved targets
- unsupported PERFORM forms

Continue translation where possible.

---

## Testing

Add tests covering:

- IF without ELSE
- IF with ELSE
- nested IF
- PERFORM
- GO TO
- multiple connected blocks
- deterministic block generation

---

## Documentation

Update:

docs/architecture/intermediate-representation.md

Document:

- control-flow graph
- basic-block construction
- branch instructions
- block connectivity

---

## Acceptance Criteria

- IF generates multiple connected basic blocks
- PERFORM translated
- GO TO translated
- Branch instructions generated correctly
- Existing tests remain green
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Optimization
- SSA
- Dead-code elimination
- Loop optimization
- Java generation