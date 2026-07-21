"""
Semantic Analyser.

Purpose:
    Orchestrate the two-pass semantic analysis pipeline over the COBOL AST
    produced by the parser.

    Pass 1 — :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`:
        Traverses the AST and registers every declared symbol (program name,
        variables, paragraphs) into a fresh
        :class:`~app.parser.semantic.context.SymbolTable`.  Detects duplicate
        declarations and emits ``SEM001`` / ``SEM002`` diagnostics.

    Pass 2 — :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`:
        Traverses the same AST again with the populated symbol table and
        resolves every identifier reference.  Emits ``SEM003`` / ``SEM004`` /
        ``SEM005`` diagnostics for unresolved references.

    Both passes share the same :class:`~app.parser.semantic.context.SymbolTable`
    and diagnostics list.  The combined result is returned as an immutable
    :class:`~app.parser.semantic.context.SemanticContext`.

Responsibilities:
    - Orchestrate pass 1 (symbol collection).
    - Orchestrate pass 2 (reference resolution).
    - Return a fully populated :class:`~app.parser.semantic.context.SemanticContext`.

Non-responsibilities:
    - Symbol registration logic (delegated to
      :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`).
    - Reference resolution logic (delegated to
      :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`).
    - Type checking or expression analysis.
    - Control-flow analysis.
    - Data-flow analysis.
    - Constant folding or optimisation.
    - Automatic correction.
    - IDE features.

Dependencies:
    - :mod:`app.parser.ast.program`                 — ``ProgramNode``.
    - :mod:`app.parser.semantic.context`            — ``SymbolTable``, ``SemanticContext``.
    - :mod:`app.parser.semantic.diagnostics`        — ``SemanticDiagnostic``.
    - :mod:`app.parser.semantic.symbol_collector`   — ``SymbolCollectorVisitor``.
    - :mod:`app.parser.semantic.reference_resolver` — ``ReferenceResolverVisitor``.
    - :mod:`app.parser.semantic.visitors`           — ``traverse_program``.
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
from app.parser.semantic.reference_resolver import ReferenceResolverVisitor
from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
from app.parser.semantic.visitors import traverse_program

__all__ = ["SemanticAnalyzer"]


# ===========================================================================


class SemanticAnalyzer:
    """
    Two-pass semantic analysis pipeline for a COBOL compilation unit.

    :class:`SemanticAnalyzer` runs two traversal passes over a
    :class:`~app.parser.ast.program.ProgramNode`:

    **Pass 1 — symbol collection**
        :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`
        registers all declared symbols and detects duplicates.

    **Pass 2 — reference resolution**
        :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`
        resolves identifier references against the populated symbol table
        and emits diagnostics for any undefined references.

    Both passes share the same :class:`~app.parser.semantic.context.SymbolTable`
    and diagnostics list.  The combined result is returned as an immutable
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
        Run the two-pass semantic analysis pipeline over *program*.

        This method:

        1. Creates a fresh :class:`~app.parser.semantic.context.SymbolTable`
           and diagnostics list.
        2. **Pass 1** — runs :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`
           via :func:`~app.parser.semantic.visitors.traverse_program` to
           register all symbols and detect duplicates.
        3. **Pass 2** — runs :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`
           via :func:`~app.parser.semantic.visitors.traverse_program` to
           resolve all identifier references against the populated table.
        4. Returns a :class:`~app.parser.semantic.context.SemanticContext`
           wrapping the populated symbol table and all diagnostics.

        Args:
            program:
                The :class:`~app.parser.ast.program.ProgramNode` to analyse.
                This must be the root node returned by the parser.

        Returns:
            An immutable :class:`~app.parser.semantic.context.SemanticContext`
            containing the symbol table and any diagnostics from both passes.

        Examples:
            >>> from app.parser.semantic.analyzer import SemanticAnalyzer
            >>> # Assumes `program` is a ProgramNode from the parser.
            >>> analyzer = SemanticAnalyzer()
            >>> # ctx = analyzer.analyse(program)
            >>> # ctx.has_errors → True/False
        """
        logger.debug("SemanticAnalyzer: starting analysis pipeline.")

        table: SymbolTable = SymbolTable()
        diagnostics: list[SemanticDiagnostic] = []

        # --- Pass 1: symbol collection ------------------------------------
        logger.debug("SemanticAnalyzer: pass 1 — symbol collection.")
        collector = SymbolCollectorVisitor(table=table, diagnostics=diagnostics)
        traverse_program(program, collector)
        logger.debug("SemanticAnalyzer: pass 1 complete — {} symbol(s).", len(table))

        # --- Pass 2: reference resolution ---------------------------------
        logger.debug("SemanticAnalyzer: pass 2 — reference resolution.")
        resolver = ReferenceResolverVisitor(table=table, diagnostics=diagnostics)
        traverse_program(program, resolver)
        logger.debug(
            "SemanticAnalyzer: pass 2 complete — {} diagnostic(s) total.",
            len(diagnostics),
        )

        return SemanticContext(symbol_table=table, diagnostics=diagnostics)
