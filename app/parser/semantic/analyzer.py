"""
Semantic Analyser.

Purpose:
    Implement the primary semantic analysis pass over the COBOL AST
    produced by the parser.

    The :class:`SemanticAnalyzer` traverses a
    :class:`~app.parser.ast.program.ProgramNode`, builds a
    :class:`~app.parser.semantic.context.SymbolTable`, detects structural
    violations (duplicate names), and returns an immutable
    :class:`~app.parser.semantic.context.SemanticContext` that bundles the
    symbol table with all collected
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` records.

Responsibilities:
    - Register a :class:`~app.parser.semantic.symbols.ProgramSymbol` from
      the PROGRAM-ID clause (if present).
    - Register a :class:`~app.parser.semantic.symbols.VariableSymbol` for
      every data item declared in the WORKING-STORAGE SECTION.
    - Register a :class:`~app.parser.semantic.symbols.ParagraphSymbol` for
      every paragraph declared in the PROCEDURE DIVISION.
    - Emit :data:`~app.parser.semantic.diagnostics.DIAGNOSTIC_CODES` ``"SEM001"``
      for each duplicate variable declaration.
    - Emit ``"SEM002"`` for each duplicate paragraph declaration.
    - Return a fully populated :class:`~app.parser.semantic.context.SemanticContext`.

Non-responsibilities:
    - Type checking or expression analysis.
    - Control-flow analysis.
    - Data-flow analysis.
    - Constant folding or optimisation.
    - Automatic correction.
    - IDE features.
    - Semantic validation beyond duplicate detection.

Dependencies:
    - :mod:`app.parser.ast.program`          — ``ProgramNode``.
    - :mod:`app.parser.ast.data_items`       — ``DataItemNode`` subtypes.
    - :mod:`app.parser.ast.paragraphs`       — ``ParagraphNode``.
    - :mod:`app.parser.semantic.context`     — ``SymbolTable``, ``SemanticContext``.
    - :mod:`app.parser.semantic.diagnostics` — ``SemanticDiagnostic``, ``SemanticSeverity``.
    - :mod:`app.parser.semantic.symbols`     — symbol types.
    - :mod:`app.parser.semantic.visitors`    — ``SemanticVisitor``, ``traverse_program``.
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

from app.parser.ast.data_items import (
    ConditionNameNode,
    ElementaryItemNode,
    GroupItemNode,
)
from app.parser.ast.identification import IdentificationDivisionNode
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.semantic.context import SemanticContext, SymbolTable
from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity
from app.parser.semantic.symbols import (
    ParagraphSymbol,
    ProgramSymbol,
    VariableSymbol,
)
from app.parser.semantic.visitors import SemanticVisitor, traverse_program

__all__ = ["SemanticAnalyzer"]


class _SymbolRegistrationVisitor(SemanticVisitor):
    """
    Internal visitor that populates the symbol table during traversal.

    This visitor is created once per :meth:`SemanticAnalyzer.analyse` call
    and is not part of the public API.  It accumulates symbols into the
    provided :class:`~app.parser.semantic.context.SymbolTable` and appends
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` records
    to the provided list whenever a duplicate is detected.

    Attributes:
        _table:
            The :class:`~app.parser.semantic.context.SymbolTable` being
            populated.
        _diagnostics:
            Mutable list of
            :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
            records collected during traversal.
    """

    def __init__(
        self,
        table: SymbolTable,
        diagnostics: list[SemanticDiagnostic],
    ) -> None:
        """
        Initialise the visitor with shared mutable state.

        Args:
            table:
                The :class:`~app.parser.semantic.context.SymbolTable` to
                populate.
            diagnostics:
                The mutable list to append diagnostics to.
        """
        self._table = table
        self._diagnostics = diagnostics

    # ------------------------------------------------------------------
    # Identification Division
    # ------------------------------------------------------------------

    def visit_identification_division(self, node: IdentificationDivisionNode) -> None:
        """
        Register the program symbol from the PROGRAM-ID clause.

        If the PROGRAM-ID clause is present, a
        :class:`~app.parser.semantic.symbols.ProgramSymbol` is registered
        in the symbol table.  If it is absent (partial parse), no symbol
        is registered and no diagnostic is emitted.

        Args:
            node: The identification division node.
        """
        pid = node.program_id
        if pid is None:
            logger.debug(
                "SemanticAnalyzer: PROGRAM-ID clause absent; skipping program symbol."
            )
            return

        program_name = pid.value.upper()
        sym = ProgramSymbol(name=program_name, declared_at=pid.start_position)
        registered = self._table.register(sym)
        if registered:
            logger.debug(
                "SemanticAnalyzer: registered program symbol {!r}.", program_name
            )
        else:
            # Duplicate program symbol — unlikely but guard it anyway.
            logger.warning(
                "SemanticAnalyzer: duplicate program name {!r}.", program_name
            )

    # ------------------------------------------------------------------
    # Working-Storage Section
    # ------------------------------------------------------------------

    def visit_working_storage_section(self, node: WorkingStorageSectionNode) -> None:
        """
        No-op at section level; items are visited individually by the traversal.

        Args:
            node: The working-storage section node.
        """

    def visit_elementary_item(self, node: ElementaryItemNode) -> None:
        """
        Register a :class:`~app.parser.semantic.symbols.VariableSymbol` for
        an elementary data item.

        Args:
            node: The elementary item node.
        """
        self._register_variable(
            name=node.name,
            level=node.level,
            picture=node.picture,
            declared_at=node.start_position,
        )

    def visit_group_item(self, node: GroupItemNode) -> None:
        """
        Register a :class:`~app.parser.semantic.symbols.VariableSymbol` for
        a group data item (no PIC clause).

        Args:
            node: The group item node.
        """
        self._register_variable(
            name=node.name,
            level=node.level,
            picture=None,
            declared_at=node.start_position,
        )

    def visit_condition_name(self, node: ConditionNameNode) -> None:
        """
        Register a :class:`~app.parser.semantic.symbols.VariableSymbol` for
        an 88-level condition-name entry.

        Args:
            node: The condition-name node.
        """
        self._register_variable(
            name=node.name,
            level=node.level,
            picture=None,
            declared_at=node.start_position,
        )

    def _register_variable(
        self,
        name: str,
        level: int,
        picture: str | None,
        declared_at: object,
    ) -> None:
        """
        Create and register a :class:`~app.parser.semantic.symbols.VariableSymbol`.

        If a symbol with the same name already exists, emit a ``"SEM001"``
        diagnostic and do not overwrite the original.

        Args:
            name:
                The data-name string (uppercased by the node).
            level:
                The COBOL level number.
            picture:
                The picture string, or ``None`` for group/condition items.
            declared_at:
                The source :class:`~app.parser.lexer.position.Position`.
        """
        from app.parser.lexer.position import Position

        if not isinstance(declared_at, Position):  # pragma: no cover
            return

        sym = VariableSymbol(
            name=name.upper(),
            declared_at=declared_at,
            level=level,
            picture=picture,
        )
        registered = self._table.register(sym)
        if registered:
            logger.debug(
                "SemanticAnalyzer: registered variable {!r} (level={}).",
                name,
                level,
            )
        else:
            existing = self._table.lookup(name)
            logger.warning("SemanticAnalyzer: duplicate variable {!r}.", name)
            first_pos = existing.declared_at if existing else declared_at
            self._diagnostics.append(
                SemanticDiagnostic(
                    message=f"duplicate variable declaration: {name!r}"
                    f" (first declared at {first_pos.filename}:{first_pos.line})",
                    position=declared_at,
                    severity=SemanticSeverity.ERROR,
                    code="SEM001",
                )
            )

    # ------------------------------------------------------------------
    # Procedure Division
    # ------------------------------------------------------------------

    def visit_procedure_division(self, node: ProcedureDivisionNode) -> None:
        """
        No-op at division level; paragraphs are visited individually.

        Args:
            node: The procedure division node.
        """

    def visit_paragraph(self, node: ParagraphNode) -> None:
        """
        Register a :class:`~app.parser.semantic.symbols.ParagraphSymbol`.

        If a paragraph with the same name already exists, emit a ``"SEM002"``
        diagnostic and do not overwrite the original.

        Args:
            node: The paragraph node.
        """
        name = node.name.upper()
        sym = ParagraphSymbol(name=name, declared_at=node.start_position)
        registered = self._table.register(sym)
        if registered:
            logger.debug("SemanticAnalyzer: registered paragraph {!r}.", name)
        else:
            existing = self._table.lookup(name)
            logger.warning("SemanticAnalyzer: duplicate paragraph {!r}.", name)
            first_pos = existing.declared_at if existing else node.start_position
            self._diagnostics.append(
                SemanticDiagnostic(
                    message=f"duplicate paragraph declaration: {name!r}"
                    f" (first declared at {first_pos.filename}:{first_pos.line})",
                    position=node.start_position,
                    severity=SemanticSeverity.ERROR,
                    code="SEM002",
                )
            )


# ===========================================================================
# Public API
# ===========================================================================


class SemanticAnalyzer:
    """
    Primary semantic analysis pass for a COBOL compilation unit.

    :class:`SemanticAnalyzer` traverses a
    :class:`~app.parser.ast.program.ProgramNode` using an internal
    :class:`_SymbolRegistrationVisitor`, accumulates symbols and
    diagnostics, and returns a fully populated
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

        visitor = _SymbolRegistrationVisitor(table=table, diagnostics=diagnostics)
        traverse_program(program, visitor)

        logger.debug(
            "SemanticAnalyzer: analysis complete — {} symbol(s), {} diagnostic(s).",
            len(table),
            len(diagnostics),
        )

        return SemanticContext(symbol_table=table, diagnostics=diagnostics)
