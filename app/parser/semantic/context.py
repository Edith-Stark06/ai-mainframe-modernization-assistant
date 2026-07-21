"""
Semantic Context and Symbol Table.

Purpose:
    Provide the runtime data structures used during and produced by a single
    semantic analysis pass of a COBOL compilation unit.

    * :class:`SymbolTable` — mutable, scoped registry built *during* analysis.
    * :class:`SemanticContext` — immutable result object returned *after*
      analysis completes; holds the populated symbol table and the collected
      semantic diagnostics.

Responsibilities:
    - :class:`SymbolTable`: register symbols, detect duplicates, support
      look-up by name and iteration by kind.
    - :class:`SemanticContext`: aggregate symbol table + diagnostics into a
      single immutable result that can be safely passed to downstream
      pipeline stages (IR generation, RAG, etc.).

Non-responsibilities:
    - Type checking or expression analysis.
    - Cross-scope symbol resolution.
    - Import / COPY-book symbol merging.

Dependencies:
    - :mod:`app.parser.semantic.symbols`     — ``Symbol``, ``SymbolKind``.
    - :mod:`app.parser.semantic.diagnostics` — ``SemanticDiagnostic``.
    - Python standard library only.

Examples:
    Building a context from analysis results::

        from app.parser.semantic.context import SemanticContext, SymbolTable

        table = SymbolTable()
        # ... register symbols ...
        ctx = SemanticContext(symbol_table=table, diagnostics=[])
        ctx.has_errors  # False

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.parser.semantic.diagnostics import SemanticDiagnostic
    from app.parser.semantic.symbols import Symbol, SymbolKind

__all__ = [
    "SemanticContext",
    "SymbolTable",
]


# ===========================================================================
# SymbolTable
# ===========================================================================


class SymbolTable:
    """
    Scoped registry of :class:`~app.parser.semantic.symbols.Symbol` records.

    The table maintains two internal dictionaries:

    * ``_by_name`` — maps ``name.upper()`` → ``Symbol`` for O(1) look-up.
    * ``_all`` — ordered list preserving insertion order for iteration.

    Duplicate detection is performed per *name only* (case-insensitive).
    Two symbols with the same name but different kinds are considered
    duplicates because COBOL names share a single namespace within their
    scope.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> from app.parser.semantic.symbols import ParagraphSymbol
        >>> pos = Position(line=20, column=1, offset=400, filename="p.cbl")
        >>> sym = ParagraphSymbol(name="MAIN-PARA", declared_at=pos)
        >>> table = SymbolTable()
        >>> table.register(sym)
        True
        >>> table.register(sym)
        False
        >>> table.lookup("MAIN-PARA") is sym
        True
    """

    def __init__(self) -> None:
        """Initialise an empty symbol table."""
        self._by_name: dict[str, Symbol] = {}
        self._all: list[Symbol] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, symbol: Symbol) -> bool:
        """
        Register a symbol in the table.

        If a symbol with the same name (case-insensitive) has already been
        registered, this method does **not** overwrite the original and
        returns ``False`` so that the caller can emit a duplicate diagnostic.

        Args:
            symbol:
                The :class:`~app.parser.semantic.symbols.Symbol` to register.

        Returns:
            ``True`` if the symbol was registered successfully.
            ``False`` if a symbol with the same name already exists.

        Examples:
            >>> from app.parser.lexer.position import Position
            >>> from app.parser.semantic.symbols import ProgramSymbol
            >>> pos = Position(line=1, column=1, offset=0, filename="p.cbl")
            >>> sym = ProgramSymbol(name="PAYROLL", declared_at=pos)
            >>> table = SymbolTable()
            >>> table.register(sym)
            True
            >>> table.register(sym)
            False
        """
        key = symbol.name.upper()
        if key in self._by_name:
            return False
        self._by_name[key] = symbol
        self._all.append(symbol)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def lookup(self, name: str) -> Symbol | None:
        """
        Return the symbol registered under *name*, or ``None`` if absent.

        The look-up is case-insensitive.

        Args:
            name:
                The symbol name to search for.

        Returns:
            The :class:`~app.parser.semantic.symbols.Symbol` registered
            under *name*, or ``None``.

        Examples:
            >>> table = SymbolTable()
            >>> table.lookup("MISSING") is None
            True
        """
        return self._by_name.get(name.upper())

    def all_symbols(self) -> list[Symbol]:
        """
        Return a defensive copy of all registered symbols in insertion order.

        Returns:
            A new ``list`` of all :class:`~app.parser.semantic.symbols.Symbol`
            instances currently held in the table.

        Examples:
            >>> table = SymbolTable()
            >>> table.all_symbols()
            []
        """
        return list(self._all)

    def symbols_of_kind(self, kind: SymbolKind) -> list[Symbol]:
        """
        Return all symbols of the given *kind* in insertion order.

        Args:
            kind:
                A :class:`~app.parser.semantic.symbols.SymbolKind` member.

        Returns:
            A new ``list`` of symbols whose
            :attr:`~app.parser.semantic.symbols.Symbol.kind` matches *kind*.

        Examples:
            >>> from app.parser.semantic.symbols import SymbolKind
            >>> table = SymbolTable()
            >>> table.symbols_of_kind(SymbolKind.VARIABLE)
            []
        """
        return [s for s in self._all if s.kind is kind]

    def __len__(self) -> int:
        """Return the number of registered symbols."""
        return len(self._all)

    def __contains__(self, name: object) -> bool:
        """Return ``True`` if *name* (str) is registered in the table."""
        if isinstance(name, str):
            return name.upper() in self._by_name
        return False  # pragma: no cover

    # ------------------------------------------------------------------
    # Mutation (type annotation pass)
    # ------------------------------------------------------------------

    def replace_symbol(self, symbol: Symbol) -> bool:
        """
        Replace an already-registered symbol with *symbol* (same name).

        This method is called by the type-annotation pass (pass 4) to swap
        an existing :class:`~app.parser.semantic.symbols.VariableSymbol`
        for an updated version that carries a resolved
        :class:`~app.parser.semantic.types.CobolType`.  The name must
        already exist in the table; if it does not, the method returns
        ``False`` and makes no changes.

        The insertion order of the replaced symbol is preserved.

        Args:
            symbol:
                The replacement :class:`~app.parser.semantic.symbols.Symbol`.
                Its :attr:`~app.parser.semantic.symbols.Symbol.name` must
                match (case-insensitively) a symbol already registered.

        Returns:
            ``True`` if the replacement was performed.
            ``False`` if no symbol with that name is registered.

        Examples:
            >>> from app.parser.lexer.position import Position
            >>> from app.parser.semantic.symbols import VariableSymbol
            >>> pos = Position(line=1, column=1, offset=0, filename="p.cbl")
            >>> sym = VariableSymbol(name="WS-X", declared_at=pos, level=77)
            >>> table = SymbolTable()
            >>> table.register(sym)
            True
            >>> import dataclasses
            >>> sym2 = dataclasses.replace(sym, picture="9(5)")
            >>> table.replace_symbol(sym2)
            True
            >>> table.lookup("WS-X").picture
            '9(5)'
        """
        key = symbol.name.upper()
        if key not in self._by_name:
            return False
        # Preserve list position.
        idx = self._all.index(self._by_name[key])
        self._by_name[key] = symbol
        self._all[idx] = symbol
        return True


# ===========================================================================
# SemanticContext  (immutable result)
# ===========================================================================


class SemanticContext:
    """
    Immutable result of a completed semantic analysis pass.

    A :class:`SemanticContext` is the single object returned by
    :meth:`~app.parser.semantic.analyzer.SemanticAnalyzer.analyse`.  It
    bundles the populated :class:`SymbolTable` with the list of
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` records
    collected during analysis.

    Attributes:
        symbol_table:
            The :class:`SymbolTable` containing every symbol registered
            during the analysis pass.
        diagnostics:
            An ordered list of
            :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
            records.  An empty list indicates a clean analysis.

    Examples:
        >>> from app.parser.semantic.context import SemanticContext, SymbolTable
        >>> ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
        >>> ctx.has_errors
        False
        >>> ctx.error_count
        0
    """

    def __init__(
        self,
        symbol_table: SymbolTable,
        diagnostics: list[SemanticDiagnostic],
    ) -> None:
        """
        Initialise the semantic context.

        Args:
            symbol_table:
                The fully-populated :class:`SymbolTable`.
            diagnostics:
                The list of :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
                records collected during analysis.
        """
        self._symbol_table = symbol_table
        self._diagnostics: list[SemanticDiagnostic] = list(diagnostics)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def symbol_table(self) -> SymbolTable:
        """Return the populated :class:`SymbolTable`."""
        return self._symbol_table

    @property
    def diagnostics(self) -> list[SemanticDiagnostic]:
        """Return a defensive copy of the diagnostics list."""
        return list(self._diagnostics)

    @property
    def has_errors(self) -> bool:
        """
        Return ``True`` if any error-level diagnostics were collected.

        Examples:
            >>> ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
            >>> ctx.has_errors
            False
        """
        from app.parser.semantic.diagnostics import SemanticSeverity

        return any(d.severity is SemanticSeverity.ERROR for d in self._diagnostics)

    @property
    def error_count(self) -> int:
        """
        Return the number of error-level diagnostics.

        Examples:
            >>> ctx = SemanticContext(symbol_table=SymbolTable(), diagnostics=[])
            >>> ctx.error_count
            0
        """
        from app.parser.semantic.diagnostics import SemanticSeverity

        return sum(1 for d in self._diagnostics if d.severity is SemanticSeverity.ERROR)
