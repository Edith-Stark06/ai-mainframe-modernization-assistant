# Source Reader Architecture

## Overview

The Source Reader is the first executable component of the COBOL parser
pipeline.

Its sole responsibility is to read a COBOL source file from disk and return
its contents as a plain Python `str`.  The Source Reader performs **no lexical
analysis**, **no format detection**, and **no source normalisation**.

---

## Responsibilities

The Source Reader is responsible for:

- Reading source files from disk via `pathlib.Path`.
- Detecting and decoding supported text encodings (UTF-8, UTF-8 BOM, ASCII).
- Preserving the original source text exactly as read from disk.
- Returning the source as a `str` to the next pipeline stage.
- Raising `SourceReaderError` for missing files or unsupported encodings.

The Source Reader must **not**:

- Detect COBOL source format (fixed, free, or variable).
- Normalise or transform the source text.
- Tokenise the source.
- Parse the source.
- Interpret any COBOL syntax or semantics.

---

## Compiler Pipeline

The Source Reader occupies the first position in the COBOL compiler pipeline:

```
COBOL File  (on disk)
     │
     ▼
Source Reader          ← app.parser.lexer.source_reader  (this component)
     │  returns str
     ▼
Format Detector        ← app.parser.lexer.format_detector (Task-007)
     │
     ▼
Normalizer
     │
     ▼
Scanner
     │
     ▼
Lexer
     │  returns list[Token]
     ▼
Parser
     │  returns AST
     ▼
Semantic Analyser
     │
     ▼
IR Builder
```

Data flows in one direction only.  No stage imports from a stage above it.

---

## Supported Encodings

Version 1 supports the following encodings, probed in this order:

| Encoding      | Codec         | Notes                                      |
|---------------|---------------|--------------------------------------------|
| UTF-8 with BOM | `utf-8-sig`  | BOM is stripped; returned string is BOM-free. |
| UTF-8         | `utf-8`       | The standard Unicode encoding.             |
| ASCII         | `ascii`       | Strict 7-bit ASCII.                        |

Files that cannot be decoded by any of the above codecs raise
`SourceReaderError`.

EBCDIC is **not** supported in this version.

---

## Why Format Detection Is Separate

### Single Responsibility Principle

Each pipeline stage should have exactly one reason to change.

The Source Reader changes only when I/O or encoding support changes (e.g. adding
EBCDIC support).  The Format Detector changes when the rules for classifying
fixed-format versus free-format COBOL change.  Combining them would create a
class that has two reasons to change and two axes of variation.

### Independent Testability

Separating I/O from format logic allows each stage to be tested in isolation:

- `SourceReader` tests need only write bytes to a temporary file.
- `FormatDetector` tests need only supply strings — no filesystem access
  required.

This makes tests faster, more focused, and easier to maintain.

### Clean Contracts

The Source Reader's contract is straightforward: `Path → str`.
The Format Detector's contract is: `str → SourceFormat`.
Each contract is narrow, composable, and easy to mock in tests.

### Alignment with the Broader Pipeline

The pipeline architecture (described in `docs/architecture/parser.md`)
establishes a strict layering rule: every stage receives the output of the
preceding stage and passes its own output to the next.  Format detection
logically sits *between* raw byte reading and normalisation.  Folding it into
the Source Reader would collapse two layers and make the pipeline harder to
extend.

---

## Public API

```python
from pathlib import Path
from app.parser.lexer.source_reader import SourceReader, SourceReaderError

reader = SourceReader()

try:
    source: str = reader.read(Path("program.cbl"))
except SourceReaderError as exc:
    # exc.path    — the offending Path
    # exc.message — human-readable explanation
    ...
```

---

## Error Handling

`SourceReaderError` is raised in two situations:

1. **File not found** — the supplied `Path` does not exist or is not a regular
   file.
2. **Unsupported encoding** — the file's bytes cannot be decoded by any of
   the supported codecs.

The exception carries two attributes:

| Attribute | Type   | Description                     |
|-----------|--------|---------------------------------|
| `path`    | `Path` | The file path that caused the error. |
| `message` | `str`  | Human-readable error description.    |

---

## Design Principles

- **Single Responsibility** — I/O and encoding only.
- **No parser logic** — the Source Reader knows nothing about COBOL.
- **No format detection** — that is Task-007's concern.
- **Immutable output** — the returned `str` is not modified by any side-effect.
- **Structured errors** — typed exceptions carry context for debugging.