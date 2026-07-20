"""
Semantic Analyser.

Purpose:
    Implement the primary semantic analysis pass over the COBOL AST
    produced by the parser.

    The :class:`SemanticAnalyzer` traverses a
    :class:`~app.parser.ast.program.ProgramNode` using the public
    :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`,
    builds a :class:`~app.parser.semantic.context.SymbolTable`, detects
    structural violations (duplicate names), and returns an immutable
    :class:`~app.parser.semantic.context.SemanticContext` that bundles the
    symbol table with all collected
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` records.

Responsibilities:
    - Orchestrate the symbol-collection pass by instantiating a
      :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`
      and driving it through
      :func:`~app.parser.semantic.visitors.traverse_program`.
    - Return a fully populated :class:`~app.parser.semantic.context.SemanticContext`.

Non-responsibilities:
    - Symbol registration logic (delegated to
      :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`).
    - Type checking or expression analysis.
    - Control-flow analysis.
    - Data-flow analysis.
    - Constant folding or optimisation.
    - Automatic correction.
    - IDE features.

Dependencies:
    - :mod:`app.parser.ast.program`               — ``ProgramNode``.
    - :mod:`app.parser.semantic.context`          — ``SymbolTable``, ``SemanticContext``.
    - :mod:`app.parser.semantic.diagnostics`      — ``SemanticDiagnostic``.
    - :mod:`app.parser.semantic.symbol_collector` — ``SymbolCollectorVisitor``.
    - :mod:`app.parser.semantic.visitors`         — ``traverse_program``.
    - Loguru for logging.

Examples:
    Running the analyser on a parsed program::

        from app.parser.semantic.analyzer import SemanticAnalyzer
        from app.parser.syntax.program_parser import ProgramParser

        parser = ProgramParser()
        program = parser.parse(tokens)

        analyzer = SemanticAnalyzer()
        ctx = analyzer.analyse(program)

        ctx.has_errors        # True / False
        ctx.error_count       # number of semantic errors
        len(ctx.diagnostics)  # total diagnostics
        ctx.symbol_table.all_symbols()  # all registered symbols

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.program import ProgramNode
from app.parser.semantic.context import SemanticContext, SymbolTable
from app.parser.semantic.diagnostics import SemanticDiagnostic
from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
from app.parser.semantic.visitors import traverse_program

__all__ = ["SemanticAnalyzer"]


# ===========================================================================


class SemanticAnalyzer:
    """
    Primary semantic analysis pass for a COBOL compilation unit.

    :class:`SemanticAnalyzer` traverses a
    :class:`~app.parser.ast.program.ProgramNode` using a
    :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`,
    accumulates symbols and diagnostics, and returns a fully populated
    :class:`~app.parser.semantic.context.SemanticContext`.

    A single :class:`SemanticAnalyzer` instance may be reused across
    multiple :meth:`analyse` calls; each call produces an independent
    :class:`~app.parser.semantic.context.SemanticContext`.

    Examples:
        >>> from app.parser.semantic.analyzer import SemanticAnalyzer
        >>> analyzer = SemanticAnalyzer()
        >>> # ctx = analyzer.analyse(program_node)
    """

    def analyse(self, program: ProgramNode) -> SemanticContext:
        """
        Run the semantic analysis pass over *program*.

        This method:

        1. Creates a fresh :class:`~app.parser.semantic.context.SymbolTable`
           and diagnostics list.
        2. Instantiates an internal :class:`_SymbolRegistrationVisitor`.
        3. Calls :func:`~app.parser.semantic.visitors.traverse_program` to
           drive the top-down traversal.
        4. Returns a :class:`~app.parser.semantic.context.SemanticContext`
           wrapping the populated symbol table and diagnostics.

        Args:
            program:
                The :class:`~app.parser.ast.program.ProgramNode` to analyse.
                This must be the root node returned by the parser.

        Returns:
            An immutable :class:`~app.parser.semantic.context.SemanticContext`
            containing the symbol table and any diagnostics.

        Examples:
            >>> from app.parser.semantic.analyzer import SemanticAnalyzer
            >>> # Assumes `program` is a ProgramNode from the parser.
            >>> analyzer = SemanticAnalyzer()
            >>> # ctx = analyzer.analyse(program)
            >>> # ctx.has_errors → True/False
        """
        logger.debug("SemanticAnalyzer: starting analysis pass.")

        table: SymbolTable = SymbolTable()
        diagnostics: list[SemanticDiagnostic] = []

        collector = SymbolCollectorVisitor(table=table, diagnostics=diagnostics)
        traverse_program(program, collector)

        logger.debug(
            "SemanticAnalyzer: analysis complete — {} symbol(s), {} diagnostic(s).",
            len(table),
            len(diagnostics),
        )

        return SemanticContext(symbol_table=table, diagnostics=diagnostics)
