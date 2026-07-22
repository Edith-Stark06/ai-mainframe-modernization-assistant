# TASK-008 — Implement COBOL Source Normalizer

## Milestone

Phase 4 — COBOL Understanding Engine

---

# Objective

Implement the COBOL Source Normalizer.

The normalizer converts raw COBOL source into normalized source suitable for the Character Scanner.

It removes formatting concerns while preserving semantic content.

This task performs NO lexical analysis.

---

# Scope

Implement only

```
app/parser/lexer/normalizer.py

app/parser/lexer/exceptions.py
```

No additional parser modules.

---

# Public API

```python
class SourceNormalizer:

    def normalize(
        self,
        source: str,
        source_format: SourceFormat,
    ) -> str:
        ...
```

---

# Responsibilities

For FIXED format

- Remove columns 1–6 (sequence numbers)
- Ignore columns 73–80
- Preserve Area A and Area B
- Preserve line order

For FREE format

Return source unchanged.

---

# Do NOT Implement

Do NOT implement

- continuation line handling
- COPY expansion
- REPLACE
- EXEC SQL
- EXEC CICS
- scanner
- lexer
- parser

Those belong to future tasks.

---

# Exceptions

Create

```
NormalizationError
```

Use typed exceptions.

---

# Tests

Create

```
tests/parser/test_normalizer.py
```

Cover

- Fixed format
- Free format
- Empty source
- Invalid input
- Sequence numbers removed
- Identification columns ignored

---

# Documentation

Create

```
docs/architecture/normalizer.md
```

Explain

- responsibilities
- compiler pipeline
- why normalization precedes scanning

---

# Requirements

Pass

```
black --check .

ruff check .

mypy app

pytest
```

---

# Expected Commit

```
feat(parser): implement source normalizer
```

---

# Expected PR

```
feat(parser): implement COBOL source normalizer
```

---

# Definition of Done

✔ SourceNormalizer implemented

✔ Typed exceptions implemented

✔ Tests added

✔ Documentation added

✔ No scanner logic

✔ No lexer logic