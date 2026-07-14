# Source Normalizer Architecture

## Overview

The Source Normalizer is the third stage of the COBOL compiler pipeline.

It receives the raw source text produced by the Source Reader, together with
the :class:`SourceFormat` value determined by the Format Detector, and returns
a *normalized* source string that downstream stages (Character Scanner, Lexer,
Parser) can process without needing to understand column-position semantics.

The Normalizer performs **no lexical analysis** and **no semantic interpretation**.

---

## Responsibilities

### For FIXED format source

The COBOL ANSI reference format (fixed format) imposes a strict column layout
on every source line:

| Columns | Area                  | Action              |
|---------|-----------------------|---------------------|
| 1–6     | Sequence Number Area  | **Strip** (removed) |
| 7       | Indicator Area        | **Preserve**        |
| 8–11    | Area A                | **Preserve**        |
| 12–72   | Area B                | **Preserve**        |
| 73–80   | Program-ID / Card-ID  | **Strip** (removed) |

After normalization each fixed-format line contains only the content that was
in columns 7–72 (up to 66 characters), with its original line terminator
(`\n`, `\r\n`, or bare `\r`) preserved verbatim.

### For FREE format source

Free-format COBOL (introduced in COBOL 2002) imposes no column restrictions.
The Normalizer returns the source string **unchanged**.

### Error handling

The Normalizer raises `NormalizationError` when:

- The `source` argument is not a `str` (bytes, `None`, etc.).
- The `source_format` is `SourceFormat.UNKNOWN` (the Format Detector was
  unable to classify the file).

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
Source Normalizer          app.parser.lexer.normalizer   <- this component
     |  returns normalized str
     v
Character Scanner          app.parser.lexer.scanner      (future task)
     |
     v
Lexer                      app.parser.lexer.lexer        (future task)
     |  returns list[Token]
     v
Parser                     app.parser.syntax             (future task)
```

Data flows in one direction only. No stage imports from a stage above it.

---

## Why Normalization Precedes Scanning

### Column semantics are a physical artefact, not a semantic concern

COBOL's column layout is an artefact of the IBM 80-column punch card. The
Scanner and Lexer should not need to know whether they are processing a
fixed-format or free-format file; they should operate on a uniform character
stream. Normalizing first removes this concern from all downstream stages.

### Separation of concerns

Each stage should have exactly one reason to change:

| Stage      | Changes when...                                            |
|------------|------------------------------------------------------------|
| Normalizer | Column layout rules change (e.g. adding EBCDIC support).   |
| Scanner    | Character classification rules change.                     |
| Lexer      | Token grammar changes.                                     |

If the Scanner also stripped sequence numbers, any change to column rules
would require modifying two stages simultaneously.

### Independent testability

Because the Normalizer is a pure `str -> str` transformation, its tests need
no filesystem access, no lexer, and no parser. The Scanner can be tested
against pre-normalized strings, keeping test fixtures clean and maintainable.

### Clean contract

The Normalizer's contract is narrow and composable:

```
normalize(source: str, source_format: SourceFormat) -> str
```

Any caller that has a `str` and a `SourceFormat` can use it directly.

---

## Public API

```python
from app.parser.lexer.normalizer import SourceNormalizer
from app.parser.lexer.source_format import SourceFormat

normalizer = SourceNormalizer()

# Fixed format -- sequence numbers and card-ID columns are stripped.
normalized: str = normalizer.normalize(raw_source, SourceFormat.FIXED)

# Free format -- source is returned unchanged.
normalized: str = normalizer.normalize(raw_source, SourceFormat.FREE)
```

---

## Exception Hierarchy

```
Exception
+-- ParserError                  app.parser.lexer.exceptions
    +-- NormalizationError       app.parser.lexer.exceptions
```

`NormalizationError` is raised when the Normalizer cannot process its input.
Callers that want to catch all pipeline errors can use `except ParserError`.

---

## Design Principles

- **Single Responsibility** -- column stripping only; no lexical analysis.
- **Stateless** -- a single `SourceNormalizer` instance is safe to reuse.
- **Typed errors** -- structured exceptions carry `.message` for diagnostics.
- **No regex** -- column arithmetic is performed with simple string slicing.
- **No third-party dependencies** -- stdlib only.
