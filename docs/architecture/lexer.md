# COBOL Lexer Architecture

## Overview

The COBOL Lexer is the fifth stage of the compiler pipeline.

It consumes the :class:`CharacterScanner` introduced in Task-009 and converts
the normalized source character stream into an ordered list of immutable
:class:`Token` objects that the Parser will consume.

The Lexer performs **no parsing** and **no semantic analysis**.

---

## Responsibilities

The COBOL Lexer is responsible for:

- Consuming the `CharacterScanner` one character at a time.
- Recognising and classifying the following token categories:
  - COBOL keywords (see keyword list below).
  - User-defined identifiers.
  - Integer numeric literals.
  - Single- and double-quoted string literals.
  - Punctuation and operator symbols.
- Ignoring whitespace (spaces, tabs, newlines).
- Ignoring comment lines and inline comments.
- Preserving the exact source position (`line`, `column`, `offset`) of every
  token's first character.
- Appending a terminal `EOF` token to every token stream.
- Raising `LexerError` for unterminated strings and unrecognised characters.

The Lexer must **not**:

- Parse COBOL grammar.
- Construct an AST.
- Resolve identifiers or perform name lookup.
- Handle COPY book expansion.
- Handle EXEC SQL or EXEC CICS statements.
- Handle continuation lines.

---

## Compiler Pipeline

```
COBOL File  (on disk)
     |
     v
Source Reader              app.parser.lexer.source_reader
     |  returns str
     v
Format Detector            app.parser.lexer.format_detector
     |  returns SourceFormat
     v
Source Normalizer          app.parser.lexer.normalizer
     |  returns normalized str
     v
Character Scanner          app.parser.lexer.scanner
     |  current() / peek() / advance() / eof()
     v
Lexer                      app.parser.lexer.lexer         <- this component
     |  returns list[Token]
     v
Parser                     app.parser.syntax              (future task)
     |  returns AST
     v
Semantic Analyser          app.parser.semantic            (future task)
```

---

## Token Categories

| TokenType    | Examples                                     |
|--------------|----------------------------------------------|
| `KEYWORD`    | `MOVE`, `DISPLAY`, `STOP`, `PROCEDURE`       |
| `IDENTIFIER` | `CUSTOMER-NAME`, `WS-COUNT`, `TOTAL`         |
| `NUMBER`     | `0`, `1`, `100`, `12345`                     |
| `STRING`     | `"HELLO"`, `'WORLD'`                         |
| `PERIOD`     | `.`                                          |
| `COMMA`      | `,`                                          |
| `LPAREN`     | `(`                                          |
| `RPAREN`     | `)`                                          |
| `UNKNOWN`    | `+`, `-`, `*`, `/`, `=`, `<`, `>`, `:`      |
| `EOF`        | *(sentinel — always last)*                   |

Arithmetic and comparison operators are classified as `UNKNOWN` at this
milestone; the Parser will promote them to their specific types when grammar
rules require it.

---

## Recognised Keywords

```
ACCEPT        ADD           CALL          COMPUTE
DATA          DISPLAY       DIVIDE        DIVISION
ELSE          END-IF        ENVIRONMENT   IF
IDENTIFICATION  MOVE        MULTIPLY      PERFORM
PROCEDURE     PROGRAM-ID    RUN           STOP
SUBTRACT      WORKING-STORAGE
```

Keywords are stored in the :mod:`app.parser.lexer.keywords` module as a
`frozenset` for O(1) lookup.

---

## Comment Handling

### Fixed-format comments

After normalisation, the Indicator Area character (originally column 7)
appears at column 1 of each source line. A line whose first character is
`*` is treated as a comment and skipped to the end of the line.

### Free-format comments

The sequence `*>` marks the remainder of a line as a comment.  All characters
from `*>` through the newline (inclusive) are discarded.

---

## Scanner vs. Lexer

| Concern       | Scanner                            | Lexer                                 |
|---------------|------------------------------------|---------------------------------------|
| Abstraction   | Single-character cursor            | Token stream                          |
| State         | Offset, line, column               | Token list being built                |
| Knowledge     | None — pure cursor mechanics       | COBOL grammar for token classification|
| Changes when  | EOF / position semantics change    | Keyword set or token grammar changes  |
| Dependencies  | None (stdlib only)                 | Scanner, Token, TokenType, Keywords   |

Separating the two concerns means:

- The Lexer never needs to worry about newline counting or buffer indexing.
- The Scanner can be tested independently of any COBOL grammar knowledge.
- Both can evolve at different rates without coupling.

---

## Future Parser Integration

The Parser will receive the `list[Token]` produced by the Lexer and apply
COBOL grammar rules.  The Lexer's `EOF` sentinel token gives the Parser a
clean termination condition without requiring null checks.

Token positions (embedded `Position` objects) will allow the Parser and
Semantic Analyser to produce precise diagnostic messages that reference the
original source file, line, and column.

---

## Public API

```python
from app.parser.lexer.lexer import CobolLexer

lexer = CobolLexer()

tokens: list[Token] = lexer.tokenize(
    normalized_source,
    filename="PAYROLL.cbl",   # optional, defaults to "<unknown>"
)
```

---

## Exception Hierarchy

```
Exception
+-- LexerError               app.parser.lexer.lexer_exceptions
```

`LexerError` carries:

| Attribute | Type  | Description                              |
|-----------|-------|------------------------------------------|
| `message` | `str` | Human-readable failure description.      |
| `line`    | `int` | One-based line of the offending token.   |
| `column`  | `int` | One-based column of the offending token. |
| `offset`  | `int` | Zero-based offset of the offending token.|

---

## Design Principles

- **Single Responsibility** — tokenisation only; no parsing or semantics.
- **Stateless** — a single `CobolLexer` instance is safe to reuse.
- **Scanner-driven** — all character access goes through `CharacterScanner`.
- **Immutable output** — every `Token` is a frozen dataclass.
- **Typed errors** — `LexerError` carries position for diagnostics.
- **O(1) keyword lookup** — `frozenset` membership test.
