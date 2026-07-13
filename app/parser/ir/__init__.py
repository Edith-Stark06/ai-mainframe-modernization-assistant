"""
Intermediate Representation Sub-package.

Purpose:
    Future home of the language-neutral Intermediate Representation
    (IR) generated from a semantically validated COBOL AST.  The IR
    decouples the COBOL-specific front-end from the modernisation
    back-end, enabling analysis, transformation, and code generation
    without traversing raw COBOL syntax trees.

Responsibilities:
    - Define a flat, graph-based IR capturing control flow, data
      flow, and business rule semantics extracted from the AST.
    - Provide serialisation to JSON for persistence and for
      consumption by the RAG and LLM layers.
    - Support incremental updates so that large programs can be
      re-analysed without full recompilation.

Dependencies (future):
    - :mod:`app.parser.ast`         — AST input.
    - :mod:`app.parser.semantic`    — semantic annotations.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""
