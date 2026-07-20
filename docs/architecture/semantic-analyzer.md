# Semantic Analyser — Architecture

## Overview

The semantic analyser is the stage in the COBOL compiler pipeline that
processes the Abstract Syntax Tree (AST) produced by the parser, builds a
typed symbol table, and validates structural constraints that cannot be
expressed by the grammar alone.

This document describes the design, responsibilities, data structures, and
extension points established by **TASK-018** (foundation) and extended by
**TASK-019** (symbol-collection visitor).

---

## Pipeline Position

```
Source Reader
     ↓
Format Detection
     ↓
Source Normalisation
     ↓
Lexer  →  Token Stream
     ↓
Parser  →  AST (ProgramNode)
     ↓
Semantic Analyser  →  SemanticContext   ← HERE
     ↓
IR Generation
     ↓
RAG / AI Pipeline
```

The semantic analyser sits between the parser output (`ProgramNode`) and
the IR generation stage. It receives a fully parsed (and
recovery-augmented) AST and produces an immutable `SemanticContext`
consumed by all downstream stages.

---

## Module Structure

```
app/parser/semantic/
├── __init__.py          ← Public API surface
├── symbols.py           ← Symbol hierarchy (SymbolKind, Symbol, subclasses)
├── diagnostics.py       ← SemanticDiagnostic, SemanticSeverity
├── context.py           ← SymbolTable, SemanticContext
├── visitors.py          ← SemanticVisitor, traverse_program
├── symbol_collector.py  ← SymbolCollectorVisitor (TASK-019 — symbol-collection pass)
└── analyzer.py          ← SemanticAnalyzer (entry point)
```

---

## Symbol Hierarchy

### `SymbolKind` (enum)

Identifies the category of a registered symbol.

| Member       | Value        | Represents                          |
|-------------|--------------|-------------------------------------|
| `PROGRAM`   | `"program"`  | PROGRAM-ID clause → program name    |
| `VARIABLE`  | `"variable"` | DATA DIVISION data item             |
| `PARAGRAPH` | `"paragraph"`| PROCEDURE DIVISION paragraph label  |

### Symbol Base and Concrete Types

All symbols are **frozen dataclasses** (immutable, hashable).

```
Symbol (abstract)
├── ProgramSymbol    — name from PROGRAM-ID clause
├── VariableSymbol   — data item: name, level, picture (optional)
└── ParagraphSymbol  — paragraph label: name
```

Every symbol carries:
- `name` — uppercased identifier string.
- `declared_at` — source `Position` (line, column, offset, filename).
- `kind` — the `SymbolKind` property, overridden by each subclass.

---

## Symbol Table

`SymbolTable` is a **mutable, scoped registry** managed by the analyser
during a single analysis pass.

### Internal Structure

| Structure    | Purpose                                            |
|-------------|----------------------------------------------------|
| `_by_name`  | `dict[str, Symbol]` — O(1) case-insensitive lookup |
| `_all`      | `list[Symbol]` — insertion-order iteration          |

### Key Operations

| Method                   | Returns        | Description                                           |
|--------------------------|----------------|-------------------------------------------------------|
| `register(symbol)`       | `bool`         | `True` if registered; `False` if name already exists |
| `lookup(name)`           | `Symbol | None`| Case-insensitive name lookup                          |
| `all_symbols()`          | `list`         | Defensive copy in insertion order                     |
| `symbols_of_kind(kind)`  | `list`         | Filter by `SymbolKind`                                |
| `__len__`                | `int`          | Total registered symbol count                         |
| `__contains__(name)`     | `bool`         | Case-insensitive membership test                      |

### Duplicate Detection

Duplicate detection is **per name** (case-insensitive). The first
registration wins; subsequent registrations with the same name return
`False` without overwriting. The caller is responsible for emitting a
diagnostic.

---

## Semantic Diagnostics

`SemanticDiagnostic` is an **immutable frozen dataclass** carrying:

| Field       | Type               | Description                               |
|------------|---------------------|-------------------------------------------|
| `message`  | `str`               | Human-readable description of the error   |
| `position` | `Position`          | Source location of the offending construct|
| `severity` | `SemanticSeverity`  | `ERROR` or `WARNING`                      |
| `code`     | `str`               | Diagnostic rule code (e.g. `"SEM001"`)    |

### Registered Codes

| Code     | Rule                             |
|----------|----------------------------------|
| `SEM001` | Duplicate variable declaration   |
| `SEM002` | Duplicate paragraph declaration  |

> [!NOTE]
> `WARNING`-level diagnostics are reserved for future use (e.g. unreferenced
> variables). Only `ERROR` is emitted in TASK-018.

---

## Visitor Architecture

### Design Rationale

The Visitor pattern decouples the AST node structure from analysis logic.
Adding a new semantic rule never requires modifying an AST class — it
requires only subclassing `SemanticVisitor` and overriding the relevant
`visit_*` method.

### `SemanticVisitor` (extends `ASTVisitor`)

`SemanticVisitor` adds the following hooks on top of the base class:

| Hook                              | Fired on                               |
|-----------------------------------|----------------------------------------|
| `visit_identification_division`   | `IdentificationDivisionNode`           |
| `visit_data_division`             | `DataDivisionNode`                     |
| `visit_working_storage_section`   | `WorkingStorageSectionNode`            |
| `visit_data_item`                 | `DataItemNode` (generic fallback)      |
| `visit_elementary_item`           | `ElementaryItemNode`                   |
| `visit_group_item`                | `GroupItemNode`                        |
| `visit_condition_name`            | `ConditionNameNode`                    |
| `visit_procedure_division`        | `ProcedureDivisionNode`                |
| `visit_paragraph`                 | `ParagraphNode`                        |

All methods have **no-op default implementations** — subclasses only
override the hooks they use.

### `traverse_program(program, visitor)`

The `traverse_program` function drives the standard top-down traversal:

```
ProgramNode
├── visit_program
├── IdentificationDivisionNode  → visit_identification_division
├── DataDivisionNode            → visit_data_division
│   └── WorkingStorageSectionNode → visit_working_storage_section
│       ├── ElementaryItemNode  → visit_elementary_item
│       ├── GroupItemNode       → visit_group_item
│       └── ConditionNameNode   → visit_condition_name
└── ProcedureDivisionNode      → visit_procedure_division
    └── ParagraphNode           → visit_paragraph
```

> [!IMPORTANT]
> `traverse_program` is the **only** traversal driver used by
> `SemanticAnalyzer`. Future passes should call `traverse_program` rather
> than implementing their own traversal logic.

---

## Symbol Collection Pass (TASK-019)

### `SymbolCollectorVisitor`

Introduced in TASK-019, `SymbolCollectorVisitor` is the **public, reusable**
visitor responsible for populating the `SymbolTable`.  It separates the
symbol-collection *concern* from the orchestration *concern* owned by
`SemanticAnalyzer`.

**Module**: `app.parser.semantic.symbol_collector`

**Design Goals**

- Modular: the collector has a single, focused responsibility.
- Composable: it can be used inside a multi-pass pipeline or standalone.
- Fault-tolerant: duplicate detection never aborts traversal.

**Visited Nodes and Registered Symbols**

| AST Node                     | Symbol Registered          | Diagnostic on Duplicate |
|------------------------------|---------------------------|-------------------------|
| `IdentificationDivisionNode` | `ProgramSymbol`           | *(no duplicate expected)*|
| `ElementaryItemNode`         | `VariableSymbol`          | `SEM001`                |
| `GroupItemNode`              | `VariableSymbol` (no pic) | `SEM001`                |
| `ConditionNameNode`          | `VariableSymbol` (lvl 88) | `SEM001`                |
| `ParagraphNode`              | `ParagraphSymbol`         | `SEM002`                |

**Standalone Usage**

```python
from app.parser.semantic.context import SymbolTable
from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
from app.parser.semantic.visitors import traverse_program

table = SymbolTable()
diagnostics = []
collector = SymbolCollectorVisitor(table=table, diagnostics=diagnostics)
traverse_program(program_node, collector)

table.all_symbols()   # all registered symbols
diagnostics           # any SEM001 / SEM002 errors
```

### Two-Layer Architecture

```
SemanticAnalyzer.analyse(program)
    │
    ├─ SymbolTable  (fresh per call)
    ├─ list[SemanticDiagnostic]  (fresh per call)
    │
    └─ SymbolCollectorVisitor ─► traverse_program
           │
           ├─ visit_identification_division → ProgramSymbol
           ├─ visit_elementary_item         → VariableSymbol
           ├─ visit_group_item              → VariableSymbol
           ├─ visit_condition_name          → VariableSymbol (level 88)
           └─ visit_paragraph               → ParagraphSymbol

    ◄─ SemanticContext(symbol_table, diagnostics)
```

> [!IMPORTANT]
> `SymbolCollectorVisitor` is now the **canonical symbol-collection
> implementation**.  `SemanticAnalyzer` delegates entirely to it, making
> the analyser a thin orchestrator.

---

## `SemanticAnalyzer`

### Entry Point

```python
from app.parser.semantic import SemanticAnalyzer

analyzer = SemanticAnalyzer()
ctx = analyzer.analyse(program_node)
```

`SemanticAnalyzer.analyse(program)` is **reusable** — each call
produces an independent `SemanticContext` backed by a fresh
`SymbolTable` and diagnostics list.

### Internal Design

`SemanticAnalyzer` creates a `SymbolCollectorVisitor` that holds references
to the mutable `SymbolTable` and diagnostics list.
`traverse_program` drives the traversal; the collector populates both
structures via its `visit_*` overrides.

```
analyse(program)
    │
    ├─ SymbolTable  ─────────────────────────────────────┐
    ├─ list[SemanticDiagnostic]  ───────────────────────────┤
    │                                                             │
    └─ SymbolCollectorVisitor ─► traverse_program                  │
           │                                                      │
           ├─ visit_identification_division → ProgramSymbol       │
           ├─ visit_elementary_item  → VariableSymbol             │
           ├─ visit_group_item       → VariableSymbol             │
           ├─ visit_condition_name   → VariableSymbol (level 88)  │
           └─ visit_paragraph        → ParagraphSymbol             │
                                                                   │
    ◄── SemanticContext(symbol_table, diagnostics) ─────────────┘
```

---

## `SemanticContext` (Result)

`SemanticContext` is an **immutable result object** returned after analysis:

| Property        | Type                         | Description                           |
|----------------|------------------------------|---------------------------------------|
| `symbol_table` | `SymbolTable`                | All registered symbols                |
| `diagnostics`  | `list[SemanticDiagnostic]`   | Defensive copy of collected diagnostics|
| `has_errors`   | `bool`                       | `True` if any ERROR diagnostics exist |
| `error_count`  | `int`                        | Count of ERROR-level diagnostics      |

---

## What Is NOT Implemented (By Design)

The following are explicitly **out of scope** for TASK-018:

- Type checking and expression analysis
- Control-flow analysis (dead code, unreachable paragraphs)
- Data-flow analysis
- Constant folding
- Optimisation passes
- Cross-reference generation
- Symbol resolution (PERFORM targets, MOVE operand validation)
- IDE features (hover, completion, rename)
- Warning diagnostics (only structural `ERROR` duplicates are emitted)

---

## Future Enhancements

| Enhancement                  | Description                                           |
|-----------------------------|-------------------------------------------------------|
| `PerformTargetValidator`    | Validate PERFORM names against declared paragraphs    |
| `DataReferenceValidator`    | Validate MOVE/IF operands against declared variables  |
| `UnreferencedSymbolReporter`| Emit WARNING for symbols never referenced             |
| `SectionSymbol`             | Track SECTION declarations                            |
| `CopyBookResolver`          | Merge symbols from included COPY books                |

Add new rules by subclassing `SemanticVisitor` and registering the visitor
in `SemanticAnalyzer.analyse()` — no AST classes need modification.

---

## Testing

The test suite lives at:

- `tests/semantic/test_semantic_analyzer.py` — TASK-018 foundation tests.
- `tests/semantic/test_symbol_collector.py`  — TASK-019 `SymbolCollectorVisitor` tests.

The TASK-018 suite covers:

- `SymbolKind` enum members
- All three symbol subclasses (construction, kind, immutability)
- `SymbolTable` (register, lookup, duplicate detection, iteration, filtering)
- `SemanticDiagnostic` (construction, `__str__`, frozen, equality)
- `SemanticContext` (has_errors, error_count, defensive copies)
- `SemanticVisitor` (all default hooks, selective override)
- `traverse_program` (all division types, graceful None handling)
- `SemanticAnalyzer` (empty, partial, full programs; duplicate detection;
  reusability; mixed clean/error programs)

The TASK-019 suite covers:

- `SymbolCollectorVisitor` construction and reference storage
- Program symbol registration (present, absent, uppercasing)
- Variable symbol registration (elementary, group, condition; multi, empty, order)
- Paragraph symbol registration (single, multiple, uppercasing)
- Duplicate detection (SEM001 / SEM002; message content; first survives;
  traversal continues; position accuracy; mixed duplicates)
- Empty AST edge cases
- Representative full COBOL program (all kinds, total count, no spurious errors)
- Visitor reusability and independence
- `SemanticAnalyzer` integration regression guard

Run with:

```bash
pytest tests/semantic/ -v
```
