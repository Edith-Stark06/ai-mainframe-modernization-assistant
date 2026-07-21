"""
Semantic Analysis Sub-package.

Purpose:
    Implement the semantic analysis stage of the COBOL compiler pipeline.
    This sub-package validates program correctness beyond what can be
    determined by syntactic structure alone: symbol registration, scope
    rules, structural constraint checking, and semantic type annotation.

    The semantic analysis pipeline receives an AST produced by the parser,
    runs a four-pass analysis, and returns an immutable
    :class:`~app.parser.semantic.context.SemanticContext` for consumption
    by downstream stages (IR generation, RAG, modernisation).

    **Pass 1** — :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`
        builds a :class:`~app.parser.semantic.context.SymbolTable` and detects
        duplicate symbol declarations.

    **Pass 2** — :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`
        resolves identifier references against the populated symbol table
        and emits diagnostics for any undefined references.

    **Pass 3** — :class:`~app.parser.semantic.validation.SemanticValidationVisitor`
        enforces structural and semantic constraints (PROGRAM-ID presence,
        non-empty PROCEDURE DIVISION, reserved-word identifiers, etc.).

    **Pass 4** — :class:`~app.parser.semantic.type_builder.TypeBuilder`
        interprets PIC clause strings and attaches
        :class:`~app.parser.semantic.types.CobolType` objects to variable
        symbols.

Responsibilities:
    - Register program, variable, and paragraph symbols.
    - Detect duplicate variable and paragraph declarations.
    - Resolve identifier references in MOVE and DISPLAY statements.
    - Detect undefined variable, paragraph, and section references.
    - Validate structural and semantic constraints.
    - Interpret PIC clauses and attach semantic types to variable symbols.
    - Provide a reusable :class:`~app.parser.semantic.visitors.SemanticVisitor`
      base for future semantic rules.
    - Return a populated :class:`~app.parser.semantic.context.SemanticContext`
      from :meth:`~app.parser.semantic.analyzer.SemanticAnalyzer.analyse`.

Non-responsibilities (intentionally deferred):
    - Type compatibility checking and expression analysis.
    - Control-flow and data-flow analysis.
    - Constant folding and optimisation.
    - Cross-reference generation.
    - Storage offset calculation.
    - Java / target-language type mapping.

Public API:
    - :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`   — primary analysis entry point.
    - :class:`~app.parser.semantic.context.SemanticContext`     — immutable analysis result.
    - :class:`~app.parser.semantic.context.SymbolTable`         — symbol registry.
    - :class:`~app.parser.semantic.symbols.Symbol`              — abstract symbol base.
    - :class:`~app.parser.semantic.symbols.ProgramSymbol`       — program unit symbol.
    - :class:`~app.parser.semantic.symbols.VariableSymbol`      — data item symbol (with cobol_type).
    - :class:`~app.parser.semantic.symbols.ParagraphSymbol`     — paragraph symbol.
    - :class:`~app.parser.semantic.symbols.SymbolKind`          — symbol kind enumeration.
    - :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` — semantic error record.
    - :class:`~app.parser.semantic.diagnostics.SemanticSeverity`   — severity enumeration.
    - :class:`~app.parser.semantic.visitors.SemanticVisitor`    — extended visitor base.
    - :func:`~app.parser.semantic.visitors.traverse_program`    — traversal driver.
    - :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`   — pass 1.
    - :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor` — pass 2.
    - :class:`~app.parser.semantic.validation.SemanticValidationVisitor`        — pass 3.
    - :class:`~app.parser.semantic.type_builder.TypeBuilder`                    — pass 4.
    - :class:`~app.parser.semantic.types.CobolType`             — abstract type base.
    - :class:`~app.parser.semantic.types.NumericType`           — numeric type.
    - :class:`~app.parser.semantic.types.AlphanumericType`      — alphanumeric type.
    - :class:`~app.parser.semantic.types.GroupType`             — group type.
    - :class:`~app.parser.semantic.types.UsageType`             — USAGE clause enumeration.

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
from app.parser.semantic.reference_resolver import ReferenceResolverVisitor
from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
from app.parser.semantic.symbols import (
    ParagraphSymbol,
    ProgramSymbol,
    Symbol,
    SymbolKind,
    VariableSymbol,
)
from app.parser.semantic.type_builder import TypeBuilder
from app.parser.semantic.types import (
    AlphanumericType,
    CobolType,
    GroupType,
    NumericType,
    UsageType,
)
from app.parser.semantic.validation import SemanticValidationVisitor
from app.parser.semantic.visitors import SemanticVisitor, traverse_program

__all__ = [
    "AlphanumericType",
    "CobolType",
    "GroupType",
    "NumericType",
    "ParagraphSymbol",
    "ProgramSymbol",
    "ReferenceResolverVisitor",
    "SemanticAnalyzer",
    "SemanticContext",
    "SemanticDiagnostic",
    "SemanticSeverity",
    "SemanticValidationVisitor",
    "SemanticVisitor",
    "Symbol",
    "SymbolCollectorVisitor",
    "SymbolKind",
    "SymbolTable",
    "TypeBuilder",
    "UsageType",
    "VariableSymbol",
    "traverse_program",
]
