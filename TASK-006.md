# TASK-006 — Implement COBOL Source Reader

## Milestone

Phase 4 — COBOL Understanding Engine

---

# Objective

Implement the Source Reader component.

The Source Reader is the first executable component in the COBOL parser pipeline.

Its responsibility is to read COBOL source files from disk and return the source as a string.

This task intentionally does NOT perform format detection because that functionality is implemented in Task-007.

---

# Scope

Implement only

```
app/parser/lexer/source_reader.py
```

No other parser modules shall be created or modified.

---

# Public API

```python
class SourceReader:

    def read(
        self,
        path: Path,
    ) -> str:
        ...
```

---

# Responsibilities

The Source Reader shall

- Read source files
- Support UTF-8
- Support UTF-8 BOM
- Support ASCII
- Preserve the original source exactly
- Return the source as a string

---

# Supported Encodings

Version 1

- UTF-8
- UTF-8 BOM
- ASCII

Unsupported encodings shall raise an exception.

Do NOT implement EBCDIC.

---

# Tests

Create

```
tests/parser/test_source_reader.py
```

Cover

- UTF-8
- UTF-8 BOM
- ASCII
- Missing file
- Unsupported encoding

---

# Documentation

Create

```
docs/architecture/source-reader.md
```

Describe

- responsibilities
- compiler pipeline
- why Source Reader does not perform format detection

---

# Requirements

The following must pass

```
black --check .

ruff check .

mypy app

pytest
```

---

# Out of Scope

Do NOT implement

- SourceDocument
- SourceFormat
- FormatDetector
- Scanner
- Lexer
- Parser
- AST
- COPY
- EXEC SQL
- Normalizer

---

# Deliverables

Expected Commit

```
feat(parser): implement source reader
```

Expected Pull Request

```
feat(parser): implement COBOL source reader
```

---

# Definition of Done

✔ SourceReader implemented

✔ Tests added

✔ Documentation added

✔ No parser logic introduced

✔ No merge conflicts with Task-007