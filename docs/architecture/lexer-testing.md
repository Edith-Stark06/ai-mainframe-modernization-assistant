# COBOL Lexer Testing Strategy

## Overview

This document describes the testing strategy for the COBOL Lexer
(`app.parser.lexer.lexer.CobolLexer`).

Testing is divided into three complementary layers:

| Layer | File | Purpose |
|-------|------|---------|
| Unit tests | `tests/parser/test_lexer.py` | Fine-grained token-level assertions using inline source strings |
| Corpus tests | `tests/parser/test_lexer_corpus.py` | Validate against representative on-disk COBOL programs |
| Regression tests | `tests/parser/test_lexer_regression.py` | Guard specific failure modes across all rule categories |

---

## Corpus Strategy

### Location

```
tests/parser/corpus/
├── identification.cbl       — IDENTIFICATION DIVISION header
├── procedure.cbl            — PROCEDURE DIVISION verbs and operands
├── variables.cbl            — DATA DIVISION / WORKING-STORAGE declarations
├── strings.cbl              — Double and single quoted string literals
├── numbers.cbl              — Integer numeric literals in MOVE statements
├── comments.cbl             — Fixed-format (*) and free-format (*>) comments
├── invalid_characters.cbl   — @ character triggers LexerError
├── unterminated_string.cbl  — Unclosed string literal triggers LexerError
└── mixed_program.cbl        — Full program exercising all token categories
```

### Why file-based corpus?

COBOL programs in the wild are stored as files.  File-based corpus tests
prove that the lexer works when given input that was:

- Written by a human following COBOL column conventions.
- Read from disk with the correct encoding.
- Passed directly to `CobolLexer.tokenize()` without any pre-processing.

This is closer to real production use than inline strings.

### What each corpus file tests

| File | Primary concern | Token types exercised |
|------|----------------|-----------------------|
| `identification.cbl` | Division header keywords | KEYWORD, IDENTIFIER, PERIOD |
| `procedure.cbl` | Verb keywords, operands | KEYWORD, IDENTIFIER, NUMBER, STRING, PERIOD |
| `variables.cbl` | Data names and level numbers | KEYWORD, IDENTIFIER, NUMBER, PERIOD |
| `strings.cbl` | String literals | KEYWORD, STRING, PERIOD |
| `numbers.cbl` | Integer literals | KEYWORD, IDENTIFIER, NUMBER, PERIOD |
| `comments.cbl` | Comment suppression | KEYWORD, IDENTIFIER, STRING, PERIOD |
| `invalid_characters.cbl` | Error path — `@` char | LexerError |
| `unterminated_string.cbl` | Error path — unclosed `"` | LexerError |
| `mixed_program.cbl` | All categories together | All types |

---

## Regression Testing

### Motivation

Regression tests pin the precise behaviour of rules that are easy to break
accidentally:

- A whitespace rule change could cause spaces to appear as tokens.
- A comment rule change could cause comment text to be tokenised.
- A keyword table change could demote a keyword to an identifier.
- A punctuation rule change could misclassify `.` as UNKNOWN.

Each regression test class is named after the rule it protects.

### Categories

| Class | What it protects |
|-------|-----------------|
| `TestWhitespaceRegressions` | Spaces, tabs, CR, LF, CRLF never produce tokens |
| `TestCommentRegressions` | Fixed-format `*` and free-format `*>` comments fully discarded |
| `TestIdentifierRegressions` | Hyphenated names, mixed-case, level-number prefixes |
| `TestKeywordRegressions` | All 22 reserved words classified as KEYWORD (parametrized) |
| `TestPunctuationRegressions` | `.`, `,`, `(`, `)` typed correctly; operators → UNKNOWN |
| `TestStringRegressions` | Quoted literals, empty strings, unterminated-string errors |

### Parametrized keyword tests

The keyword regression suite uses `@pytest.mark.parametrize` to test every
reserved word independently:

```python
@pytest.mark.parametrize("kw", KEYWORDS)
def test_keyword_classified_as_keyword(self, kw: str) -> None:
    assert types(kw) == [TokenType.KEYWORD]
```

This means adding a new keyword to `keywords.py` without adding it to the
parametrize list will immediately highlight the gap.

---

## Invariants Tested Across All Corpus Files

Every corpus file that is expected to tokenise without error must satisfy:

1. **EOF sentinel** — the last token is always `TokenType.EOF`.
2. **Non-decreasing offsets** — token positions increase monotonically.
3. **Filename embedded** — every `Position.filename` matches the filename
   passed to `tokenize()`.
4. **No whitespace tokens** — no token has a lexeme consisting only of
   whitespace.

---

## Future Lexer Expansion

When the lexer gains new capabilities (e.g., COPY handling, EXEC SQL
recognition, continuation lines), the testing strategy extends as follows:

### New corpus files

Add one corpus file per new language feature:

```
tests/parser/corpus/copy_statement.cbl
tests/parser/corpus/exec_sql.cbl
tests/parser/corpus/continuation_lines.cbl
```

### New regression class

Add a `TestCopyRegressions` (or similar) class in
`test_lexer_regression.py` to protect the new rule.

### Pinned token counts

Update `test_lexer_corpus.py` to add the new corpus file's test class with
pinned token counts verified against the live lexer output.

---

## Running the Tests

```bash
# Unit tests only
pytest tests/parser/test_lexer.py -v

# Corpus tests only
pytest tests/parser/test_lexer_corpus.py -v

# Regression tests only
pytest tests/parser/test_lexer_regression.py -v

# All parser tests
pytest tests/parser/ -v

# Full suite
pytest
```
