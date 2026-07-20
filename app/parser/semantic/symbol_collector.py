"""
AST Symbol Collection Visitor.

Purpose:
    Implement the first semantic analysis pass that traverses the COBOL AST
    and populates the :class:`~app.parser.semantic.context.SymbolTable` with
    every symbol declared in the program.

    :class:`SymbolCollectorVisitor` is the **public, reusable** visitor
    responsible for symbol collection.  It separates the collection concern
    from the orchestration concern owned by
    :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`, allowing the
    same visitor to be composed into future multi-pass pipelines or used
    independently in tooling.

Responsibilities:
    - Visit :class:`~app.parser.ast.identification.IdentificationDivisionNode`
      and register a :class:`~app.parser.semantic.symbols.ProgramSymbol` from
      the PROGRAM-ID clause when present.
    - Visit :class:`~app.parser.ast.data_items.ElementaryItemNode`,
      :class:`~app.parser.ast.data_items.GroupItemNode`, and
      :class:`~app.parser.ast.data_items.ConditionNameNode` and register a
      :class:`~app.parser.semantic.symbols.VariableSymbol` for each.
    - Visit :class:`~app.parser.ast.paragraphs.ParagraphNode` and register a
      :class:`~app.parser.semantic.symbols.ParagraphSymbol` for each.
    - Detect duplicate name registrations and emit ``"SEM001"`` / ``"SEM002"``
      :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` records
      while **continuing traversal** rather than aborting.

Non-responsibilities:
    - Driving the AST traversal (delegated to
      :func:`~app.parser.semantic.visitors.traverse_program`).
    - Type checking or expression analysis.
    - Control-flow or data-flow analysis.
    - Constant folding or optimisation.

Dependencies:
    - :mod:`app.parser.ast.data_items`       — ``ElementaryItemNode``, etc.
    - :mod:`app.parser.ast.identification`   — ``IdentificationDivisionNode``.
    - :mod:`app.parser.ast.paragraphs`       — ``ParagraphNode``.
    - :mod:`app.parser.ast.procedure`        — ``ProcedureDivisionNode``.
    - :mod:`app.parser.ast.working_storage`  — ``WorkingStorageSectionNode``.
    - :mod:`app.parser.semantic.context`     — ``SymbolTable``.
    - :mod:`app.parser.semantic.diagnostics` — ``SemanticDiagnostic``, ``SemanticSeverity``.
    - :mod:`app.parser.semantic.symbols`     — symbol types.
    - :mod:`app.parser.semantic.visitors`    — ``SemanticVisitor`` base.
    - Loguru for structured logging.

Examples:
    Using the collector as a standalone visitor::

        from app.parser.semantic.context import SymbolTable
        from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
        from app.parser.semantic.visitors import traverse_program

        table = SymbolTable()
        diagnostics = []
        collector = SymbolCollectorVisitor(table=table, diagnostics=diagnostics)
        traverse_program(program_node, collector)

        table.all_symbols()   # all registered symbols
        diagnostics           # any duplicate-detection errors

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
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.semantic.context import SymbolTable
from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity
from app.parser.semantic.symbols import (
    ParagraphSymbol,
    ProgramSymbol,
    VariableSymbol,
)
from app.parser.semantic.visitors import SemanticVisitor

__all__ = ["SymbolCollectorVisitor"]


class SymbolCollectorVisitor(SemanticVisitor):
    """
    Public semantic visitor that collects symbols from a COBOL AST.

    :class:`SymbolCollectorVisitor` traverses a
    :class:`~app.parser.ast.program.ProgramNode` and registers every
    declared symbol — program name, variables, and paragraphs — into the
    provided :class:`~app.parser.semantic.context.SymbolTable`.  When a
    duplicate name is encountered the original registration is preserved,
    a :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` is
    appended to *diagnostics*, and the traversal continues normally.

    This visitor is **stateless between visits** to individual nodes; all
    mutable state lives in the externally-owned *table* and *diagnostics*
    objects.  The same visitor instance must not be shared across concurrent
    analysis passes, but it can safely be reused **sequentially** provided
    fresh *table* and *diagnostics* objects are supplied on each pass.

    Attributes:
        _table:
            The :class:`~app.parser.semantic.context.SymbolTable` being
            populated.
        _diagnostics:
            Mutable list of
            :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
            records accumulated during traversal.

    Examples:
        >>> from app.parser.semantic.context import SymbolTable
        >>> from app.parser.semantic.symbol_collector import SymbolCollectorVisitor
        >>> table = SymbolTable()
        >>> collector = SymbolCollectorVisitor(table=table, diagnostics=[])
        >>> collector._table is table
        True
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
                populate during traversal.
            diagnostics:
                A mutable list to which
                :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
                records are appended when duplicate declarations are detected.
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
        :class:`~app.parser.semantic.symbols.ProgramSymbol` is registered in
        the symbol table.  If it is absent (partial parse), the method returns
        silently without emitting any diagnostic.

        Args:
            node: The identification division node.
        """
        pid = node.program_id
        if pid is None:
            logger.debug(
                "SymbolCollectorVisitor: PROGRAM-ID clause absent; "
                "skipping program symbol."
            )
            return

        program_name = pid.value.upper()
        sym = ProgramSymbol(name=program_name, declared_at=pid.start_position)
        registered = self._table.register(sym)
        if registered:
            logger.debug(
                "SymbolCollectorVisitor: registered program symbol {!r}.",
                program_name,
            )
        else:
            # Duplicate program symbol — guard defensively.
            logger.warning(
                "SymbolCollectorVisitor: duplicate program name {!r}.",
                program_name,
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
        an elementary data item declared in the WORKING-STORAGE SECTION.

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
        diagnostic and do not overwrite the original registration.

        Args:
            name:
                The data-name string (uppercased by the node).
            level:
                The COBOL level number (e.g. 1, 5, 77, 88).
            picture:
                The picture string (e.g. ``"9(5)"``), or ``None`` for group
                items and condition-names.
            declared_at:
                The source :class:`~app.parser.lexer.position.Position` of the
                data-name token.
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
                "SymbolCollectorVisitor: registered variable {!r} (level={}).",
                name,
                level,
            )
        else:
            existing = self._table.lookup(name)
            logger.warning("SymbolCollectorVisitor: duplicate variable {!r}.", name)
            first_pos = existing.declared_at if existing else declared_at
            self._diagnostics.append(
                SemanticDiagnostic(
                    message=(
                        f"duplicate variable declaration: {name!r}"
                        f" (first declared at"
                        f" {first_pos.filename}:{first_pos.line})"  # type: ignore[union-attr]
                    ),
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
        No-op at division level; paragraphs are visited individually by the
        traversal driver.

        Args:
            node: The procedure division node.
        """

    def visit_paragraph(self, node: ParagraphNode) -> None:
        """
        Register a :class:`~app.parser.semantic.symbols.ParagraphSymbol`.

        If a paragraph with the same name already exists, emit a ``"SEM002"``
        diagnostic and do not overwrite the original registration.

        Args:
            node: The paragraph node.
        """
        name = node.name.upper()
        sym = ParagraphSymbol(name=name, declared_at=node.start_position)
        registered = self._table.register(sym)
        if registered:
            logger.debug("SymbolCollectorVisitor: registered paragraph {!r}.", name)
        else:
            existing = self._table.lookup(name)
            logger.warning("SymbolCollectorVisitor: duplicate paragraph {!r}.", name)
            first_pos = existing.declared_at if existing else node.start_position
            self._diagnostics.append(
                SemanticDiagnostic(
                    message=(
                        f"duplicate paragraph declaration: {name!r}"
                        f" (first declared at"
                        f" {first_pos.filename}:{first_pos.line})"
                    ),
                    position=node.start_position,
                    severity=SemanticSeverity.ERROR,
                    code="SEM002",
                )
            )
