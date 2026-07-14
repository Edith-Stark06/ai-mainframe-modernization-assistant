# Character Scanner Architecture

## Overview

The Character Scanner is the fourth stage of the COBOL compiler pipeline.

It receives normalized COBOL source text from the Source Normalizer and
exposes a character-by-character cursor interface that the Lexer uses to
consume source text one character at a time.

The scanner performs **no lexical analysis** and **no COBOL interpretation**.

---

## Responsibilities

The Character Scanner is responsible for:

- Iterating over normalized source text one character at a time.
- Providing the current character without advancing the cursor.
- Supporting configurable lookahead without advancing the cursor.
- Advancing the cursor and returning the newly current character.
- Tracking the absolute byte offset (zero-based).
- Tracking the current line number (one-based).
- Tracking the current column number (one-based).
- Correctly handling LF (`\n`), bare CR (`\r`), and CRLF (`\r\n`) newlines.
- Detecting and signalling end-of-input.

The Character Scanner must **not**:

- Recognize keywords or identifiers.
- Create tokens of any kind.
- Perform lexical analysis.
- Parse COBOL.

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
Character Scanner          app.parser.lexer.scanner      <- this component
     |  exposes current() / peek() / advance() / eof()
     v
Lexer                      app.parser.lexer.lexer        (future task)
     |  returns list[Token]
     v
Parser                     app.parser.syntax             (future task)
```

Data flows in one direction only. No stage imports from a stage above it.

---

## Public API

```python
from app.parser.lexer.scanner import CharacterScanner

scanner = CharacterScanner(normalized_source)

# Read current character without advancing.
ch: str | None = scanner.current()

# Look ahead without advancing.
next_ch: str | None = scanner.peek()        # 1 position ahead (default)
after_next: str | None = scanner.peek(2)    # 2 positions ahead

# Advance the cursor and return the new current character.
ch = scanner.advance()

# Check for end of input.
if scanner.eof():
    ...

# Position information.
offset: int = scanner.offset   # 0-based absolute index
line: int   = scanner.line     # 1-based line number
column: int = scanner.column   # 1-based column number
```

---

## Position Tracking

### Initial state

| Counter  | Initial value | Meaning                    |
|----------|---------------|----------------------------|
| `offset` | `0`           | Points to the first character |
| `line`   | `1`           | First line                 |
| `column` | `1`           | First column               |

### Newline rules

When `advance()` consumes a newline character the counters are updated as
follows:

| Sequence | Effect                                              |
|----------|-----------------------------------------------------|
| `\n`     | `line += 1`, `column = 1`                           |
| `\r`     | `line += 1`, `column = 1` (and sets CR-seen flag)   |
| `\r\n`   | `\r` increments `line`; the `\n` is absorbed (no double-count) |

Any other character increments `column` only.

---

## Why the Scanner Is Independent of the Lexer

### Single Responsibility Principle

The Scanner's only job is to move a cursor over characters and report
positions. The Lexer's job is to group characters into tokens according to
COBOL grammar rules. These are distinct concerns that change for different
reasons:

| Component | Changes when…                                           |
|-----------|---------------------------------------------------------|
| Scanner   | Position-tracking or EOF semantics change.              |
| Lexer     | COBOL token grammar or keyword set changes.             |

Combining them would create a class with two reasons to change.

### Independent Testability

Because the Scanner is a pure cursor — `str -> (char, position)*` — its
tests need no knowledge of COBOL tokens. Scanner tests are fast, focused,
and easy to read. Lexer tests can use a pre-constructed scanner without
worrying about position tracking.

### Composability

The Scanner interface (`current`, `peek`, `advance`, `eof`) is the minimal
contract a Lexer needs from a character source. This makes it easy to:

- Replace the scanner with a different implementation (e.g., one backed by
  a file stream) without changing the Lexer.
- Test the Lexer against mock scanners.

---

## Exception Hierarchy

```
Exception
+-- ScannerError               app.parser.lexer.scanner_exceptions
```

`ScannerError` is raised when the scanner is constructed with invalid input
(e.g. a `bytes` object instead of `str`) or when `peek()` is called with a
negative offset.

---

## Design Principles

- **Single Responsibility** -- cursor management only, no lexical analysis.
- **Stateless lookahead** -- `peek()` never modifies internal state.
- **Typed errors** -- `ScannerError` carries `.message` for diagnostics.
- **No regex** -- position arithmetic uses integer indexing only.
- **No third-party dependencies** -- stdlib only (plus Loguru for debug).
