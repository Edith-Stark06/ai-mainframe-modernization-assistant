# TASK-043 — AST / IR / Diagnostics Serialization

## Objective

Add a read-only serialization layer for the existing compiler pipeline so that
AST nodes, IR structures, and compiler diagnostics can be converted into
deterministic JSON-safe Python structures.

This task prepares the existing AnalysisService result for future API and
frontend integration.

The serializer layer must expose existing compiler information without changing
compiler behavior or introducing new compiler concepts.

---

## Scope

Implement serializers for:

1. AST
2. IR
3. Diagnostics

The implementation must use the existing repository classes as the source of
truth.

Do not invent, rename, or modify AST/IR/diagnostic fields merely to make them
easier to serialize.

---

## Important Constraints

### 1. Read-only adapters

Serializers must not mutate:

- AST nodes
- IR nodes
- diagnostic objects
- AnalysisResult
- semantic-analysis state
- parser state
- backend state

### 2. No compiler behavior changes

Do not modify:

- lexer behavior
- parser behavior
- semantic analysis
- IR construction
- Java generation
- diagnostic generation

### 3. No API changes

Do not add FastAPI routes in this task.

Do not add:

- WebSocket endpoints
- upload endpoints
- analysis endpoints
- artifact endpoints

Those belong to later integration work.

### 4. No frontend changes

Do not modify the React/Stitch frontend.

### 5. Repository source is authoritative

Before implementing the serializers, inspect the actual current definitions of:

- AST nodes
- AST base/protocol classes
- IRProgram
- IRModule
- IRFunction
- IRBasicBlock
- IRInstruction subclasses
- syntax diagnostics
- semantic diagnostics
- backend diagnostics
- severity enums
- existing serialization/schema utilities

Do not guess fields from documentation or previous task descriptions.

---

# Target Structure

Create the serializer package if it does not already exist.

Expected conceptual structure:

app/
└── analysis/
    ├── __init__.py
    ├── models.py
    ├── service.py
    └── serializers/
        ├── __init__.py
        ├── ast.py
        ├── ir.py
        └── diagnostics.py

Tests should follow the existing repository conventions.

Expected conceptual test structure:

tests/
└── analysis/
    ├── test_ast_serializer.py
    ├── test_ir_serializer.py
    └── test_diagnostics_serializer.py

If the repository already has an appropriate serializer/test location,
follow the existing convention instead of creating duplicate structures.

---

# AST Serialization

Implement a serializer for the existing AST hierarchy.

The serializer must:

- accept existing AST objects
- recursively serialize nested nodes
- preserve the existing AST structure
- preserve relevant source-position information already present on nodes
- preserve lists/tuples of child nodes
- serialize primitive values directly
- produce only JSON-safe Python values

The result must contain enough structural information for a future frontend
or API consumer to inspect the AST.

Use explicit type information for AST nodes where necessary to distinguish
different node kinds.

Do not alter the AST classes.

---

# IR Serialization

Implement a serializer for the existing IR hierarchy.

The serializer must support the repository's existing:

- IRProgram
- IRModule
- IRFunction
- IRBasicBlock
- IRInstruction hierarchy

and any additional IR structures actually present in the repository.

The serializer must:

- preserve hierarchy
- preserve instruction ordering
- preserve existing instruction fields
- preserve block/function/module relationships
- preserve primitive values
- produce JSON-safe Python structures
- be deterministic

Do not modify IR classes.

---

# Diagnostics Serialization

Implement serialization for all diagnostic types currently used by the
compiler pipeline.

At minimum inspect and support the repository's:

- parser/syntax diagnostics
- semantic diagnostics
- backend diagnostics

Preserve information that actually exists on each diagnostic, including
where applicable:

- message
- severity
- diagnostic code
- line
- column
- offset
- filename
- source/recovery context
- skipped-token information
- other existing diagnostic metadata

Do not invent fields that do not exist.

If different diagnostic classes have different fields, preserve those
differences rather than forcing them into an inaccurate common structure.

---

# JSON Safety

Serializer output must contain only JSON-compatible values:

- dict
- list
- str
- int
- float
- bool
- None

Enums, Paths, dataclasses, custom objects, and other non-JSON-native values
must be converted appropriately.

Do not return arbitrary object instances.

---

# Determinism

Repeated serialization of the same compiler object must produce equivalent
output.

Do not rely on:

- memory addresses
- object repr output
- unordered iteration where ordering is semantically relevant

Preserve source/program/instruction ordering.

---

# Public API

Expose clean serializer functions from the serializer modules.

Use names consistent with existing repository conventions.

Do not introduce a large framework or generic serialization dependency when
a small explicit implementation is sufficient.

If a shared internal helper is required, keep it private to the serialization
package unless there is an existing repository convention for exposing it.

---

# Tests

Add focused tests covering:

## AST

- representative AST serialization
- nested nodes
- lists of statements/nodes
- source position preservation
- primitive values
- deterministic output

## IR

- IRProgram serialization
- nested module/function/block structure
- instruction serialization
- instruction ordering
- deterministic output

## Diagnostics

- syntax diagnostic serialization
- semantic diagnostic serialization
- backend diagnostic serialization
- severity/code/location preservation where available
- diagnostic-specific fields where available
- JSON-safe output

Tests should construct or obtain real repository objects rather than using
fake structures that do not match production classes.

---

# Regression Safety

Existing behavior must remain unchanged.

The following must continue to pass where applicable:

```bash
pytest -q
ruff check .
black --check .
python -m mypy app
