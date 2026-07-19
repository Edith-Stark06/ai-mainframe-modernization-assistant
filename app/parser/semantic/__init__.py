"""
Semantic Analysis Sub-package.

Purpose:
    Implement the semantic analysis stage of the COBOL compiler pipeline.
    This sub-package validates program correctness beyond what can be
    determined by syntactic structure alone: symbol registration, scope
    rules, and structural constraint checking.

    The semantic analysis pipeline receives an AST produced by the parser,
    builds a :class:`~app.parser.semantic.context.SymbolTable`, detects
    duplicate symbol declarations, and returns an immutable
    :class:`~app.parser.semantic.context.SemanticContext` for consumption
    by downstream stages (IR generation, RAG, modernisation).

Responsibilities:
    - Register program, variable, and paragraph symbols.
    - Detect duplicate variable and paragraph declarations.
    - Provide a reusable :class:`~app.parser.semantic.visitors.SemanticVisitor`
      base for future semantic rules.
    - Return a populated :class:`~app.parser.semantic.context.SemanticContext`
      from :meth:`~app.parser.semantic.analyzer.SemanticAnalyzer.analyse`.

Non-responsibilities (intentionally deferred):
    - Type checking and expression analysis.
    - Control-flow and data-flow analysis.
    - Constant folding and optimisation.
    - Cross-reference generation.

Public API:
    - :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`   — primary analysis entry point.
    - :class:`~app.parser.semantic.context.SemanticContext`     — immutable analysis result.
    - :class:`~app.parser.semantic.context.SymbolTable`         — symbol registry.
    - :class:`~app.parser.semantic.symbols.Symbol`              — abstract symbol base.
    - :class:`~app.parser.semantic.symbols.ProgramSymbol`       — program unit symbol.
    - :class:`~app.parser.semantic.symbols.VariableSymbol`      — data item symbol.
    - :class:`~app.parser.semantic.symbols.ParagraphSymbol`     — paragraph symbol.
    - :class:`~app.parser.semantic.symbols.SymbolKind`          — symbol kind enumeration.
    - :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` — semantic error record.
    - :class:`~app.parser.semantic.diagnostics.SemanticSeverity`   — severity enumeration.
    - :class:`~app.parser.semantic.visitors.SemanticVisitor`    — extended visitor base.
    - :func:`~app.parser.semantic.visitors.traverse_program`    — traversal driver.

Dependencies:
    - :mod:`app.parser.ast`         — AST input.
    - :mod:`app.parser.lexer`       — ``Position`` value type.
    - :mod:`app.parser.diagnostics` — syntax diagnostics (separate concern).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from app.parser.semantic.analyzer import SemanticAnalyzer
from app.parser.semantic.context import SemanticContext, SymbolTable
from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity
from app.parser.semantic.symbols import (
    ParagraphSymbol,
    ProgramSymbol,
    Symbol,
    SymbolKind,
    VariableSymbol,
)
from app.parser.semantic.visitors import SemanticVisitor, traverse_program

__all__ = [
    "ParagraphSymbol",
    "ProgramSymbol",
    "SemanticAnalyzer",
    "SemanticContext",
    "SemanticDiagnostic",
    "SemanticSeverity",
    "SemanticVisitor",
    "Symbol",
    "SymbolKind",
    "SymbolTable",
    "VariableSymbol",
    "traverse_program",
]
