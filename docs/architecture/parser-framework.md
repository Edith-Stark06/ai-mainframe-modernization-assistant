# Parser Framework Architecture

## Overview

The Parser Framework establishes the structural foundation for converting a flat
sequence of COBOL lexer tokens into a hierarchical Abstract Syntax Tree (AST).

This component sits immediately downstream of the Lexer and immediately upstream
of the grammar rules that will recognise COBOL divisions, sections, paragraphs,
and statements.

```
Lexer (list[Token])
     |
     v
TokenStream          — cursor-based navigation abstraction
     |
     v
ParserState          — mutable bookkeeping (position, error count)
     |
     v
CobolParser          — grammar entry point  →  ProgramNode (AST root)
```

---

## Recursive Descent Architecture

The COBOL parser follows the **recursive descent** strategy: each grammar rule
maps to one private method on `CobolParser`.  The top-level rule is
`_parse_program()`; it will later call `_parse_identification_division()`,
`_parse_data_division()`, and so on.

### Why recursive descent?

| Property | Benefit |
|----------|---------|
| Readability | Each method mirrors a grammar rule — easy to trace |
| Error recovery | Methods can skip tokens and record errors without unwinding the stack |
| Debuggability | Stack traces directly reflect the grammar path taken |
| Extensibility | New rules are new methods — no generated code or tables |

---

## Token Stream Abstraction

`TokenStream` wraps a `list[Token]` and exposes **only** the navigation
primitives the parser needs.  The parser **never** accesses the token list
directly.

```python
from app.parser.syntax.token_stream import TokenStream

stream = TokenStream(tokens)

stream.current()        # Token at the cursor (read without consuming)
stream.peek(offset=1)   # Look ahead by `offset` positions (default 1)
stream.advance()        # Consume and return the current token
stream.eof()            # True when the cursor is on the EOF sentinel
stream.expect(ttype)    # Consume if type matches, else raise an error
stream.position         # Zero-based cursor index (int)
```

### Design invariants

- The token list **must** end with exactly one `TokenType.EOF` sentinel.
- Advancing past EOF keeps the cursor on EOF — the stream never goes out of bounds.
- `peek()` beyond the end returns the EOF sentinel so callers never receive
  `IndexError`.

---

## Parser State

`ParserState` is a lightweight container that wraps a `TokenStream` and adds
an error counter.

```python
from app.parser.syntax.parser_state import ParserState

state = ParserState(stream)

state.current_token     # delegates to stream.current()
state.position          # delegates to stream.position
state.stream            # direct access to the TokenStream
state.error_count       # number of errors recorded
state.has_errors        # True when error_count > 0
state.record_error()    # increment error_count by 1
```

### Why separate state from the parser?

Grammar methods on `CobolParser` receive `state` as their sole argument.
This makes each method a pure function of its input (modulo the mutable
counter), enabling targeted unit tests without constructing a full parser.

---

## Parser Entry Point

```python
from app.parser.syntax.parser import CobolParser

parser = CobolParser()
program_node = parser.parse(tokens)
```

`CobolParser` satisfies
[`ParserProtocol`](file:///app/parser/syntax/parser_interfaces.py) structurally,
so it can be passed wherever the protocol is expected without explicit
inheritance.

### Current behaviour (framework only)

`parse()` currently returns an empty `ProgramNode` — all four division fields
are `None`.  Grammar rules will be added in subsequent tasks.

### Sequence diagram

```
caller
  │
  │  parse(tokens)
  ▼
CobolParser
  │  TokenStream(tokens)
  │  ParserState(stream)
  │  _parse_program(state)
  │    return ProgramNode(start, end)
  │
  ▼
ProgramNode (all divisions None)
```

---

## Error Hierarchy

```
Exception
└── ParserError                     parser_exceptions.py   (TASK-012)
    ├── UnexpectedTokenError        parser_errors.py
    └── UnexpectedEOFError          parser_errors.py
```

### UnexpectedTokenError

Raised by `TokenStream.expect()` when the current token's type does not match
the expected type.

```python
from app.parser.syntax.parser_errors import UnexpectedTokenError
from app.parser.lexer.token_types import TokenType

raise UnexpectedTokenError(
    found_lexeme="MOVE",
    found_type=TokenType.KEYWORD,
    expected_type=TokenType.PERIOD,
    line=10,
    column=5,
    offset=200,
)
```

Attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `found_lexeme` | `str` | The raw text of the offending token |
| `found_type` | `TokenType` | The actual token type |
| `expected_type` | `TokenType \| None` | What the parser expected |
| `line` | `int` | One-based line number |
| `column` | `int` | One-based column number |
| `offset` | `int` | Zero-based byte offset |

### UnexpectedEOFError

Raised by `TokenStream.expect()` when the stream is on the EOF sentinel but
the grammar rule required more tokens.

```python
from app.parser.syntax.parser_errors import UnexpectedEOFError

raise UnexpectedEOFError(line=42, column=1, offset=999)
```

---

## Future Grammar Parsers

The framework is designed to accommodate grammar rules with zero structural
changes.  Each future rule follows this pattern:

```python
class CobolParser:

    def _parse_identification_division(
        self, state: ParserState
    ) -> DivisionNode | None:
        """
        IDENTIFICATION DIVISION .
        """
        if state.current_token.type is not TokenType.KEYWORD:
            return None
        if state.current_token.lexeme.upper() != "IDENTIFICATION":
            return None

        start = state.current_token.position
        state.stream.expect(TokenType.KEYWORD)   # IDENTIFICATION
        state.stream.expect(TokenType.KEYWORD)   # DIVISION
        state.stream.expect(TokenType.PERIOD)    # .

        return DivisionNode(
            start_position=start,
            end_position=state.current_token.position,
            name="IDENTIFICATION",
            children=(),
        )
```

### Planned grammar method hierarchy

```
_parse_program()
├── _parse_identification_division()
├── _parse_environment_division()
├── _parse_data_division()
│   └── _parse_data_record()
│       └── _parse_level_entry()
└── _parse_procedure_division()
    └── _parse_section()
        └── _parse_paragraph()
            └── _parse_statement()
```

---

## Design Principles

- **Abstraction** — the parser never touches raw token lists; all access is
  through `TokenStream`.
- **Separation of concerns** — navigation (`TokenStream`), bookkeeping
  (`ParserState`), and grammar (`CobolParser`) are three distinct classes.
- **Immutability** — AST nodes are frozen dataclasses; the only mutable state
  is the cursor and error counter in `ParserState`.
- **Composability** — grammar methods are small, single-rule functions that
  compose to handle the full COBOL structure.
- **Structural protocol** — `CobolParser` satisfies `ParserProtocol` without
  explicit inheritance, keeping the AST layer decoupled from this module.
