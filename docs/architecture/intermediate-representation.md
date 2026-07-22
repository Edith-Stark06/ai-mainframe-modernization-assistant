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
  IR Builder  (structural translation implemented in TASK-025)
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
└── builder.py        — IRBuilder (structural translation)
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

### IRDisplay

Write an operand value to the console output.

```python
IRDisplay(operand='"HELLO WORLD"')
IRDisplay(operand="WS-NAME")
```

| Field | Description |
|-------|-------------|
| `operand` | Variable name or literal text |

### IRAccept

Read input from the console into a variable.

```python
IRAccept(result="WS-INPUT")
```

| Field | Description |
|-------|-------------|
| `result` | Name of the destination variable |

### Arithmetic Instructions (IRAdd, IRSubtract, IRMultiply, IRDivide)

Compute the arithmetic result of two operands.
These map to `ADD ... TO`, `SUBTRACT ... FROM`, `MULTIPLY ... BY`, and `DIVIDE ... INTO`.

```python
IRAdd(left="100", right="WS-AMOUNT")
IRSubtract(left="WS-TAX", right="WS-NET")
```

| Field | Description |
|-------|-------------|
| `left` | Source operand name (or literal) |
| `right` | Target operand name (or literal) |


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
    def visit_display(self, node: IRDisplay) -> Any: ...
    def visit_accept(self, node: IRAccept) -> Any: ...
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

## AST-to-IR Translation Pipeline (TASK-025)

### Overview

`IRBuilder.build()` translates a `SemanticContext` into a structured
`IRProgram` using four focused helper methods:

| Method | Input | Output |
|--------|-------|--------|
| `build_program(prog_name, proc_div?)` | Program name + optional AST | `IRProgram` with one `IRModule` |
| `build_module(module_name, proc_div?)` | Module name + optional AST | `IRModule` with one `IRFunction` |
| `build_function(function_name, proc_div?)` | Function name + optional AST | `IRFunction` with one entry `IRBasicBlock` |
| `build_entry_block(proc_div?)` | Optional `ProcedureDivisionNode` | `IRBasicBlock` with translated `IRMove` instructions |

### Translation Mapping

```
ProgramNode + SemanticContext
     │
     ├─ ProgramSymbol.name ─────────────────────────► IRProgram.name
     │                                                 IRModule.name
     │
     ├─ (always)  ──────────────────────────────────► IRFunction("__entry__")
     │
     └─ ProcedureDivision.paragraphs[*].statements
          └─ MoveStatementNode(source, target) ──► IRMove(source, result)
```

### Naming Helpers

Naming is delegated to three overridable methods:

| Method | Default | Purpose |
|--------|---------|--------|
| `_program_name()` | First `ProgramSymbol.name`, or `""` | Derives IRProgram name |
| `_module_name(prog_name)` | `prog_name` (identity) | Derives IRModule name |
| `_function_name()` | `"__entry__"` | Derives entry function name |

Subclass `IRBuilder` and override any naming helper to customise conventions
(e.g. Java package prefixes) without touching orchestration logic.

### Extension Points for Future Tasks

| Extension | Where to add |
|-----------|-------------|
| **✅ TASK-026** Translate MOVE statements | `build_entry_block()` — iterates paragraphs, emits `IRMove` |
| Translate DISPLAY statements | `build_entry_block()` — emit `IRCall` |
| Translate IF / EVALUATE | `build_function()` — emit additional `IRBasicBlock` + `IRBranch` |
| Translate PERFORM | `build_function()` — emit `IRCall` |
| Translate GO TO | `build_function()` — emit unconditional `IRBranch` |
| Translate arithmetic | `build_entry_block()` — emit `IRAssignment` |
| Multiple paragraphs → multiple functions | `build_module()` — iterate `ParagraphSymbol` list |
| Nested programs → multiple modules | `build_program()` — iterate nested `ProgramSymbol` list |

---

## TASK-024 + TASK-025 Test Coverage

The `tests/ir/test_ir_foundation.py` suite covers (221 tests):

**TASK-024 — IR Foundation (161 tests):**
- `IRNodeKind`: all 5 values, uniqueness.
- `IRNode`: cannot instantiate abstract class.
- `IRBasicBlock`: construction, label/name sync, `len()`, kind, frozen, hashable, equality, `accept()`.
- `IRInstruction`: abstract — cannot instantiate.
- `IRAssignment`, `IRMove`, `IRCall`, `IRReturn`, `IRBranch`: construction, defaults, fields, frozen, hashable, equality, `accept()` dispatch, no-method fallback.
- `IRFunction`, `IRModule`, `IRProgram`: construction, defaults, `len()`, kind, frozen, hashable, `accept()`.
- `IRVisitor`: all hooks return `None` by default; subclass can override.
- `traverse_ir()`: visit order, all instruction types dispatched, empty nodes, multi-level programs, counting visitor.
- `IRBuilder`: input validation, `context` property, `build()` returns `IRProgram`, reusability, error-context tolerance.
- Instruction hierarchy isinstance checks; public API exports.

**TASK-025 — Translation Foundation (60 tests):**
- Empty context → one unnamed module with one `__entry__` function and one `"entry"` block.
- Named `ProgramSymbol` → correct name propagation at every IR level.
- Multiple program name variations.
- IR node kinds at each level.
- `build()` determinism and statelessness.
- Traversal order via `traverse_ir()`.
- Error-context tolerance (context with semantic errors still produces full IR structure).
- Individual helper methods: `build_program`, `build_module`, `build_function`, `build_entry_block`.
- Naming helpers: `_program_name`, `_module_name`, `_function_name`.
- Subclass extensibility: override naming, override entry block generation.
- Structure invariants: frozen, hashable, correct types at each level.
- Context with paragraphs and variables: still one module, correct program name.
- `current_program()` contract.

---

## MOVE Statement Lowering (TASK-026)

### Overview

`build_entry_block(proc_div)` accepts a `ProcedureDivisionNode` and iterates
all paragraphs in source order, translating each `MoveStatementNode` into an
`IRMove` instruction.

```
ProcedureDivisionNode
  └─ ParagraphNode("MAIN-PARA")
       ├─ MoveStatementNode(source="WS-IN",   target="WS-OUT") ► IRMove(source="WS-IN",   result="WS-OUT")
       ├─ MoveStatementNode(source='"HELLO"', target="WS-OUT") ► IRMove(source='"HELLO"', result="WS-OUT")
       └─ MoveStatementNode(source="0",       target="WS-CNT") ► IRMove(source="0",       result="WS-CNT")
```

Unsupported statement types (DISPLAY, STOP RUN, GOBACK, etc.) are **logged at
DEBUG level and skipped**; translation continues with the remaining statements.

### Operand Translation

The three operand helpers provide a reusable classification layer:

| Helper | Classification rule | IR form |
|--------|--------------------|---------| 
| `build_operand(text)` | Dispatcher — calls one of the two below | — |
| `build_literal(text)` | Quoted string (`"..."`) or numeric (`42`, `-1`, `3.14`) | literal text unchanged |
| `build_variable_reference(name)` | Any other token | `SymbolTable.lookup(upper(name)).name` |

**Variable reference lookup flow:**

```
build_operand("ws-count")
  → build_variable_reference("ws-count")
  → SymbolTable.lookup("WS-COUNT")
      ├─ found  → return sym.name  ("WS-COUNT")
      └─ not found → return upper("ws-count")  ("WS-COUNT")  + DEBUG log
```

No re-parsing or semantic validation is performed during operand translation —
the `SymbolTable` already contains resolved symbols from earlier passes.

### New Methods (TASK-026)

| Method | Signature | Purpose |
|--------|-----------|--------|
| `build_move_instruction` | `(stmt: MoveStatementNode) -> IRMove` | Lower one MOVE statement |
| `build_operand` | `(text: str) -> str` | Classify and translate an operand |
| `build_variable_reference` | `(name: str) -> str` | Variable lookup with normalisation |
| `build_literal` | `(text: str) -> str` | Return literal text unchanged |
| `_is_numeric_literal` | `(text: str) -> bool` | Numeric token classification |
| `_translate_paragraph` | `(para: ParagraphNode) -> list[IRMove]` | Per-paragraph translation |
| `_translate_statement` | `(stmt: StatementNode) -> IRMove \| None` | Per-statement dispatch |
| `_extract_procedure_division` | `(node: ProgramNode \| None) -> ProcedureDivisionNode \| None` | Safe AST extraction |

---

## Test Coverage Summary

| Task | File | Tests |
|------|------|-------|
| TASK-024 — IR Foundation | `test_ir_foundation.py` | 161 |
| TASK-025 — Translation Foundation | `test_ir_foundation.py` | 60 |
| TASK-026 — MOVE Translation | `test_ir_move_translation.py` | 92 |
| **Total** | | **313+** |

### `tests/ir/test_ir_move_translation.py` (TASK-026, 92 tests)

- `_is_numeric_literal()`: plain integers, signed, decimal, empty, alphabetic, double-dot.
- `build_literal()`: string, numeric, zero, negative, decimal, empty-quotes.
- `build_variable_reference()`: known symbol, unknown symbol, case normalisation.
- `build_operand()`: quoted string → literal, numeric → literal, identifier → variable.
- `build_move_instruction()`: var→var, literal→var, numeric→var; frozen, hashable.
- `build_entry_block()`: None / empty proc_div, single MOVE, multi-MOVE order, cross-paragraph, DISPLAY skipped, mixed MOVE+DISPLAY.
- `build()` pipeline: no node, no proc div, empty proc div, single MOVE, two MOVEs, five MOVEs, cross-paragraph ordering, determinism, statelessness, name propagation, backward compat, unsupported-skip, structural invariants.
