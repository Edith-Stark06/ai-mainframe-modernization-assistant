# Parser Error Recovery

## Overview

This document describes the panic-mode error recovery system introduced in
**TASK-017** for the AI-Powered Mainframe Modernization Assistant COBOL
recursive-descent parser.

Prior to TASK-017 the parser terminated at the first unrecoverable syntax
error, making it impractical to report more than one problem per parse run.
The recovery system allows the parser to continue after encountering an error,
collect multiple diagnostics, and return a partially-populated AST that
represents as much of the source program as could be understood.

---

## Panic-Mode Recovery

Panic-mode recovery is the simplest and most widely implemented strategy for
error recovery in recursive-descent parsers.

### How It Works

1. **Error detected** — a grammar rule encounters a token it cannot handle.
2. **Diagnostic recorded** — a `SyntaxDiagnostic` is appended to the
   `RecoveryManager`.
3. **Synchronise** — the `synchronise()` function discards tokens from the
   stream until it reaches a *safe restart point*.
4. **Resume** — control returns to the calling grammar rule; parsing continues
   from the synchronisation point.

The key insight is that COBOL's rigid hierarchical structure (program → division
→ section → paragraph → statement) provides natural synchronisation boundaries
that are reliable across a wide variety of syntactically damaged inputs.

---

## Synchronisation Tokens

The synchroniser (`app.parser.diagnostics.recovery.synchronise`) anchors on the
following token classes, in priority order:

| Priority | Anchor | Consumed? | Description |
|----------|--------|-----------|-------------|
| 1 | `PERIOD` (`.`) | **Yes** | Statement terminator; safe to resume after. |
| 2 | Division keyword | No | `IDENTIFICATION`, `DATA`, `PROCEDURE`, `ENVIRONMENT`. Verified by peeking that next token is `DIVISION`. |
| 3 | Section keyword | No | `WORKING-STORAGE`, `LINKAGE`, `FILE`, etc. |
| 4 | Paragraph label | No | An identifier or keyword immediately followed by a `.` that is not a statement keyword. |
| 5 | `EOF` | No | End of stream — final safety net. |

Anchors that are *not consumed* allow the calling grammar rule to re-inspect the
token and dispatch correctly after recovery (e.g. start parsing the DATA
DIVISION header that was found during synchronisation).

---

## Diagnostic Model

### `SyntaxDiagnostic`

An immutable frozen dataclass that records everything about a single recovered
syntax error:

```python
@dataclass(frozen=True, slots=True)
class SyntaxDiagnostic:
    message: str           # human-readable error description
    line: int              # one-based source line
    column: int            # one-based source column
    offset: int            # zero-based byte offset
    filename: str          # originating source file
    context: RecoveryContext
    sync_point: SynchronisationPoint | None  # None if no sync performed
    tokens_skipped: int    # tokens consumed during synchronisation
```

### `RecoveryContext`

Identifies the grammar rule that triggered recovery:

| Value | Meaning |
|-------|---------|
| `identification_division` | Error in IDENTIFICATION DIVISION parser |
| `data_division` | Error in DATA DIVISION parser |
| `procedure_division` | Error in PROCEDURE DIVISION / paragraph parser |
| `working_storage_section` | Error in WORKING-STORAGE SECTION |
| `paragraph` | Error in paragraph body |
| `statement` | Error in statement parser |
| `unknown` | Context not specified |

### `SynchronisationPoint`

Records which anchor the synchroniser stopped at:

| Value | Anchor token |
|-------|-------------|
| `period` | `.` |
| `division` | `X DIVISION` keyword pair |
| `section` | Section keyword |
| `paragraph` | Paragraph label |
| `eof` | End of stream |

---

## Architecture

```
app/parser/
├── diagnostics/
│   ├── __init__.py          ← re-exports all public names
│   └── recovery.py          ← SyntaxDiagnostic, RecoveryContext,
│                               SynchronisationPoint, RecoveryManager,
│                               synchronise()
└── syntax/
    ├── parser_state.py      ← extended: record_and_synchronise(),
    │                           diagnostics, recovery_manager, in_recovery
    ├── identification_parser.py  ← recovery-aware
    ├── data_parser.py            ← recovery-aware
    └── procedure_parser.py       ← recovery-aware
```

### Component Responsibilities

#### `synchronise(stream: TokenStream) → (SynchronisationPoint, int)`

Low-level function. Advances the stream until a synchronisation anchor is
found and returns `(anchor, tokens_skipped)`. Stateless.

#### `RecoveryManager`

Stateful accumulator for a single parse pass. Grammar rules call it via
`ParserState`; it holds the `_diagnostics` list and the `_in_recovery` re-
entrant guard.

#### `ParserState` extensions

```
ParserState
├── record_and_synchronise(message, error_token, context)
│   └─→ RecoveryManager.record_and_synchronise(stream, ...)
├── diagnostics: list[SyntaxDiagnostic]  (property, defensive copy)
├── recovery_manager: RecoveryManager    (for advanced callers)
├── in_recovery: bool                    (proxy to manager)
└── record_error()                       ← backward-compatible legacy method
```

`error_count` is the sum of legacy errors (from `record_error()`) and
structured diagnostics (from `record_and_synchronise()`), preserving backward
compatibility for callers that check only the count.

---

## Parser Flow

### Before TASK-017

```
Grammar rule
    → bad token
    → raise ParserError  ← parse aborts here, single error reported
```

### After TASK-017

```
Grammar rule
    → bad token
    → state.record_and_synchronise(message, token, context)
        ├── RecoveryManager builds SyntaxDiagnostic (partial)
        ├── synchronise(stream)
        │     ├── skip tokens ...
        │     └── stop at anchor (PERIOD / DIVISION / SECTION / PARAGRAPH / EOF)
        └── diagnostic completed with sync_point + tokens_skipped
    → grammar rule resumes from synchronisation point
    → ... next grammar iteration ...
    → (another bad token)
    → state.record_and_synchronise(...)
    → ...
    → EOF
    → state.diagnostics  ← full list of all recovered errors
```

### Fatal vs Recoverable Errors

Not every error can be recovered from.  Division headers (e.g. the
`IDENTIFICATION DIVISION .` opening line) are still **fatal** — if the
header is malformed, the parser cannot know what structure it is inside
and raises `ParserError` immediately.

| Condition | Recoverable | Action |
|-----------|-------------|--------|
| Unknown clause keyword in IDENTIFICATION DIVISION | ✓ | `record_and_synchronise()` → sync to next period |
| Invalid level number in DATA DIVISION | ✓ | `record_and_synchronise()` → sync to next period |
| Missing period after paragraph label | ✓ | `record_and_synchronise()` → sync to next period |
| Malformed statement (missing operand) | ✓ | `record_and_synchronise()` → sync to next period |
| Missing `IDENTIFICATION` keyword | ✗ | `raise ParserError` |
| Missing `DATA` keyword | ✗ | `raise ParserError` |
| Missing `PROCEDURE` keyword | ✗ | `raise ParserError` |

---

## Implementation Files

| File | Change |
|------|--------|
| `app/parser/diagnostics/recovery.py` | **New** — full recovery utilities |
| `app/parser/diagnostics/__init__.py` | Updated — re-exports recovery API |
| `app/parser/syntax/parser_state.py` | Extended — `RecoveryManager` integration |
| `app/parser/syntax/identification_parser.py` | Updated — clause-level recovery |
| `app/parser/syntax/data_parser.py` | Updated — data-item-level recovery |
| `app/parser/syntax/procedure_parser.py` | Updated — statement-level recovery |
| `tests/parser/test_parser_recovery.py` | **New** — comprehensive test suite |

---

## Out of Scope

The following are explicitly **not** implemented by this recovery system:

- Semantic diagnostics (undefined identifiers, type mismatches).
- Warning-level diagnostics (deprecated constructs, style issues).
- Symbol resolution.
- Automatic source correction.
- IDE / LSP integration (hover, completion, go-to-definition).
- Reporting diagnostics through the HTTP API.

---

## Testing Strategy

Tests are organised into five categories in `tests/parser/test_parser_recovery.py`:

1. **`SyntaxDiagnostic` unit tests** — construction, equality, immutability, str.
2. **`RecoveryManager` unit tests** — accumulation, re-entrant guard, no-sync path.
3. **`synchronise()` unit tests** — all five anchor types, skipped-token counting.
4. **`ParserState` extension tests** — backward-compat, merged error_count.
5. **Per-division recovery tests** — recoverable vs fatal errors, context values.
6. **End-to-end integration tests** — multi-division programs, diagnostic ordering.

All quality gates must pass before merging:

```
ruff check .
black --check .
mypy app
pytest
```

---

## Future Enhancements

| Enhancement | Notes |
|-------------|-------|
| Phrase-level recovery | Skip to a specific clause keyword (e.g. skip to `PIC` if data-name is missing). |
| Error grouping | Suppress cascading errors triggered by a single root cause. |
| Diagnostic severity levels | Distinguish errors from warnings when semantic analysis is added. |
| LSP integration | Surface `SyntaxDiagnostic` records as LSP `Diagnostic` objects. |
| Recovery statistics | Track synchronisation frequency per grammar rule for parser quality metrics. |
| Configurable max errors | Abort parse after N errors to prevent noise in very broken files. |
