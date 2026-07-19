# TASK-018 — Semantic Analyzer Foundation

## Objective

Implement the semantic analysis foundation for the COBOL compiler.

The semantic analyzer will traverse the AST produced by the parser, build symbol tables, collect semantic diagnostics, and provide the infrastructure for future semantic validation.

This task establishes the semantic analysis architecture but intentionally performs only minimal validation.

---

## Background

Completed compiler pipeline:

- Source Reader
- Format Detection
- Source Normalization
- Lexer
- Parser
- Error Recovery

Next stage:

AST → Semantic Analyzer

---

## Scope

### Implement

- SemanticAnalyzer
- SemanticContext
- SymbolTable
- Symbol hierarchy
- Semantic diagnostics
- AST visitor infrastructure
- Tests
- Documentation

---

## Symbol Types

Support:

- Program
- Variable
- Paragraph

Represent symbols using immutable dataclasses.

---

## Semantic Analyzer Responsibilities

Implement:

SemanticAnalyzer

Responsibilities:

- Traverse ProgramNode
- Register program symbol
- Register variables from Working-Storage
- Register paragraph names
- Produce semantic diagnostics
- Return SemanticContext

---

## Diagnostics

Implement structured semantic diagnostics.

Examples:

- Duplicate variable
- Duplicate paragraph

Do NOT implement type checking.

---

## AST Visitor

Implement a reusable visitor abstraction for AST traversal.

Future semantic rules should be implemented using visitors rather than modifying AST classes.

---

## Out of Scope

Do NOT implement:

- Type checking
- Expression analysis
- Procedure flow analysis
- Control-flow graph
- Constant folding
- Dead code detection
- Data-flow analysis
- Cross-reference generation
- Optimization

---

## Files to Create

app/semantic/

    __init__.py
    analyzer.py
    context.py
    diagnostics.py
    symbols.py
    visitors.py

tests/semantic/

    test_semantic_analyzer.py

docs/architecture/

    semantic-analyzer.md

---

## Files to Modify

app/parser/ast/program.py

Only if visitor hooks are required.

---

## Tests

Create tests covering:

- Program registration
- Variable registration
- Paragraph registration
- Duplicate variables
- Duplicate paragraphs
- Empty program
- SemanticContext creation
- Visitor traversal

---

## Documentation

Create:

docs/architecture/semantic-analyzer.md

Document:

- Semantic pipeline
- Visitor architecture
- Symbol table
- Diagnostics
- Future enhancements

---

## Quality Gates

Implementation must pass:

- Ruff
- Black
- MyPy
- Pytest

No parser regressions.

---

## Acceptance Criteria

- SemanticAnalyzer implemented
- SymbolTable implemented
- SemanticContext implemented
- Semantic diagnostics implemented
- Visitor infrastructure implemented
- Tests passing
- Documentation completed