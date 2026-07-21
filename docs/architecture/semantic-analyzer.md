# Semantic Analyser — Architecture

## Overview

The semantic analyser is the stage in the COBOL compiler pipeline that
processes the Abstract Syntax Tree (AST) produced by the parser, builds a
typed symbol table, and validates structural constraints that cannot be
expressed by the grammar alone.

This document describes the design, responsibilities, data structures, and
extension points established by **TASK-018** (foundation), **TASK-019**
(symbol-collection visitor), and **TASK-020** (reference resolution visitor).

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
├── __init__.py           ← Public API surface
├── symbols.py            ← Symbol hierarchy (SymbolKind, Symbol, subclasses)
├── diagnostics.py        ← SemanticDiagnostic, SemanticSeverity, DIAGNOSTIC_CODES
├── context.py            ← SymbolTable, SemanticContext
├── visitors.py           ← SemanticVisitor, traverse_program
├── symbol_collector.py   ← SymbolCollectorVisitor  (pass 1 — TASK-019)
├── reference_resolver.py ← ReferenceResolverVisitor (pass 2 — TASK-020)
└── analyzer.py           ← SemanticAnalyzer (pipeline orchestrator)
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
           ├
> [!IMPORTANT]
> `SymbolCollectorVisitor` is now the **canonical symbol-collection
> implementation**.  `SemanticAnalyzer` delegates entirely to it, making
> the analyser a thin orchestrator with a clear two-pass pipeline.

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

### Multi-Pass Pipeline (TASK-020)

As of TASK-020, `SemanticAnalyzer` orchestrates a **two-pass pipeline**.
Both passes share the same `SymbolTable` and diagnostics list:

```
analyse(program)
    │
    ├─ SymbolTable          (fresh per call) ─────────────────────────┐
    ├─ list[SemanticDiagnostic] (fresh per call) ─────────────────────┤
    │                                                                  │
    ├─ PASS 1: SymbolCollectorVisitor ──► traverse_program            │
    │         │                                                        │
    │         ├─ visit_identification_division → ProgramSymbol        │
    │         ├─ visit_elementary_item         → VariableSymbol       │
    │         ├─ visit_group_item              → VariableSymbol       │
    │         ├─ visit_condition_name          → VariableSymbol       │
    │         └─ visit_paragraph               → ParagraphSymbol      │
    │                                                                  │
    └─ PASS 2: ReferenceResolverVisitor ──► traverse_program          │
              │                                                        │
              ├─ visit_move_statement    → resolve source & target     │
              └─ visit_display_statement → resolve operand            │
                                                                       │
    ◄── SemanticContext(symbol_table, diagnostics) ───────────────────┘
```

> [!IMPORTANT]
> Pass 1 **always** runs before pass 2.  This guarantees that every
> declared symbol is registered before any reference-resolution check
> occurs — forward references to paragraphs and variables declared later
> in the source are handled correctly.

---� forward references to paragraphs and variables declared later
> in the source are handled correctly.    │
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

---

## Reference Resolution Pass (TASK-020)

### `ReferenceResolverVisitor`

Introduced in TASK-020, `ReferenceResolverVisitor` is the **second semantic
pass**.  It expects a fully-populated `SymbolTable` and traverses statement
nodes inside paragraphs to resolve identifier references.

**Module**: `app.parser.semantic.reference_resolver`

**Statements Visited**

| Statement          | Operands Resolved          | Skip Condition                              |
|--------------------|---------------------------|---------------------------------------------|
| `MoveStatementNode`    | `source`, `target`        | Literal or figurative constant              |
| `DisplayStatementNode` | `operand`                 | Literal or figurative constant              |

**Literal Classification**

The helper `_is_literal(token)` classifies tokens:

| Token form          | Example            | Treated as |
|---------------------|--------------------|------------|
| Quoted string       | `"HELLO"`, `'Y'`   | Literal    |
| Numeric             | `1`, `+5`, `-99`   | Literal    |
| Figurative constant | `SPACES`, `ZEROS`  | Literal    |
| Other               | `WS-COUNT`         | Data-name  |

**Diagnostic Codes Emitted**

| Code    | Condition                       |
|---------|---------------------------------|
| SEM003  | Undefined variable reference    |
| SEM004  | Undefined paragraph reference   |
| SEM005  | Undefined section reference     |

**Extensibility**

All resolution flows through `_resolve_identifier()`, the single resolution
point.  Future subclasses override only this method to add:

- Nested scope walk (via the `scope` parameter)
- Qualified-name resolution (`qualifier` parameter)
- COPYBOOK or external-program symbol tables

---

## What Is NOT Implemented (By Design)

The following are explicitly **out of scope** for TASK-018 / TASK-019 / TASK-020:

- Type checking and expression analysis
- Control-flow analysis (dead code, unreachable paragraphs)
- Data-flow analysis
- Constant folding
- Optimisation passes
- Cross-reference generation
- PERFORM target validation (paragraphs not yet reachable through AST)
- IDE features (hover, completion, rename)
- Warning diagnostics (only structural `ERROR` codes are emitted)

---

## Future Enhancements

| Enhancement                  | Description                                                  |
|-----------------------------|--------------------------------------------------------------|
| `PerformTargetValidator`    | Validate PERFORM names against declared paragraphs           |
| `UnreferencedSymbolReporter`| Emit WARNING for symbols never referenced                    |
| `SectionSymbol`             | Track SECTION declarations                                   |
| `CopyBookResolver`          | Merge symbols from included COPY books                       |
| `ExternalProgramResolver`   | Validate CALL targets against known entry points             |

Add new rules by subclassing `SemanticVisitor` and registering the visitor
in `SemanticAnalyzer.analyse()` — no AST classes need modification.

---

## Testing

The test suite lives at:

- `tests/semantic/test_semantic_analyzer.py` — TASK-018 foundation tests.
- `tests/semantic/test_symbol_collector.py`  — TASK-019 `SymbolCollectorVisitor` tests.
- `tests/semantic/test_reference_resolver.py` — TASK-020 `ReferenceResolverVisitor` tests.

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

The TASK-020 suite covers:

- `_is_literal` helper (quoted strings, numerics, figurative constants, bare identifiers)
- `ReferenceResolverVisitor` construction and reference storage
- `MOVE` statement resolution (declared, undeclared, literals, figurative constants)
- `DISPLAY` statement resolution (declared, undeclared, literals)
- Traversal continuity after errors
- Empty / minimal program edge cases
- `_resolve_paragraph_reference` (SEM004)
- `_resolve_section_reference` (SEM005)
- Diagnostic content (code, severity, message, position)
- Representative full COBOL program (clean and dirty)
- `SemanticAnalyzer` two-pass integration (pass ordering, reusability, coexistence
  of SEM001 + SEM003, literal operand not falsely flagged)

Run with:

```bash
pytest tests/semantic/ -v
```

---

## Semantic Validation Pass (TASK-021)

### `SemanticValidationVisitor`

Introduced in TASK-021, `SemanticValidationVisitor` is the **third semantic
pass**.  It runs after reference resolution and enforces structural and
semantic constraints on the AST.

**Module**: `app.parser.semantic.validation`

### Three-Pass Pipeline (Updated)

`
SemanticAnalyzer.analyse(program)
 |
 +-->> PASS 1: SymbolCollectorVisitor  <--> traverse_program
 |          |
 |          +->> visit_elementary_item  --> VariableSymbol
 |          +->> visit_group_item       --> VariableSymbol
 |          +->> visit_condition_name   --> VariableSymbol
 |          +->> visit_paragraph        --> ParagraphSymbol
 |
 +-->> PASS 2: ReferenceResolverVisitor <--> traverse_program
 |          |
 |          +->> visit_move_statement    --> resolve source & target
 |          +->> visit_display_statement --> resolve operand
 |
 +-->> PASS 3: SemanticValidationVisitor <--> traverse_program
           |
           +->> visit_identification_division --> _check_program_id      (SEM006)
           +->> visit_procedure_division      --> _check_empty_proc_div  (SEM007)
           +->> visit_elementary_item         --> _check_reserved_word   (SEM008)
           +->> visit_group_item              --> _check_reserved_word   (SEM008)
           +->> visit_condition_name          --> _check_reserved_word   (SEM008)
           +->> _check_static_call_target()   --> (SEM009, future use)
 |
 +--, SemanticContext(symbol_table, diagnostics) <-------------------<<
`

> [!IMPORTANT]
> Passes execute strictly in order: 1 ? 2 ? 3. All three share the same
> `SymbolTable` and `diagnostics` list. Pass 3 can rely on the fully
> populated symbol table from pass 1.

### Validation Rules

| Code   | Rule                                   | Condition                              |
|--------|----------------------------------------|----------------------------------------|
| SEM006 | Missing or empty PROGRAM-ID            | `program_id` absent or blank         |
| SEM007 | Empty PROCEDURE DIVISION               | Division present, zero paragraphs      |
| SEM008 | Reserved word used as identifier       | Data-item name in `COBOL_RESERVED_WORDS` |
| SEM009 | Invalid static CALL target             | CALL literal blank (hook for future use) |

### Diagnostic Code Summary (All Passes)

| Code   | Pass | Rule                              |
|--------|------|-----------------------------------|
| SEM001 | 1    | Duplicate variable declaration    |
| SEM002 | 1    | Duplicate paragraph declaration   |
| SEM003 | 2    | Undefined variable reference      |
| SEM004 | 2    | Undefined paragraph reference     |
| SEM005 | 2    | Undefined section reference       |
| SEM006 | 3    | Missing or empty PROGRAM-ID       |
| SEM007 | 3    | Empty PROCEDURE DIVISION          |
| SEM008 | 3    | Reserved word used as identifier  |
| SEM009 | 3    | Invalid static CALL target        |

### Adding New Validation Rules

1. Write a private `_check_<rule>(node, �)` method in `SemanticValidationVisitor`.
2. Call it from the relevant `visit_*` hook.
3. Register the new code in `DIAGNOSTIC_CODES` in `diagnostics.py`.

No existing visitor or analyser code needs modification.

The TASK-021 test suite covers:

- `SemanticValidationVisitor` construction
- `COBOL_RESERVED_WORDS` constant
- SEM006: absent program_id, blank value, whitespace, valid value, severity, message, position
- SEM007: zero paragraphs, one paragraph, multiple paragraphs, absent division, severity, message, position
- SEM008: elementary/group/condition-name reserved names, case-insensitivity, normal names, multiple violations, severity, message, position
- SEM009: blank target, whitespace target, non-blank target, severity, message
- Traversal continuity: SEM006+SEM007 together, SEM008+SEM007 together, multiple SEM008
- Empty program edge cases
- Representative valid and invalid programs
- `SemanticAnalyzer` three-pass integration: all codes in context, reusability, cross-pass coexistence
- Standalone composition with `SymbolCollectorVisitor`
- Parameterised reserved-word spot-checks (16 keywords)

---

## COBOL Data Type Model (TASK-022)

### Overview

TASK-022 introduces a **semantic type system** for COBOL data items, independent
of the parser AST.  The type objects model the storage layout and interpretation
of each data item as understood by the semantic analyser � separate from the raw
PIC clause string captured in the AST.

### New Modules

| Module | Purpose |
|--------|---------|
| `app.parser.semantic.types` | `CobolType` abstract base and concrete type classes |
| `app.parser.semantic.type_builder` | Pass 4: interprets PIC clauses, builds types, attaches to symbols |

### Type Hierarchy

`
CobolType (ABC)
+-- NumericType       � PIC 9 / PIC S9 (signed, decimal, COMP, COMP-3)
+-- AlphanumericType  � PIC X (character strings)
+-- GroupType         � group records (no PIC clause)
`

All type classes are **frozen dataclasses** (immutable and hashable).

### UsageType Enum

`python
class UsageType(Enum):
    DISPLAY    # default character representation
    COMP       # binary (alias: COMP-4, BINARY)
    COMP_1     # single-precision float
    COMP_2     # double-precision float
    COMP_3     # packed decimal (alias: PACKED-DECIMAL)
    COMP_5     # native binary
    INDEX      # index data items
    POINTER    # USAGE POINTER
`

### VariableSymbol Enhancement

`VariableSymbol` (in `symbols.py`) now carries an optional
`cobol_type: CobolType | None` field.  It defaults to `None` before pass 4
runs, and is populated by `TypeBuilder` via `dataclasses.replace()` +
`SymbolTable.replace_symbol()`.

### SymbolTable Enhancement

`SymbolTable.replace_symbol(symbol)` was added to allow pass 4 to swap an
existing symbol for an updated copy carrying a resolved `CobolType` while
preserving insertion order.

### Four-Pass Pipeline (Updated)

`
SemanticAnalyzer.analyse(program)
 |
 +-->> PASS 1: SymbolCollectorVisitor   (AST traversal)
 |          registers all symbols; detects SEM001/SEM002
 |
 +-->> PASS 2: ReferenceResolverVisitor (AST traversal)
 |          resolves MOVE/DISPLAY refs; emits SEM003/SEM004/SEM005
 |
 +-->> PASS 3: SemanticValidationVisitor (AST traversal)
 |          checks PROGRAM-ID, empty PROC DIV, reserved words; emits SEM006-SEM009
 |
 +-->> PASS 4: TypeBuilder              (SymbolTable iteration, no AST re-traversal)
           interprets PIC clauses; attaches CobolType to VariableSymbols
`

> [!IMPORTANT]
> Pass 4 does **not** re-traverse the AST. It operates entirely on the already-populated `SymbolTable`.

### PIC Clause Interpretation

| PIC Pattern | Resulting Type |
|-------------|----------------|
| `9` / `9(n)` | `NumericType(digits=n, signed=False, decimal_places=0)` |
| `S9(n)` | `NumericType(digits=n, signed=True)` |
| `9(n)V9(m)` | `NumericType(digits=n+m, decimal_places=m)` |
| `S9(n)V9(m)` | `NumericType(digits=n+m, signed=True, decimal_places=m)` |
| `X` / `X(n)` | `AlphanumericType(length=n)` |
| `XX...` (bare) | `AlphanumericType(length=len)` |
| absent (group/88) | `GroupType()` |
| unrecognised | `None` (warning logged; no crash) |

### Extensibility

New COBOL features can be added without modifying existing types:

| Feature | Extension path |
|---------|----------------|
| OCCURS | Add `ArrayType(element_type, occurs)` subclass |
| REDEFINES | Add `RedefinesType(target_name)` subclass |
| POINTER | Add to `UsageType.POINTER`; extend `TypeBuilder._infer_usage()` |
| PIC N (National) | Add `NationalType(length)`; extend `_parse_pic` |
| PIC U (UTF-8) | Add `Utf8Type(length)`; extend `_parse_pic` |
| Explicit USAGE | Extend `TypeBuilder._infer_usage(usage_str)` |

### TASK-022 Test Suite

The `tests/semantic/test_type_builder.py` suite covers:

- `UsageType` enum: all values, aliases, uniqueness.
- `CobolType` abstract base: all three concrete subtypes.
- `NumericType`: digits, signed, decimal_places, usage, is_integer,
  total_digits, immutability, equality, hashing, `dataclasses.replace()`.
- `AlphanumericType`: length, usage default, immutability, equality.
- `GroupType`: member_names default, storage, immutability.
- `VariableSymbol.cobol_type`: default None, set at construction,
  existing fields unaffected, frozen, `dataclasses.replace()`.
- `SymbolTable.replace_symbol()`: success/failure, lookup after replace,
  insertion order, length unchanged.
- `TypeBuilder._parse_numeric_pic()`: 9 parametrised patterns.
- `TypeBuilder._parse_alpha_pic()`: 6 parametrised patterns.
- `TypeBuilder._infer_usage()`: DISPLAY default.
- `TypeBuilder.usage_from_string()`: 11 known usages + unknown fallback +
  case-insensitivity + whitespace.
- `TypeBuilder.build()`: all PIC categories, empty table, already-typed
  skip, unrecognised PIC, mixed table.
- AST-traversal integration (SymbolCollectorVisitor + TypeBuilder).
- `SemanticAnalyzer` four-pass integration: all type categories, mixed WS,
  no pass-4 diagnostics, cross-pass coexistence, reusability.
- Parametrised spot-checks: 7 numeric PIC patterns � full pipeline;
  5 alpha PIC patterns � full pipeline.
- COMP / COMP-3 usage attachment.
- Public API exports.

---

## Semantic Type Checking (TASK-023)

### Overview

TASK-023 introduces **pass 5** of the semantic pipeline:
`TypeCheckerVisitor`. This pass validates that COBOL statements operate on
compatible data types using the `CobolType` objects attached to
`VariableSymbol` records by `TypeBuilder` (pass 4).

### New Module

| Module | Purpose |
|--------|---------|
| `app.parser.semantic.type_checker` | Pass 5: validates type compatibility of COBOL statements |

### New Diagnostic Codes

| Code | Meaning |
|------|---------|
| SEM010 | Alphanumeric source moved to numeric target (incompatible MOVE) |
| SEM011 | Non-numeric operand in arithmetic statement |
| SEM012 | Variable referenced but has no resolved semantic type |
| SEM013 | Unsupported operation on this type (reserved for future use) |

### Five-Pass Pipeline (Updated)

`
SemanticAnalyzer.analyse(program)
 |
 +-->> PASS 1: SymbolCollectorVisitor   (AST traversal)
 |          registers all symbols; detects SEM001/SEM002
 |
 +-->> PASS 2: ReferenceResolverVisitor (AST traversal)
 |          resolves MOVE/DISPLAY refs; emits SEM003/SEM004/SEM005
 |
 +-->> PASS 3: SemanticValidationVisitor (AST traversal)
 |          checks PROGRAM-ID, empty PROC DIV, reserved words; emits SEM006-SEM009
 |
 +-->> PASS 4: TypeBuilder              (SymbolTable iteration, no AST re-traversal)
 |          interprets PIC clauses; attaches CobolType to VariableSymbols
 |
 +-->> PASS 5: TypeCheckerVisitor       (AST traversal)
           validates type compatibility; emits SEM010-SEM013
`

> [!IMPORTANT]
> Pass 5 depends on pass 4 having already attached `CobolType` objects. The pipeline order is fixed.

### TypeCheckerVisitor

`TypeCheckerVisitor` is a `SemanticVisitor` subclass (extends pass 2/3 architecture). It:

- **visit_move_statement()** � validates MOVE type compatibility.
- **visit_display_statement()** � validates DISPLAY operand has a resolved type.
- **_check_arithmetic_operand()** � extension hook for future ADD/COMPUTE support.
- **_check_unsupported_operation()** � extension hook for future type constraints.
- **_compatible_move()** � single authority for MOVE type compatibility rules.

### Compatibility Rules

#### MOVE Statement

| Source \ Target  | Numeric | Alphanumeric | Group |
|-----------------|---------|--------------|-------|
| NumericType     | ?       | ?            | ?     |
| AlphanumericType| ? SEM010| ?            | ?     |
| GroupType       | ?       | ?            | ?     |
| Literal         | ?       | ?            | ?     |
| Figurative const| ?       | ?            | ?     |

Only alphanumeric ? numeric is prohibited.

#### DISPLAY Statement

Any resolved type (numeric, alphanumeric, group) is valid for DISPLAY.
Literals and figurative constants are always valid.

#### Arithmetic (extension hook)

Operands must be `NumericType` (SEM011 otherwise). Currently not wired to any
AST node as arithmetic statements are not yet represented.

### Extensibility

Adding new statement support:

1. Override the `visit_<statement>` hook.
2. Implement a `_check_<statement>` method.
3. Add new SEM0xx codes to `DIAGNOSTIC_CODES`.

Adding new compatibility rules:

- Extend `_compatible_move()` only. No other callers need modification.
- Add new subclasses to the `CobolType` hierarchy (e.g., `NationalType`).

### TASK-023 Test Suite

The `tests/semantic/test_type_checker.py` suite covers:

- `_is_literal()` helper: 16 cases (quoted, numeric, figurative, bare id).
- `_compatible_move()`: 11 cases (all type combinations).
- `TypeCheckerVisitor` construction.
- `visit_move_statement()`: 16 cases (all combinations, literals, undefined, untyped).
- `visit_display_statement()`: 10 cases (literals, all types, undefined, untyped).
- `_check_arithmetic_operand()`: 10 cases (numeric ok, alpha/group SEM011, untyped SEM012).
- `_check_unsupported_operation()`: 4 cases (SEM013 content and severity).
- `SemanticAnalyzer` pass 5 integration: 10 cases (valid programs, invalid MOVEs,
  cross-pass diagnostic coexistence, reusability, ordering guarantee).
- Standalone traversal via `traverse_program`.
- Representative programs: payroll, multi-paragraph with mixed errors.
- Public API export.
