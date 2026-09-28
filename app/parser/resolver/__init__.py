"""
COPY-book Resolver Sub-package.

Purpose:
    Home of :mod:`app.parser.resolver.copybook` (task #stage45), which
    locates, reads, and inlines every ``COPY`` and ``COPY ... REPLACING``
    statement encountered in a source, producing a single, flattened
    text ready for the existing lexer/parser pipeline.

Responsibilities:
    - Resolve COPY-book member names to file-system paths using a
      configurable search path (see
      :class:`~app.parser.resolver.copybook.CopybookExpander`).
    - Expand ``REPLACING ==...== BY ==...==`` pseudo-text clauses with
      whitespace-tolerant, token-sequence-based text substitution.
    - Detect and report circular COPY dependencies
      (:class:`~app.parser.resolver.copybook.CircularCopyError`).

Non-responsibilities:
    - Cross-file diagnostic provenance -- a diagnostic inside expanded
      copybook content reports its line in the *flattened* text, not
      the copybook's own original file/line; see
      :mod:`app.parser.resolver.copybook`'s own module docstring for why
      this is a deliberate scope decision, not an oversight.
    - The identifier-by-identifier / literal-by-literal ``REPLACING``
      forms, or the standalone ``REPLACE`` statement.

Dependencies:
    - :mod:`app.parser.lexer.lexer`    — ``CobolLexer`` (reused to find
      statement boundaries, never a second hand-rolled scanner).
    - :mod:`app.analysis.service`      — ``AnalysisService.prepare_source``
      (reused to format-detect and normalize each copybook).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.parser.resolver.copybook import (
    CircularCopyError,
    CopybookExpander,
    CopybookNotFoundError,
    MalformedCopyStatementError,
)

__all__ = [
    "CircularCopyError",
    "CopybookExpander",
    "CopybookNotFoundError",
    "MalformedCopyStatementError",
]
