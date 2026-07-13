"""
Semantic Analysis Sub-package.

Purpose:
    Future home of the COBOL semantic analyser.  This sub-package
    validates program correctness beyond what can be determined by
    syntactic structure alone: data-type compatibility, scope
    rules, valid PERFORM targets, and division-specific constraints.

Responsibilities:
    - Enforce COBOL data-type and usage-clause compatibility rules.
    - Resolve paragraph and section references within PERFORM
      statements.
    - Validate that all referenced data names are declared in the
      Data Division.
    - Annotate the AST with semantic metadata consumed by downstream
      IR generation.

Dependencies (future):
    - :mod:`app.parser.ast`         — AST input.
    - :mod:`app.parser.resolver`    — resolved symbol table.
    - :mod:`app.parser.diagnostics` — error and warning reporting.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""
