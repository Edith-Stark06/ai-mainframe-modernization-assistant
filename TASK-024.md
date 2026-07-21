# TASK-024 — Intermediate Representation (IR) Foundation

## Objective

Establish the Intermediate Representation (IR) architecture for the compiler.

This task introduces the core IR model, separate from both the parser AST and Java code generation. It does not yet translate COBOL programs; it creates the infrastructure that later passes will populate.

---

## Background

The semantic analysis phase is now complete. The compiler requires a language-independent representation before generating Java or Spring Boot applications.

The IR should model executable program structure while remaining independent of COBOL syntax.

---

## Scope

Implement the IR foundation including:

- IR node hierarchy
- IR program model
- IR module
- IR function
- IR basic block
- IR instruction base classes

No AST translation is required in this task.

---

## Functional Requirements

### 1. IR Package

Create:

```
app/ir/
```

Suggested structure:

```
app/ir/
├── __init__.py
├── nodes.py
├── program.py
├── instructions.py
├── blocks.py
├── visitors.py
└── builder.py
```

---

### 2. Core IR Model

Implement immutable IR dataclasses for:

- IRNode
- IRProgram
- IRModule
- IRFunction
- IRBasicBlock

Each node should support future visitor traversal.

---

### 3. Instruction Hierarchy

Implement abstract instruction types:

- IRInstruction
- IRAssignment
- IRMove
- IRCall
- IRReturn
- IRBranch

These are structural only—no translation logic yet.

---

### 4. Visitor Infrastructure

Create an IR visitor framework that supports traversal without embedding behavior in IR nodes.

---

### 5. Builder Placeholder

Implement an `IRBuilder` class that accepts a validated semantic context and exposes a public interface for future AST-to-IR translation.

Translation logic is intentionally out of scope.

---

## Testing

Add tests covering:

- IR node construction
- Dataclass immutability
- Visitor traversal
- Instruction hierarchy
- IRBuilder initialization

---

## Documentation

Create:

```
docs/architecture/intermediate-representation.md
```

Describe:

- Purpose of the IR
- Separation from AST
- Relationship to semantic analysis
- Planned role in Java generation

---

## Acceptance Criteria

- IR package created
- Immutable IR model implemented
- Visitor framework established
- Builder scaffold created
- Tests pass
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- AST-to-IR translation
- Optimizations
- SSA
- Control-flow graph construction
- Java generation