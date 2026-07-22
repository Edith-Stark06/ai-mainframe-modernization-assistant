# TASK-009 — Implement Character Scanner

## Milestone

Phase 4 — COBOL Understanding Engine

---

# Objective

Implement the Character Scanner.

The scanner consumes normalized COBOL source text and exposes a
character-by-character interface for the lexer.

It performs NO lexical analysis.

---

# Scope

Implement only

```
app/parser/lexer/scanner.py

app/parser/lexer/scanner_exceptions.py
```

---

# Public API

```python
class CharacterScanner:

    def __init__(self, source: str):
        ...

    def current(self) -> str | None:
        ...

    def peek(self, offset: int = 1) -> str | None:
        ...

    def advance(self) -> str | None:
        ...

    def eof(self) -> bool:
        ...

    @property
    def line(self) -> int:
        ...

    @property
    def column(self) -> int:
        ...

    @property
    def offset(self) -> int:
        ...
```

---

# Responsibilities

The Character Scanner shall

- Read one character at a time
- Support lookahead
- Track current position
- Track line number
- Track column number
- Track absolute offset
- Detect EOF

The scanner shall NOT

- recognize keywords
- recognize identifiers
- create tokens
- parse COBOL

---

# Position Tracking

Track

```
line

column

offset
```

Newline handling

```
line += 1

column = 1
```

---

# Exceptions

Create

```
ScannerError
```

Use typed exceptions.

---

# Tests

Create

```
tests/parser/test_scanner.py
```

Test

- empty source
- single character
- multiple characters
- newline handling
- peek()
- advance()
- eof()
- line tracking
- column tracking
- offset tracking

---

# Documentation

Create

```
docs/architecture/scanner.md
```

Explain

- responsibilities
- compiler pipeline
- why scanner is independent of lexer

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

# Out of Scope

Do NOT implement

- Token creation
- Keyword recognition
- Numbers
- Strings
- Lexer
- Parser
- AST
- COPY
- EXEC SQL

---

# Expected Commit

```
feat(parser): implement character scanner
```

---

# Expected Pull Request

```
feat(parser): implement character scanner
```

---

# Definition of Done

✔ CharacterScanner implemented

✔ Position tracking implemented

✔ Lookahead implemented

✔ EOF detection implemented

✔ Tests passing

✔ Documentation added

✔ No lexer logic introduced