"""
Abstract Syntax Tree Sub-package.

Purpose:
    Future home of the COBOL Abstract Syntax Tree (AST) node
    hierarchy.  The AST provides a semantically cleaned, normalised
    representation of a COBOL program stripped of syntactic noise
    (whitespace, redundant keywords, formatting artefacts).

Responsibilities:
    - Define the complete set of AST node types covering all COBOL
      divisions, sections, paragraphs, statements, and expressions.
    - Provide a visitor base class for tree traversal.
    - Remain immutable after construction; all mutation produces new
      nodes.

Dependencies (future):
    - :mod:`app.parser.syntax`      — CST input.
    - :mod:`app.parser.lexer`       — token and position types.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""
