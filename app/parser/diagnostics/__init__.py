"""
Diagnostics Sub-package.

Purpose:
    Future home of the compiler diagnostic collection and reporting
    layer.  All parser components emit structured
    :class:`Diagnostic` records rather than raising exceptions for
    recoverable errors, enabling the parser to continue past the
    first error and deliver a complete error report.

Responsibilities:
    - Define the ``Diagnostic`` model carrying severity, code,
      message, and source :class:`~app.parser.lexer.Position`.
    - Provide a ``DiagnosticSink`` that accumulates diagnostics
      during a parse pass.
    - Format diagnostics for IDE Language Server Protocol (LSP)
      responses and JSON API payloads.

Dependencies (future):
    - :mod:`app.parser.lexer` — ``Position`` value type.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""
