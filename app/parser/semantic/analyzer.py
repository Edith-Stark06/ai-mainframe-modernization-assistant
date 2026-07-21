"""
Semantic Analyser.

Purpose:
    Orchestrate the four-pass semantic analysis pipeline over the COBOL AST
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

    Pass 3 — :class:`~app.parser.semantic.validation.SemanticValidationVisitor`:
        Traverses the AST once more and enforces structural and semantic
        constraints.  Emits ``SEM006`` / ``SEM007`` / ``SEM008`` / ``SEM009``
        diagnostics for rule violations.

    Pass 4 — :class:`~app.parser.semantic.type_builder.TypeBuilder`:
        Iterates over the populated symbol table, interprets PIC clause strings
        stored in :class:`~app.parser.semantic.symbols.VariableSymbol` records,
        constructs :class:`~app.parser.semantic.types.CobolType` objects, and
        attaches them back to the symbols.  Does **not** re-traverse the AST.

    All AST-traversal passes share the same
    :class:`~app.parser.semantic.context.SymbolTable` and diagnostics list.
    The combined result is returned as an immutable
    :class:`~app.parser.semantic.context.SemanticContext`.

Responsibilities:
    - Orchestrate pass 1 (symbol collection).
    - Orchestrate pass 2 (reference resolution).
    - Orchestrate pass 3 (semantic validation).
    - Orchestrate pass 4 (type annotation via TypeBuilder).
    - Return a fully populated :class:`~app.parser.semantic.context.SemanticContext`.

Non-responsibilities:
    - Symbol registration logic (delegated to
      :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`).
    - Reference resolution logic (delegated to
      :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`).
    - Validation logic (delegated to
      :class:`~app.parser.semantic.validation.SemanticValidationVisitor`).
    - PIC interpretation and type construction (delegated to
      :class:`~app.parser.semantic.type_builder.TypeBuilder`).
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
    - :mod:`app.parser.semantic.validation`         — ``SemanticValidationVisitor``.
    - :mod:`app.parser.semantic.type_builder`       — ``TypeBuilder``.
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
from app.parser.semantic.type_builder import TypeBuilder
from app.parser.semantic.validation import SemanticValidationVisitor
from app.parser.semantic.visitors import traverse_program

__all__ = ["SemanticAnalyzer"]


# ===========================================================================


class SemanticAnalyzer:
    """
    Four-pass semantic analysis pipeline for a COBOL compilation unit.

    :class:`SemanticAnalyzer` runs four passes over a
    :class:`~app.parser.ast.program.ProgramNode`:

    **Pass 1 — symbol collection**
        :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`
        registers all declared symbols and detects duplicates.

    **Pass 2 — reference resolution**
        :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`
        resolves identifier references against the populated symbol table
        and emits diagnostics for any undefined references.

    **Pass 3 — semantic validation**
        :class:`~app.parser.semantic.validation.SemanticValidationVisitor`
        enforces structural and semantic constraints (PROGRAM-ID presence,
        non-empty PROCEDURE DIVISION, reserved-word identifiers, etc.).

    **Pass 4 — type annotation**
        :class:`~app.parser.semantic.type_builder.TypeBuilder`
        interprets PIC clause strings and attaches
        :class:`~app.parser.semantic.types.CobolType` objects to variable
        symbols.

    All AST-traversal passes share the same
    :class:`~app.parser.semantic.context.SymbolTable` and diagnostics list.
    The combined result is returned as an immutable
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
        Run the four-pass semantic analysis pipeline over *program*.

        This method:

        1. Creates a fresh :class:`~app.parser.semantic.context.SymbolTable`
           and diagnostics list.
        2. **Pass 1** — runs :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`
           via :func:`~app.parser.semantic.visitors.traverse_program` to
           register all symbols and detect duplicates.
        3. **Pass 2** — runs :class:`~app.parser.semantic.reference_resolver.ReferenceResolverVisitor`
           via :func:`~app.parser.semantic.visitors.traverse_program` to
           resolve all identifier references against the populated table.
        4. **Pass 3** — runs :class:`~app.parser.semantic.validation.SemanticValidationVisitor`
           via :func:`~app.parser.semantic.visitors.traverse_program` to
           validate structural and semantic constraints.
        5. **Pass 4** — runs :class:`~app.parser.semantic.type_builder.TypeBuilder`
           to interpret PIC clauses and attach
           :class:`~app.parser.semantic.types.CobolType` objects to variable
           symbols.
        6. Returns a :class:`~app.parser.semantic.context.SemanticContext`
           wrapping the populated symbol table and all diagnostics.

        Args:
            program:
                The :class:`~app.parser.ast.program.ProgramNode` to analyse.
                This must be the root node returned by the parser.

        Returns:
            An immutable :class:`~app.parser.semantic.context.SemanticContext`
            containing the symbol table and any diagnostics from all passes.

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
            "SemanticAnalyzer: pass 2 complete — {} diagnostic(s) so far.",
            len(diagnostics),
        )

        # --- Pass 3: semantic validation ----------------------------------
        logger.debug("SemanticAnalyzer: pass 3 — semantic validation.")
        validator = SemanticValidationVisitor(diagnostics=diagnostics)
        traverse_program(program, validator)
        logger.debug(
            "SemanticAnalyzer: pass 3 complete — {} diagnostic(s) total.",
            len(diagnostics),
        )

        # --- Pass 4: type annotation (TypeBuilder) ------------------------
        logger.debug("SemanticAnalyzer: pass 4 — type annotation.")
        type_builder = TypeBuilder(table=table)
        type_builder.build()
        logger.debug("SemanticAnalyzer: pass 4 complete — types attached.")

        return SemanticContext(symbol_table=table, diagnostics=diagnostics)
