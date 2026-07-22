# TASK-011 — COBOL Lexer Validation & Test Corpus

## Milestone

Phase 4 — COBOL Understanding Engine

---

# Objective

Validate the COBOL Lexer using a representative COBOL source corpus.

No production lexer logic shall be modified.

This task increases confidence that the lexer behaves correctly across
real-world COBOL source files.

---

# Scope

Create

tests/parser/

test_lexer_corpus.py

test_lexer_regression.py

tests/parser/corpus/

multiple sample COBOL programs

docs/architecture/lexer-testing.md

---

# Corpus

Create representative COBOL samples.

Include

- Identification Division
- Procedure Division
- Variable declarations
- String literals
- Integer literals
- Comments
- Invalid characters
- Unterminated strings
- Mixed COBOL program

---

# Corpus Tests

Verify

- token count
- token ordering
- keyword recognition
- identifier recognition
- string recognition
- integer recognition
- EOF generation

---

# Regression Tests

Protect against

- whitespace regressions
- comment regressions
- identifier regressions
- keyword regressions
- punctuation regressions

---

# Documentation

Create

docs/architecture/lexer-testing.md

Explain

- corpus strategy
- regression testing
- future lexer expansion

---

# Requirements

Pass

black --check .

ruff check .

mypy app

pytest

---

# Out of Scope

Do NOT modify

lexer.py

scanner.py

normalizer.py

source_reader.py

No parser logic.

No AST.

---

# Expected Commit

feat(parser): add lexer validation corpus

---

# Expected Pull Request

feat(parser): add lexer validation corpus

---

# Definition of Done

✔ Corpus created

✔ Regression tests added

✔ Existing lexer unchanged

✔ All tests passing