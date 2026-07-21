"""
Semantic Type Checker Visitor — Pass 5 of the Semantic Analysis Pipeline.

Purpose:
    Implement the fifth semantic analysis pass that traverses the COBOL AST
    and validates that statements operate on compatible semantic types using
    the :class:`~app.parser.semantic.types.CobolType` objects attached to
    :class:`~app.parser.semantic.symbols.VariableSymbol` records by the
    :class:`~app.parser.semantic.type_builder.TypeBuilder` (pass 4).

    :class:`TypeCheckerVisitor` is a
    :class:`~app.parser.semantic.visitors.SemanticVisitor` that evaluates
    type compatibility rules for COBOL statements and emits structured
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` records for
    any violation found, while **always continuing traversal** — it is never
    aborting.

Responsibilities:
    - Visit :class:`~app.parser.ast.statements.MoveStatementNode` and validate
      that the source type is compatible with the target type:

      * numeric → numeric: **allowed**
      * alphanumeric → alphanumeric: **allowed**
      * numeric → alphanumeric: **allowed** (numeric is stringified on display)
      * alphanumeric → numeric: **SEM010** (type error)
      * group → any: **allowed** (COBOL treats group as alphanumeric)
      * any → group: **allowed** (group items receive raw bytes)
      * literal → any: **allowed** (literal compatibility is deferred to runtime)
      * figurative constant → any: **allowed**
      * missing type on target: **SEM012**

    - Visit :class:`~app.parser.ast.statements.DisplayStatementNode` and
      validate that:

      * literals are always valid.
      * referenced variables have a resolved semantic type (SEM012 if absent).
      * any resolved type (numeric, alphanumeric, group) is valid for DISPLAY.

    - Provide an extension hook
      :meth:`_check_arithmetic_operand` for validating that operands to
      arithmetic statements are numeric (**SEM011**).  Arithmetic statement
      nodes are not yet represented in the AST; the hook is ready to be
      wired when they are.

    - Produce **SEM013** for any statement that requests an operation that the
      type system cannot support (reserved for future extensions such as
      ``NATIONAL`` items in numeric contexts).

Non-responsibilities:
    - Symbol registration (pass 1).
    - Reference resolution (pass 2).
    - Structural validation (pass 3).
    - PIC interpretation and type construction (pass 4).
    - Implicit coercions or conversions.
    - Storage layout or offset calculation.
    - Code generation.
    - Constant folding.

Design for extensibility:
    Compatibility rules are expressed as small, focused private ``_check_*``
    methods.  Adding a new statement type requires:

    1. Overriding the corresponding ``visit_*`` hook.
    2. Implementing a ``_check_<statement>`` method.
    3. Registering any new diagnostic code in ``DIAGNOSTIC_CODES``.

    No existing methods need modification.  The
    :meth:`_compatible_move` predicate is the single place where MOVE
    compatibility rules live; future additions (edited PIC, NATIONAL, UTF-8,
    floating-point, OCCURS) extend that predicate only.

    Extension hooks provided:

    * :meth:`_check_arithmetic_operand` — called with an operand name once
      arithmetic nodes are represented in the AST.
    * :meth:`_check_unsupported_operation` — called whenever a statement
      requests an operation that the type model cannot sanction.

Diagnostic codes emitted:
    ========  ======================================================
    SEM010    Alphanumeric source moved to numeric target.
    SEM011    Non-numeric operand in arithmetic statement.
    SEM012    Variable referenced but has no resolved semantic type.
    SEM013    Operation not supported on this type (reserved).
    ========  ======================================================

Compatibility matrix (MOVE statement):
    +-----------------+-------------+----------------+-------------+
    | Source \\ Target | Numeric     | Alphanumeric   | Group       |
    +=================+=============+================+=============+
    | Numeric         | ✓ allowed   | ✓ allowed      | ✓ allowed   |
    +-----------------+-------------+----------------+-------------+
    | Alphanumeric    | ✗ SEM010    | ✓ allowed      | ✓ allowed   |
    +-----------------+-------------+----------------+-------------+
    | Group           | ✓ allowed   | ✓ allowed      | ✓ allowed   |
    +-----------------+-------------+----------------+-------------+
    | Literal         | ✓ allowed   | ✓ allowed      | ✓ allowed   |
    +-----------------+-------------+----------------+-------------+
    | Figurative const| ✓ allowed   | ✓ allowed      | ✓ allowed   |
    +-----------------+-------------+----------------+-------------+

Dependencies:
    - :mod:`app.parser.ast.statements`       — statement node types.
    - :mod:`app.parser.semantic.context`     — ``SymbolTable``.
    - :mod:`app.parser.semantic.diagnostics` — ``SemanticDiagnostic``, ``SemanticSeverity``.
    - :mod:`app.parser.semantic.symbols`     — ``VariableSymbol``.
    - :mod:`app.parser.semantic.types`       — ``CobolType``, ``NumericType``,
      ``AlphanumericType``, ``GroupType``.
    - :mod:`app.parser.semantic.visitors`    — ``SemanticVisitor`` base.
    - Loguru for structured logging.

Examples:
    Using the visitor as a standalone pass::

        from app.parser.semantic.context import SymbolTable
        from app.parser.semantic.type_checker import TypeCheckerVisitor
        from app.parser.semantic.visitors import traverse_program

        # table already populated and typed by passes 1–4
        diagnostics = []
        checker = TypeCheckerVisitor(table=table, diagnostics=diagnostics)
        traverse_program(program_node, checker)

        # SEM010 / SEM012 diagnostics available
        for d in diagnostics:
            print(d)

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from loguru import logger

from app.parser.ast.statements import DisplayStatementNode, MoveStatementNode
from app.parser.semantic.context import SymbolTable
from app.parser.semantic.diagnostics import SemanticDiagnostic, SemanticSeverity
from app.parser.semantic.symbols import VariableSymbol
from app.parser.semantic.types import (
    AlphanumericType,
    CobolType,
    GroupType,
    NumericType,
)
from app.parser.semantic.visitors import SemanticVisitor

__all__ = ["TypeCheckerVisitor"]

# ---------------------------------------------------------------------------
# Helpers shared with ReferenceResolverVisitor (kept local to avoid coupling)
# ---------------------------------------------------------------------------

# String / character literal starters.
_LITERAL_PREFIXES: frozenset[str] = frozenset({'"', "'"})

# Numeric literal starters (digit or sign character).
_NUMERIC_STARTERS: frozenset[str] = frozenset(
    {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "+", "-"}
)

# Well-known COBOL figurative constants — never looked up in the symbol table.
_FIGURATIVE_CONSTANTS: frozenset[str] = frozenset(
    {
        "SPACES",
        "SPACE",
        "ZEROS",
        "ZERO",
        "ZEROES",
        "HIGH-VALUES",
        "HIGH-VALUE",
        "LOW-VALUES",
        "LOW-VALUE",
        "QUOTES",
        "QUOTE",
        "ALL",
        "NULL",
        "NULLS",
    }
)


def _is_literal(token: str) -> bool:
    """
    Return ``True`` if *token* represents a literal value rather than a
    data-name reference.

    Literals include:

    * Quoted string literals (starting with ``"`` or ``'``).
    * Numeric literals (starting with a digit or ``+``/``-``).
    * COBOL figurative constants (``SPACES``, ``ZEROS``, etc.).

    Args:
        token:
            The raw operand string from a statement node.

    Returns:
        ``True`` if the token is a literal; ``False`` if it is a data-name.
    """
    if not token:
        return False
    if token[0] in _LITERAL_PREFIXES:
        return True
    if token[0] in _NUMERIC_STARTERS:
        return True
    if token.upper() in _FIGURATIVE_CONSTANTS:
        return True
    return False


# ===========================================================================
# TypeCheckerVisitor
# ===========================================================================


class TypeCheckerVisitor(SemanticVisitor):
    """
    Pass 5: validate semantic type compatibility of COBOL statements.

    :class:`TypeCheckerVisitor` traverses the COBOL AST after the
    :class:`~app.parser.semantic.type_builder.TypeBuilder` (pass 4) has
    attached :class:`~app.parser.semantic.types.CobolType` objects to every
    :class:`~app.parser.semantic.symbols.VariableSymbol` in the
    :class:`~app.parser.semantic.context.SymbolTable`.

    The visitor checks each statement it encounters against the compatibility
    rules defined in the module docstring and appends a
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` to the
    shared *diagnostics* list for each violation.  Traversal is never aborted
    — all violations in a compilation unit are reported in a single pass.

    Attributes:
        _table:
            The fully-populated and type-annotated
            :class:`~app.parser.semantic.context.SymbolTable`.
        _diagnostics:
            Shared mutable list of
            :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
            records accumulated across all passes.

    Examples:
        >>> from app.parser.semantic.context import SymbolTable
        >>> from app.parser.semantic.type_checker import TypeCheckerVisitor
        >>> checker = TypeCheckerVisitor(table=SymbolTable(), diagnostics=[])
        >>> checker._table is not None
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
                The :class:`~app.parser.semantic.context.SymbolTable`
                populated and type-annotated by the earlier passes.
            diagnostics:
                A mutable list to which
                :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
                records are appended when type violations are detected.
        """
        self._table = table
        self._diagnostics = diagnostics

    # ------------------------------------------------------------------
    # Statement visitors
    # ------------------------------------------------------------------

    def visit_move_statement(self, node: MoveStatementNode) -> None:
        """
        Validate type compatibility of a ``MOVE source TO target`` statement.

        Type-checking rules applied:

        * If *source* is a literal or figurative constant → skip (runtime).
        * If *target* is not in the symbol table → skip (SEM003 already emitted).
        * If *target* symbol has no resolved ``cobol_type`` → SEM012.
        * If *source* is a variable symbol with an alphanumeric type and
          *target* has a numeric type → SEM010.

        Args:
            node: The ``MOVE`` statement node.
        """
        source_raw = node.source.strip()
        target_raw = node.target.strip()

        logger.debug(
            "TypeCheckerVisitor: MOVE {} TO {} at {}:{}.",
            source_raw,
            target_raw,
            node.start_position.filename,
            node.start_position.line,
        )

        # --- Resolve target type -------------------------------------------
        target_sym = self._table.lookup(target_raw)
        if target_sym is None or not isinstance(target_sym, VariableSymbol):
            # Reference is undefined — already reported by pass 2; skip.
            return

        target_type = target_sym.cobol_type
        if target_type is None:
            self._emit(
                code="SEM012",
                message=(
                    f"MOVE target {target_raw!r} has no resolved semantic type; "
                    f"TypeBuilder may not have processed it."
                ),
                node=node,
            )
            return

        # --- Skip if source is a literal -----------------------------------
        if _is_literal(source_raw):
            logger.debug(
                "TypeCheckerVisitor: MOVE source {!r} is a literal — skipping.",
                source_raw,
            )
            return

        # --- Resolve source type -------------------------------------------
        source_sym = self._table.lookup(source_raw)
        if source_sym is None or not isinstance(source_sym, VariableSymbol):
            # Source undefined — already reported by pass 2; skip.
            return

        source_type = source_sym.cobol_type
        if source_type is None:
            self._emit(
                code="SEM012",
                message=(
                    f"MOVE source {source_raw!r} has no resolved semantic type; "
                    f"TypeBuilder may not have processed it."
                ),
                node=node,
            )
            return

        # --- Check compatibility -------------------------------------------
        if not self._compatible_move(source_type, target_type):
            self._emit(
                code="SEM010",
                message=(
                    f"incompatible MOVE: cannot move {source_type.category!r} "
                    f"value ({source_raw!r}) to numeric target {target_raw!r}."
                ),
                node=node,
            )
            logger.warning(
                "TypeCheckerVisitor: SEM010 — MOVE {} → {} incompatible types.",
                source_raw,
                target_raw,
            )

    def visit_display_statement(self, node: DisplayStatementNode) -> None:
        """
        Validate the operand of a ``DISPLAY`` statement.

        DISPLAY is permissive: any literal or any variable with a resolved
        semantic type is valid.  Only an undeclared identifier with no resolved
        type produces a diagnostic.

        Rules:

        * If the operand is a literal or figurative constant → valid (skip).
        * If the operand names a variable with a resolved type → valid.
        * If the operand names a variable with no resolved type → SEM012.
        * If the operand is not in the symbol table → skip (SEM003 from pass 2).

        Args:
            node: The ``DISPLAY`` statement node.
        """
        operand_raw = node.operand.strip()

        logger.debug(
            "TypeCheckerVisitor: DISPLAY {} at {}:{}.",
            operand_raw,
            node.start_position.filename,
            node.start_position.line,
        )

        if _is_literal(operand_raw):
            # Literals are always valid for DISPLAY.
            return

        sym = self._table.lookup(operand_raw)
        if sym is None or not isinstance(sym, VariableSymbol):
            # Undefined reference — already reported by pass 2; skip.
            return

        if sym.cobol_type is None:
            self._emit(
                code="SEM012",
                message=(
                    f"DISPLAY operand {operand_raw!r} has no resolved semantic "
                    f"type; TypeBuilder may not have processed it."
                ),
                node=node,
            )
            return

        # Any resolved type (numeric, alphanumeric, group) is valid for DISPLAY.
        logger.debug(
            "TypeCheckerVisitor: DISPLAY {!r} — type {} OK.",
            operand_raw,
            sym.cobol_type.category,
        )

    # ------------------------------------------------------------------
    # Arithmetic extension hook
    # ------------------------------------------------------------------

    def _check_arithmetic_operand(
        self,
        operand_name: str,
        node: object,
    ) -> None:
        """
        Validate that *operand_name* resolves to a numeric type.

        This method is the extension point for arithmetic statement support
        (ADD, SUBTRACT, MULTIPLY, DIVIDE, COMPUTE).  It is not called by
        any existing ``visit_*`` hook because arithmetic nodes are not yet
        represented in the AST.  Call it from future ``visit_add_statement``,
        ``visit_compute_statement``, etc. hooks.

        Rules:

        * If the operand is a literal → valid (skip).
        * If the operand names a variable with a numeric type → valid.
        * If the operand names a variable with a non-numeric type → SEM011.
        * If the operand names a variable with no resolved type → SEM012.
        * If the operand is not in the symbol table → skip (SEM003 from pass 2).

        Args:
            operand_name:
                Raw operand string from the arithmetic statement node.
            node:
                The statement node (used for position in the diagnostic).
        """
        operand_raw = operand_name.strip()
        if _is_literal(operand_raw):
            return

        sym = self._table.lookup(operand_raw)
        if sym is None or not isinstance(sym, VariableSymbol):
            return  # Undefined — SEM003 already emitted.

        if sym.cobol_type is None:
            self._emit(
                code="SEM012",
                message=(
                    f"arithmetic operand {operand_raw!r} has no resolved "
                    f"semantic type."
                ),
                node=node,
            )
            return

        if not isinstance(sym.cobol_type, NumericType):
            self._emit(
                code="SEM011",
                message=(
                    f"invalid arithmetic operand: {operand_raw!r} has type "
                    f"{sym.cobol_type.category!r} but numeric type is required."
                ),
                node=node,
            )
            logger.warning(
                "TypeCheckerVisitor: SEM011 — arithmetic operand {!r} is {}.",
                operand_raw,
                sym.cobol_type.category,
            )

    def _check_unsupported_operation(
        self,
        operation: str,
        type_name: str,
        node: object,
    ) -> None:
        """
        Emit a SEM013 diagnostic for an operation that is not supported on a type.

        This is the extension point for future type constraints (e.g.
        ``NATIONAL`` items in arithmetic contexts, ``POINTER`` items in
        comparison contexts, etc.).

        Args:
            operation:
                A short human-readable name for the operation (e.g.
                ``"ADD"``, ``"INSPECT"``).
            type_name:
                The :attr:`~app.parser.semantic.types.CobolType.category`
                string of the offending type.
            node:
                The statement node (used for position in the diagnostic).
        """
        self._emit(
            code="SEM013",
            message=(
                f"operation {operation!r} is not supported on type {type_name!r}."
            ),
            node=node,
        )
        logger.warning(
            "TypeCheckerVisitor: SEM013 — {} not supported on {}.",
            operation,
            type_name,
        )

    # ------------------------------------------------------------------
    # Compatibility predicates
    # ------------------------------------------------------------------

    @staticmethod
    def _compatible_move(source: CobolType, target: CobolType) -> bool:
        """
        Return ``True`` if moving *source* type into *target* type is valid.

        This is the single authority for MOVE type-compatibility rules.
        Extend this method to support future types without changing callers.

        Compatibility matrix:

        +-----------------+----------+--------------+-------+
        | source \\ target | Numeric  | Alphanumeric | Group |
        +=================+==========+==============+=======+
        | NumericType     | ✓        | ✓            | ✓     |
        +-----------------+----------+--------------+-------+
        | AlphanumericType| ✗        | ✓            | ✓     |
        +-----------------+----------+--------------+-------+
        | GroupType       | ✓        | ✓            | ✓     |
        +-----------------+----------+--------------+-------+

        Only alphanumeric → numeric is prohibited.

        Args:
            source:
                The :class:`~app.parser.semantic.types.CobolType` of the
                MOVE source.
            target:
                The :class:`~app.parser.semantic.types.CobolType` of the
                MOVE target.

        Returns:
            ``True`` if the assignment is type-compatible; ``False`` otherwise.

        Examples:
            >>> from app.parser.semantic.types import NumericType, AlphanumericType
            >>> TypeCheckerVisitor._compatible_move(
            ...     AlphanumericType(length=10), NumericType(digits=5)
            ... )
            False
            >>> TypeCheckerVisitor._compatible_move(
            ...     NumericType(digits=5), AlphanumericType(length=10)
            ... )
            True
        """
        # Group source: always allowed (COBOL treats group as a raw byte area).
        if isinstance(source, GroupType):
            return True

        # Group target: always allowed (raw byte area accepts anything).
        if isinstance(target, GroupType):
            return True

        # Alphanumeric → Numeric: the one prohibited combination.
        if isinstance(source, AlphanumericType) and isinstance(target, NumericType):
            return False

        # All other combinations (numeric→numeric, numeric→alpha, alpha→alpha).
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(
        self,
        code: str,
        message: str,
        node: object,
    ) -> None:
        """
        Append a :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
        to the shared diagnostics list.

        Args:
            code:
                The diagnostic code (e.g. ``"SEM010"``).
            message:
                Human-readable description of the violation.
            node:
                The AST node supplying the source position.  Must have a
                ``start_position`` attribute.
        """
        from app.parser.lexer.position import Position

        pos = getattr(node, "start_position", None)
        if not isinstance(pos, Position):
            logger.warning(  # pragma: no cover
                "TypeCheckerVisitor._emit: node has no valid start_position."
            )
            return  # pragma: no cover

        diag = SemanticDiagnostic(
            message=message,
            position=pos,
            severity=SemanticSeverity.ERROR,
            code=code,
        )
        self._diagnostics.append(diag)
        logger.warning(
            "TypeCheckerVisitor: {} — {} at {}:{}.",
            code,
            message,
            pos.filename,
            pos.line,
        )
