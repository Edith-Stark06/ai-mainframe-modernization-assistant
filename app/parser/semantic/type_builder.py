"""
COBOL Data Type Builder — Pass 4 of the Semantic Analysis Pipeline.

Purpose:
    Implement the fourth semantic analysis pass that interprets PIC clause
    strings stored in :class:`~app.parser.semantic.symbols.VariableSymbol`
    records, constructs the appropriate
    :class:`~app.parser.semantic.types.CobolType` objects, and attaches them
    back to the symbols in the
    :class:`~app.parser.semantic.context.SymbolTable`.

    :class:`TypeBuilder` is **not** a
    :class:`~app.parser.semantic.visitors.SemanticVisitor`.  It operates
    entirely on the *already-populated* symbol table rather than re-traversing
    the AST.  This keeps the pass lightweight and decouples type interpretation
    from the AST node hierarchy.

Responsibilities:
    - Iterate over every
      :class:`~app.parser.semantic.symbols.VariableSymbol` in the
      :class:`~app.parser.semantic.context.SymbolTable`.
    - Parse the ``picture`` string (if present) using
      :meth:`_parse_pic` to determine the type category, digit count,
      character length, and sign.
    - Determine the :class:`~app.parser.semantic.types.UsageType` from the
      symbol's ``picture`` string heuristic (future: from an explicit USAGE
      node attribute).
    - Construct the appropriate :class:`~app.parser.semantic.types.CobolType`
      (:class:`~app.parser.semantic.types.NumericType`,
      :class:`~app.parser.semantic.types.AlphanumericType`, or
      :class:`~app.parser.semantic.types.GroupType`).
    - Call :meth:`~app.parser.semantic.context.SymbolTable.replace_symbol`
      to swap the original symbol for an enriched copy
      (using ``dataclasses.replace``).
    - Skip symbols that already have a resolved ``cobol_type``.
    - Never raise on unrecognised PIC strings — produce a warning and leave
      ``cobol_type`` as ``None`` for that symbol.

Non-responsibilities:
    - AST traversal (TypeBuilder does not subclass SemanticVisitor).
    - Symbol registration (pass 1).
    - Reference resolution (pass 2).
    - Semantic validation (pass 3).
    - Type compatibility checking.
    - Storage offset calculation.
    - Java / target-language type mapping.
    - OCCURS, REDEFINES, or INDEXED BY resolution.

Design for extensibility:
    * New PIC categories (``A``, ``N``, ``U``, ``1``) are handled by adding
      branches in :meth:`_parse_pic`.
    * USAGE attributes other than DISPLAY are attached in
      :meth:`_infer_usage` — extend the USAGE map there.
    * OCCURS and REDEFINES metadata can be captured by adding fields to the
      future ``ArrayType`` / ``RedefinesType`` classes without touching
      :class:`TypeBuilder`.

PIC clause syntax handled::

    PIC 9(n)         → NumericType(digits=n, signed=False)
    PIC S9(n)        → NumericType(digits=n, signed=True)
    PIC 9(n)V9(m)    → NumericType(digits=n+m, decimal_places=m)
    PIC S9(n)V9(m)   → NumericType(digits=n+m, signed=True, decimal_places=m)
    PIC X(n)         → AlphanumericType(length=n)
    PIC X            → AlphanumericType(length=1)
    PIC 9            → NumericType(digits=1)
    (no PIC)         → GroupType()

Recognised USAGE suffixes (future-facing; currently derived heuristically
from symbol name conventions — extend :meth:`_infer_usage` for explicit
USAGE node support)::

    COMP   → UsageType.COMP
    COMP-3 → UsageType.COMP_3
    COMP-1 → UsageType.COMP_1
    COMP-2 → UsageType.COMP_2
    COMP-5 → UsageType.COMP_5
    (none) → UsageType.DISPLAY

Dependencies:
    - :mod:`app.parser.semantic.context`  — ``SymbolTable``.
    - :mod:`app.parser.semantic.symbols`  — ``VariableSymbol``, ``SymbolKind``.
    - :mod:`app.parser.semantic.types`    — ``CobolType`` hierarchy,
      ``UsageType``.
    - Python standard library (``dataclasses``, ``re``).
    - Loguru for structured logging.

Examples:
    Using TypeBuilder as pass 4 after SymbolCollectorVisitor::

        from app.parser.semantic.context import SymbolTable
        from app.parser.semantic.type_builder import TypeBuilder

        # table already populated by SymbolCollectorVisitor
        builder = TypeBuilder(table=table)
        builder.build()

        # Variables now carry cobol_type
        for sym in table.symbols_of_kind(SymbolKind.VARIABLE):
            print(sym.name, sym.cobol_type)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses
import re

from loguru import logger

from app.parser.semantic.context import SymbolTable
from app.parser.semantic.symbols import SymbolKind, VariableSymbol
from app.parser.semantic.types import (
    AlphanumericType,
    CobolType,
    GroupType,
    NumericType,
    UsageType,
)

__all__ = ["TypeBuilder"]

# ---------------------------------------------------------------------------
# Compiled PIC-clause patterns
# ---------------------------------------------------------------------------

# Matches: optional leading 'S', then digit specs.
# Examples: 9(5), S9(7)V9(2), 99, S999.
_RE_NUMERIC = re.compile(
    r"""
    ^
    (?P<signed>S)?          # optional sign indicator
    9(?:\((?P<int_n>\d+)\)|(?P<int_bare>9*))  # integer digits: 9(n) or 9/99/999
    (?:V9(?:\((?P<dec_n>\d+)\)|(?P<dec_bare>9*)))?  # optional V9(m) or V99
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Matches: PIC X(n) or bare X / XX etc.
_RE_ALPHA = re.compile(
    r"""
    ^
    X(?:\((?P<len_n>\d+)\)|(?P<len_bare>X*))
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Normalised USAGE keyword → UsageType mapping (used by _infer_usage).
_USAGE_MAP: dict[str, UsageType] = {
    "DISPLAY": UsageType.DISPLAY,
    "COMP": UsageType.COMP,
    "COMP-4": UsageType.COMP,  # alias
    "BINARY": UsageType.COMP,  # alias
    "COMP-1": UsageType.COMP_1,
    "COMP-2": UsageType.COMP_2,
    "COMP-3": UsageType.COMP_3,
    "PACKED-DECIMAL": UsageType.COMP_3,  # alias
    "COMP-5": UsageType.COMP_5,
    "INDEX": UsageType.INDEX,
    "POINTER": UsageType.POINTER,
}


# ===========================================================================
# TypeBuilder
# ===========================================================================


class TypeBuilder:
    """
    Pass 4: interpret PIC clauses and attach semantic types to variable symbols.

    :class:`TypeBuilder` iterates over all
    :class:`~app.parser.semantic.symbols.VariableSymbol` records in the
    provided :class:`~app.parser.semantic.context.SymbolTable`, builds the
    appropriate :class:`~app.parser.semantic.types.CobolType`, and stores the
    enriched symbol back into the table using
    :meth:`~app.parser.semantic.context.SymbolTable.replace_symbol`.

    A :class:`TypeBuilder` instance is single-use; create a new instance for
    each :meth:`build` call.

    Attributes:
        _table:
            The :class:`~app.parser.semantic.context.SymbolTable` to enrich.

    Examples:
        >>> from app.parser.semantic.context import SymbolTable
        >>> from app.parser.semantic.type_builder import TypeBuilder
        >>> table = SymbolTable()
        >>> builder = TypeBuilder(table=table)
        >>> builder.build()   # no-op on empty table
    """

    def __init__(self, table: SymbolTable) -> None:
        """
        Initialise the type builder.

        Args:
            table:
                The :class:`~app.parser.semantic.context.SymbolTable`
                populated by the symbol-collection pass (pass 1).  The
                builder will enrich :class:`~app.parser.semantic.symbols.VariableSymbol`
                records in-place (via
                :meth:`~app.parser.semantic.context.SymbolTable.replace_symbol`).
        """
        self._table = table

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> None:
        """
        Run the type-builder pass over the symbol table.

        For every :class:`~app.parser.semantic.symbols.VariableSymbol` in
        the symbol table the method:

        1. Skips the symbol if it already has a non-``None`` ``cobol_type``.
        2. Calls :meth:`_build_type` to produce a
           :class:`~app.parser.semantic.types.CobolType`.
        3. Calls :meth:`~app.parser.semantic.context.SymbolTable.replace_symbol`
           with a ``dataclasses.replace``-d copy of the symbol that carries
           the resolved type.

        This method is idempotent — calling it multiple times produces the
        same result.
        """
        logger.debug("TypeBuilder: starting type annotation pass.")
        variables = self._table.symbols_of_kind(SymbolKind.VARIABLE)
        enriched = 0
        for sym in variables:
            if not isinstance(sym, VariableSymbol):
                continue  # pragma: no cover
            if sym.cobol_type is not None:
                logger.debug(
                    "TypeBuilder: skipping {} — type already resolved.", sym.name
                )
                continue
            cobol_type = self._build_type(sym)
            enriched_sym = dataclasses.replace(sym, cobol_type=cobol_type)
            self._table.replace_symbol(enriched_sym)
            enriched += 1
            logger.debug(
                "TypeBuilder: {} → {}.",
                sym.name,
                cobol_type.category if cobol_type else "unresolved",
            )
        logger.debug("TypeBuilder: pass complete — {} symbol(s) enriched.", enriched)

    # ------------------------------------------------------------------
    # Type construction
    # ------------------------------------------------------------------

    def _build_type(self, sym: VariableSymbol) -> CobolType | None:
        """
        Produce a :class:`~app.parser.semantic.types.CobolType` for *sym*.

        The logic branches on the symbol's ``picture`` and ``level``:

        - ``picture`` is ``None``  → :class:`~app.parser.semantic.types.GroupType`.
        - ``picture`` matches numeric pattern → :class:`~app.parser.semantic.types.NumericType`.
        - ``picture`` matches alphanumeric pattern → :class:`~app.parser.semantic.types.AlphanumericType`.
        - Unrecognised ``picture`` → ``None`` (with a warning logged).

        Args:
            sym:
                The :class:`~app.parser.semantic.symbols.VariableSymbol`
                whose PIC clause is to be interpreted.

        Returns:
            A :class:`~app.parser.semantic.types.CobolType` instance, or
            ``None`` if the PIC clause could not be interpreted.
        """
        pic = sym.picture

        if pic is None:
            # Group item or condition-name — no PIC clause.
            return GroupType()

        pic_normalised = pic.strip().upper()

        # --- Attempt numeric match -----------------------------------------
        numeric = self._parse_numeric_pic(pic_normalised)
        if numeric is not None:
            usage = self._infer_usage(pic_normalised)
            return dataclasses.replace(numeric, usage=usage)

        # --- Attempt alphanumeric match ------------------------------------
        alpha = self._parse_alpha_pic(pic_normalised)
        if alpha is not None:
            return alpha

        # --- Unrecognised ---------------------------------------------------
        logger.warning(
            "TypeBuilder: unrecognised PIC clause {!r} for symbol {!r}; "
            "cobol_type will remain None.",
            pic,
            sym.name,
        )
        return None

    # ------------------------------------------------------------------
    # PIC parsers
    # ------------------------------------------------------------------

    def _parse_numeric_pic(self, pic: str) -> NumericType | None:
        """
        Attempt to parse *pic* as a numeric PIC clause.

        Recognised patterns (case-insensitive, normalised to upper-case)::

            9(n)         → NumericType(digits=n, signed=False, decimal_places=0)
            S9(n)        → NumericType(digits=n, signed=True,  decimal_places=0)
            9(n)V9(m)    → NumericType(digits=n+m, decimal_places=m)
            S9(n)V9(m)   → NumericType(digits=n+m, signed=True, decimal_places=m)
            9 / 99 / 999 → NumericType(digits=len_of_bare_nines, …)

        Args:
            pic:
                Upper-cased, whitespace-stripped PIC clause string.

        Returns:
            A :class:`~app.parser.semantic.types.NumericType` or ``None`` if
            the pattern does not match.
        """
        m = _RE_NUMERIC.match(pic)
        if m is None:
            return None

        signed = m.group("signed") is not None

        # Integer part
        int_n_str = m.group("int_n")
        int_bare = m.group("int_bare")
        if int_n_str:
            int_digits = int(int_n_str)
        else:
            # bare nines: first '9' is already matched; int_bare holds extra 9s
            int_digits = 1 + (len(int_bare) if int_bare else 0)

        # Decimal part
        dec_n_str = m.group("dec_n")
        dec_bare = m.group("dec_bare")
        if dec_n_str:
            dec_digits = int(dec_n_str)
        elif dec_bare is not None:
            dec_digits = 1 + len(dec_bare)  # at least one V9 was matched
        else:
            dec_digits = 0

        total_digits = int_digits + dec_digits
        return NumericType(
            digits=total_digits,
            signed=signed,
            decimal_places=dec_digits,
        )

    def _parse_alpha_pic(self, pic: str) -> AlphanumericType | None:
        """
        Attempt to parse *pic* as an alphanumeric PIC clause.

        Recognised patterns::

            X(n)         → AlphanumericType(length=n)
            X / XX / XXX → AlphanumericType(length=len_of_bare_Xs)

        Args:
            pic:
                Upper-cased, whitespace-stripped PIC clause string.

        Returns:
            An :class:`~app.parser.semantic.types.AlphanumericType` or ``None``
            if the pattern does not match.
        """
        m = _RE_ALPHA.match(pic)
        if m is None:
            return None

        len_n_str = m.group("len_n")
        len_bare = m.group("len_bare")
        if len_n_str:
            length = int(len_n_str)
        else:
            # bare Xs: first 'X' matched; len_bare holds extra Xs
            length = 1 + (len(len_bare) if len_bare else 0)

        return AlphanumericType(length=length)

    # ------------------------------------------------------------------
    # USAGE inference
    # ------------------------------------------------------------------

    def _infer_usage(self, pic: str) -> UsageType:
        """
        Infer the :class:`~app.parser.semantic.types.UsageType` from context.

        In the current AST, the USAGE clause is not surfaced as a separate
        node attribute on the symbol; this method returns
        :attr:`~app.parser.semantic.types.UsageType.DISPLAY` as the default.
        It is the extension point for when explicit USAGE information becomes
        available (e.g. from an enriched ``ElementaryItemNode``).

        Extend this method or replace it with one that accepts a USAGE string
        from the AST node when the parser is updated to capture USAGE clauses.

        Args:
            pic:
                The normalised PIC string (currently unused; provided for
                future heuristics such as detecting ``COMP`` embedded in
                extended PIC-like strings).

        Returns:
            The inferred :class:`~app.parser.semantic.types.UsageType`.
        """
        _ = pic  # reserved for future heuristic use
        return UsageType.DISPLAY

    @staticmethod
    def usage_from_string(usage_str: str) -> UsageType:
        """
        Resolve a USAGE clause string to a :class:`~app.parser.semantic.types.UsageType`.

        This is a **static utility** intended for callers that have access to
        an explicit USAGE clause value (e.g. from a future enriched AST node).

        Args:
            usage_str:
                Raw USAGE clause value as it appears in the COBOL source,
                e.g. ``"COMP"``, ``"COMP-3"``, ``"DISPLAY"``.

        Returns:
            The matching :class:`~app.parser.semantic.types.UsageType`, or
            :attr:`~app.parser.semantic.types.UsageType.DISPLAY` if the
            value is unrecognised.

        Examples:
            >>> TypeBuilder.usage_from_string("COMP-3")
            <UsageType.COMP_3: 'COMP-3'>
            >>> TypeBuilder.usage_from_string("BINARY")
            <UsageType.COMP: 'COMP'>
            >>> TypeBuilder.usage_from_string("UNKNOWN")
            <UsageType.DISPLAY: 'DISPLAY'>
        """
        return _USAGE_MAP.get(usage_str.strip().upper(), UsageType.DISPLAY)
