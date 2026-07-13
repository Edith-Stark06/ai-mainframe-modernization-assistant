"""
COPY-book Resolver Sub-package.

Purpose:
    Future home of the COPY-book expansion and cross-reference
    resolver.  This sub-package will locate, read, and inline all
    ``COPY`` and ``COPY … REPLACING`` statements encountered during
    parsing, producing a fully expanded, single-compilation-unit AST.

Responsibilities:
    - Resolve COPY-book member names to file-system paths using a
      configurable search path.
    - Expand ``REPLACING`` clauses with exact text substitution.
    - Detect and report circular COPY dependencies.
    - Track expansion provenance so that diagnostics reference the
      original COPY-book source positions.

Dependencies (future):
    - :mod:`app.parser.lexer`       — token and position types.
    - :mod:`app.parser.ast`         — AST node definitions.
    - :mod:`app.parser.diagnostics` — error reporting.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""
