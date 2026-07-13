"""
COBOL Parser Package.

Purpose:
    Provide a layered compiler architecture for the COBOL
    understanding engine of the AI-Powered Mainframe Modernization
    Assistant.  This package is the root namespace for all COBOL
    source analysis: lexical analysis, syntax analysis, semantic
    analysis, intermediate representation, and diagnostics.

Responsibilities:
    - Organise parser sub-packages by compiler stage so that each
      layer can evolve independently without coupling concerns.
    - Re-export top-level symbols that are required by application
      services, keeping downstream import paths stable.
    - Enforce the architectural constraint that no parser component
      imports from ``app.api`` or ``app.services``; data flows
      upward only.

Sub-packages:
    lexer:
        Lexical analysis layer.  Transforms raw COBOL source text
        into a flat sequence of :class:`~app.parser.lexer.Token`
        objects.  See :mod:`app.parser.lexer`.
    syntax:
        Syntax analysis layer (future).  Consumes the token stream
        and constructs a Concrete Syntax Tree.
    ast:
        Abstract Syntax Tree layer (future).  Provides a cleaned,
        normalised tree representation of the COBOL program structure.
    resolver:
        COPY-book and cross-reference resolver (future).  Expands
        ``COPY`` statements and resolves symbolic references.
    semantic:
        Semantic analysis layer (future).  Enforces data-type rules,
        scope resolution, and COBOL division/section constraints.
    ir:
        Intermediate Representation layer (future).  Translates the
        AST into a language-neutral IR suitable for modernisation
        analysis and code generation.
    diagnostics:
        Diagnostic collection and reporting (future).  Aggregates
        parser errors, warnings, and hints and formats them for IDE
        and API consumers.

Dependencies:
    - :mod:`app.parser.lexer` — lexer foundation (current milestone).

Examples:
    Importing the lexer public API via the parser namespace::

        from app.parser.lexer import ILexer, Position, Token, TokenType

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""
