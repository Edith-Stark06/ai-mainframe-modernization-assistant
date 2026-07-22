# TASK-010 — Implement COBOL Lexer

## Milestone

Phase 4 — COBOL Understanding Engine

---

# Objective

Implement the first version of the COBOL Lexer.

The lexer converts a stream of characters into immutable Token objects.

It consumes the CharacterScanner introduced in Task-009.

This task performs NO parsing.

---

# Scope

Implement only

```
app/parser/lexer/lexer.py

app/parser/lexer/keywords.py

app/parser/lexer/lexer_exceptions.py
```

---

# Responsibilities

The lexer shall

- Consume CharacterScanner
- Produce Token objects
- Preserve token positions
- Skip whitespace
- Skip comments

---

# Recognize

## COBOL Keywords

Recognize

```
IDENTIFICATION
DIVISION
PROGRAM-ID
ENVIRONMENT
DATA
PROCEDURE
WORKING-STORAGE
MOVE
ADD
SUBTRACT
MULTIPLY
DIVIDE
DISPLAY
STOP
RUN
IF
ELSE
END-IF
PERFORM
CALL
ACCEPT
COMPUTE
```

---

## Identifiers

Recognize

```
CUSTOMER-NAME
WS-COUNT
TOTAL
PAYROLL-RECORD
```

---

## Numeric Literals

Recognize

```
0
1
100
12345
```

Integers only.

No decimals.

---

## String Literals

Recognize

```
"HELLO"

'WORLD'
```

No multiline strings.

---

## Symbols

Recognize

```
.
,
(
)
:
+
-
*
/
=
<
>
```

---

# Ignore

Whitespace

Comments

---

# Output

Return

```
list[Token]
```

---

# Exceptions

Create

```
LexerError
```

Raise on

- unterminated strings
- invalid characters

---

# Tests

Create

```
tests/parser/test_lexer.py
```

Cover

- keywords
- identifiers
- numbers
- strings
- symbols
- comments
- whitespace
- invalid tokens
- unterminated strings

---

# Documentation

Create

```
docs/architecture/lexer.md
```

Explain

- scanner vs lexer
- tokenization pipeline
- future parser integration

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

# Explicitly Out of Scope

Do NOT implement

- parser
- AST
- COPY
- EXEC SQL
- EXEC CICS
- continuation lines
- semantic analysis

---

# Expected Commit

```
feat(parser): implement COBOL lexer
```

---

# Expected Pull Request

```
feat(parser): implement COBOL lexer
```

---

# Definition of Done

✔ Lexer implemented

✔ Keywords recognized

✔ Identifiers recognized

✔ Numbers recognized

✔ Strings recognized

✔ Symbols recognized

✔ Token positions preserved

✔ Tests passing

✔ Documentation complete