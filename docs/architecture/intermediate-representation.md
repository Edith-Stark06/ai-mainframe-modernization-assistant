# Intermediate Representation Architecture

## Overview

The **Intermediate Representation (IR)** is the language-independent program
model that sits between the semantic analysis phase (COBOL AST + semantic
context) and the back-end code generation phase (Java / Spring Boot).

The IR models *program behaviour* — data movement, function calls, control
flow, and return — without any dependency on COBOL syntax or Java class
structure.  This separation means:

* The semantic analyser remains unaware of the target language.
* The code generator is unaware of COBOL.
* Both sides are independently testable and replaceable.

---

## Position in the Compiler Pipeline

```
COBOL Source
      │
      ▼
  Lexer / Parser
      │  (COBOL AST)
      ▼
  Semantic Analyser
      │  (SemanticContext — symbol table, types, diagnostics)
      ▼
  IR Builder  (TASK-024 scaffold; translation in TASK-025+)
      │  (IRProgram)
      ▼
  IR Optimiser  (future)
      │
      ▼
  Java Code Generator  (future)
      │
      ▼
  Java / Spring Boot Output
```

> [!NOTE]
> The `IRBuilder` introduced in TASK-024 is a scaffold. It accepts a
> `SemanticContext` and returns an empty `IRProgram`. Translation logic
> will be added in TASK-025 and later tasks.

---

## Package Structure

```
app/ir/
├── __init__.py       — public API exports
├── nodes.py          — IRNode (abstract base), IRNodeKind enum
├── instructions.py   — instruction hierarchy
├── blocks.py         — IRBasicBlock
├── program.py        — IRProgram, IRModule, IRFunction
├── visitors.py       — IRVisitor base + traverse_ir()
└── builder.py        — IRBuilder scaffold
```

---

## Five-Layer Node Hierarchy

```
IRProgram           — top-level compilation unit
└── IRModule        — logical grouping (→ Java class)
    └── IRFunction  — callable unit (→ Java method)
        └── IRBasicBlock  — straight-line instruction sequence
            └── IRInstruction  — atomic executable operation
```

All nodes are **frozen dataclasses** — immutable and hashable. Downstream
passes produce new nodes rather than mutating existing ones.

### IRNode (nodes.py)

Abstract base for every IR node. Carries:

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `IRNodeKind` | Category tag for fast kind-checking |
| `name` | `str` | Human-readable label for diagnostics |

Subclasses must implement `accept(visitor)` for the Visitor pattern.

### IRNodeKind (nodes.py)

```python
class IRNodeKind(Enum):
    PROGRAM      = "program"
    MODULE       = "module"
    FUNCTION     = "function"
    BASIC_BLOCK  = "basic_block"
    INSTRUCTION  = "instruction"
```

---

## Structural Nodes (program.py)

### IRProgram

Top-level root of every IR tree.

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `modules` | `tuple[IRModule, ...]` | `()` |

`len(program)` → number of modules.

### IRModule

Logical grouping, maps to a Java class in the back-end.

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `functions` | `tuple[IRFunction, ...]` | `()` |

`len(module)` → number of functions.

### IRFunction

Callable unit, maps to a Java method. The first basic block is the entry point.

| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `blocks` | `tuple[IRBasicBlock, ...]` | `()` |
| `params` | `tuple[str, ...]` | `()` |
| `return_type` | `str` | `"void"` |

`len(function)` → number of basic blocks.

---

## IRBasicBlock (blocks.py)

A straight-line sequence of instructions with a single entry (the `label`)
and a single exit (the last instruction, which should be a branch or return).

| Field | Type | Default |
|-------|------|---------|
| `label` | `str` | `""` |
| `instructions` | `tuple[IRInstruction, ...]` | `()` |

`name` is automatically synced to `label` for uniform diagnostics.
`len(block)` → number of instructions.

---

## Instruction Hierarchy (instructions.py)

All instructions are frozen dataclasses. Every instruction has:

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `IRNodeKind` | Always `INSTRUCTION` |
| `result` | `str` | Output operand name (`""` if none) |
| `comment` | `str` | Optional annotation |

### IRAssignment

Assign a literal constant to a named operand.

```python
IRAssignment(result="WS-COUNT", value="0")
```

| Field | Description |
|-------|-------------|
| `value` | Literal string to assign |

### IRMove

Copy one named operand to another.

```python
IRMove(result="WS-TARGET", source="WS-SOURCE")
```

| Field | Description |
|-------|-------------|
| `source` | Source operand name |

### IRCall

Invoke a named function or paragraph.

```python
IRCall(result="RET-VAL", target="PROCESS-RECORD", args=("EMP-ID", "EMP-NAME"))
```

| Field | Description |
|-------|-------------|
| `target` | Function/paragraph name |
| `args` | Positional argument names |

### IRReturn

Terminate the enclosing function.

```python
IRReturn(operand="WS-RESULT")   # return a value
IRReturn()                       # void return
```

| Field | Description |
|-------|-------------|
| `operand` | Operand to return (`""` for void) |

### IRBranch

Transfer control, conditionally or unconditionally.

```python
IRBranch(target="MAIN-EXIT")                       # unconditional
IRBranch(target="EOF-HANDLER", condition="WS-EOF") # conditional
```

| Field | Description |
|-------|-------------|
| `target` | Label to jump to |
| `condition` | Guard operand (`""` = unconditional) |

---

## Visitor Framework (visitors.py)

The IR uses the **Visitor pattern** to separate traversal from behaviour.

### IRVisitor

No-op base class. Override only the hooks your pass needs.

```python
class IRVisitor:
    def visit_program(self, node: IRProgram) -> Any: ...
    def visit_module(self, node: IRModule) -> Any: ...
    def visit_function(self, node: IRFunction) -> Any: ...
    def visit_basic_block(self, node: IRBasicBlock) -> Any: ...
    def visit_assignment(self, node: IRAssignment) -> Any: ...
    def visit_move(self, node: IRMove) -> Any: ...
    def visit_call(self, node: IRCall) -> Any: ...
    def visit_return(self, node: IRReturn) -> Any: ...
    def visit_branch(self, node: IRBranch) -> Any: ...
    def visit_instruction(self, node: IRInstruction) -> Any: ...  # fallback
```

### traverse_ir()

Top-down traversal driver.

```python
traverse_ir(program: IRProgram, visitor: IRVisitor) -> None
```

Traversal order:

```
IRProgram → IRModule → IRFunction → IRBasicBlock → IRInstruction
```

Each instruction dispatches to its own specific hook via `accept()`.

**Example — instruction counter:**

```python
class InstructionCounter(IRVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit_move(self, node):       self.count += 1
    def visit_assignment(self, node): self.count += 1
    def visit_call(self, node):       self.count += 1
    def visit_return(self, node):     self.count += 1
    def visit_branch(self, node):     self.count += 1

counter = InstructionCounter()
traverse_ir(program, counter)
print(counter.count)
```

---

## IRBuilder Scaffold (builder.py)

`IRBuilder` is the bridge between the semantic analysis phase and the IR.

```python
from app.ir.builder import IRBuilder
from app.parser.semantic.context import SemanticContext

ctx: SemanticContext = analyzer.analyse(program_node)
builder = IRBuilder(context=ctx)
ir_program = builder.build()
```

### Current behaviour (TASK-024 scaffold)

| Method | Returns | Notes |
|--------|---------|-------|
| `build()` | `IRProgram` | Empty program (scaffold) |
| `current_program()` | `IRProgram` | Delegates to `build()` |
| `context` | `SemanticContext` | The supplied context |

> [!IMPORTANT]
> `IRBuilder` raises `TypeError` if the supplied argument is not a
> `SemanticContext`. It logs a warning if the context contains semantic
> errors, but does **not** abort — incomplete IR may be generated.

### Future behaviour (TASK-025+)

`build()` will walk the COBOL AST (via the semantic context or directly),
query the symbol table and type information, and emit the corresponding IR
nodes.

---

## Extensibility

### Adding a new instruction type

1. Create a frozen dataclass that subclasses `IRInstruction`.
2. Implement `accept(visitor)` to call `visitor.visit_<new_type>(self)`.
3. Add `visit_<new_type>` as a no-op to `IRVisitor`.
4. Export from `app/ir/instructions.py` and `app/ir/__init__.py`.

No existing code needs modification (Open/Closed Principle).

### Adding a new analysis pass

Subclass `IRVisitor` and override the hooks you need. Wire it into the
pipeline by calling `traverse_ir(program, my_pass)`.

### Planned extensions

| Feature | Extension path |
|---------|---------------|
| SSA construction | New `IRPhiInstruction` + transformation pass |
| Control-flow graph | `IRFunction` gains `successors`/`predecessors` maps |
| Type-annotated operands | `IROperand` value type replaces `str` operand names |
| Constant folding | New `IROptimiser` pass over `IRBasicBlock` |
| Java generation | `JavaCodegenVisitor(IRVisitor)` back-end |

---

## Independence Guarantee

> [!IMPORTANT]
> The `app/ir` package has **no imports from `app/parser/ast`**.
> The only semantic dependency is `app/parser/semantic/context.SemanticContext`
> used by `IRBuilder`. All other IR modules depend only on the Python standard
> library plus Loguru.

This isolation ensures the IR can be tested, serialised, and transformed
without requiring a parser.

---

## TASK-024 Test Coverage

The `tests/ir/test_ir_foundation.py` suite covers (161 tests):

- `IRNodeKind`: all 5 values, uniqueness.
- `IRNode`: cannot instantiate abstract class.
- `IRBasicBlock`: construction, label/name sync, `len()`, kind, frozen, hashable, equality, `accept()`.
- `IRInstruction`: abstract — cannot instantiate.
- `IRAssignment`, `IRMove`, `IRCall`, `IRReturn`, `IRBranch`: construction, defaults, fields, frozen, hashable, equality, `accept()` dispatch, no-method fallback.
- `IRFunction`, `IRModule`, `IRProgram`: construction, defaults, `len()`, kind, frozen, hashable, `accept()`.
- `IRVisitor`: all hooks return `None` by default; subclass can override.
- `traverse_ir()`: visit order (program → module → function → block → instruction), all instruction types dispatched, empty nodes at every level, multi-module/function/block programs, instruction-counting visitor.
- `IRBuilder`: valid context accepted, `TypeError` for wrong input, `context` property, `build()` returns `IRProgram`, empty result, reusability, context-with-errors accepted (warning logged).
- Instruction hierarchy isinstance checks (all types are `IRInstruction` and `IRNode`).
- Public API exports (all 15 types exported from `app.ir`).
