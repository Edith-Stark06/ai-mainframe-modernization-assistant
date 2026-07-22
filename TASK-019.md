# TASK-019 — AST Symbol Collection Visitor

## Objective

Implement the first semantic analysis pass that traverses the parsed COBOL AST and populates the semantic symbol table.

This task establishes symbol collection for COBOL programs without performing semantic validation beyond duplicate detection.

---

## Background

Task-018 introduced the semantic analysis framework:

- SemanticAnalyzer
- SemanticContext
- SymbolTable
- Symbol hierarchy
- Diagnostics
- Visitor infrastructure

This task implements the first real semantic pass.

---

## Scope

Implement a SymbolCollectorVisitor that walks the AST and registers:

- Program symbols
- Working-Storage variables
- Local-Storage variables (if parsed)
- Linkage variables (if parsed)
- Paragraph names
- Section names (if represented)

The visitor should populate the SemanticContext symbol table.

---

## Functional Requirements

### 1. SymbolCollectorVisitor

Create:

app/parser/semantic/symbol_collector.py

Responsibilities:

- Traverse AST
- Visit declarations
- Register symbols
- Record duplicates
- Continue after diagnostics

---

### 2. SemanticAnalyzer Integration

SemanticAnalyzer should:

- Create SemanticContext
- Execute SymbolCollectorVisitor
- Return populated SemanticContext

---

### 3. Duplicate Detection

Detect duplicate declarations such as:

- Variables
- Paragraphs
- Sections

Emit semantic diagnostics rather than stopping analysis.

---

### 4. Symbol Registration

Register at minimum:

Program

Variables

Paragraphs

Future symbol kinds should be easy to extend.

---

### 5. Diagnostics

Produce structured diagnostics including:

- duplicate symbol
- symbol location
- previous declaration location (when available)

---

## Testing

Add unit tests covering:

- Single variable
- Multiple variables
- Multiple paragraphs
- Duplicate variable detection
- Duplicate paragraph detection
- Empty program
- Large sample AST

---

## Documentation

Update:

docs/architecture/semantic-analyzer.md

Describe:

- Symbol collection pass
- Visitor workflow
- Population of SemanticContext

---

## Acceptance Criteria

- AST traverses correctly
- Symbols registered
- Duplicate diagnostics emitted
- Tests pass
- Ruff passes
- Black passes
- MyPy passes
- Pytest passes

---

## Non-Goals

Do NOT implement:

- Type checking
- Name resolution
- Procedure flow analysis
- Constant evaluation
- Data type validation