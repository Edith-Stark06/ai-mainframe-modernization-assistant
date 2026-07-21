"""
Reference Resolution Visitor.

Purpose:
    Implement the second semantic analysis pass that traverses the COBOL AST
    and resolves every identifier reference against the
    :class:`~app.parser.semantic.context.SymbolTable` populated by
    :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`.

    :class:`ReferenceResolverVisitor` is the **public, reusable** visitor
    responsible for reference resolution.  It separates resolution from both
    symbol collection (pass 1) and the orchestration owned by
    :class:`~app.parser.semantic.analyzer.SemanticAnalyzer`, allowing the
    same visitor to be composed into future multi-pass pipelines or used
    independently.

Responsibilities:
    - Resolve ``MOVE`` statement operands — :attr:`source` and :attr:`target`
      — against variable symbols in the :class:`~app.parser.semantic.context.SymbolTable`.
    - Resolve ``DISPLAY`` statement operands against variable symbols
      (literal string operands, starting with ``"`` or ``'``, are skipped).
    - Emit ``"SEM003"`` diagnostics for each unresolved variable identifier.
    - Emit ``"SEM004"`` diagnostics for each unresolved paragraph reference
      (forward-looking: paragraph ``PERFORM`` targets are not yet in the AST,
      but the hook is provided for future use).
    - Emit ``"SEM005"`` diagnostics for each unresolved section reference.
    - Continue traversal after every error — never abort.

Non-responsibilities:
    - Symbol registration (pass 1, delegated to
      :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`).
    - Driving the AST traversal (delegated to
      :func:`~app.parser.semantic.visitors.traverse_program`).
    - Type checking or expression analysis.
    - Control-flow or data-flow analysis.
    - Constant folding or optimisation.

Design for extensibility:
    The resolver is designed to accommodate future requirements:

    * **Nested scopes**: the :meth:`_resolve_identifier` helper accepts an
      optional ``scope`` parameter reserved for qualified-name look-up.
    * **Qualified names**: callers may pass a ``qualifier`` to
      :meth:`_resolve_identifier` to support ``OF``/``IN`` qualifiers.
    * **COPYBOOK symbols**: a composite :class:`~app.parser.semantic.context.SymbolTable`
      can be supplied that delegates to multiple underlying tables.
    * **External program references**: additional pass subclasses can be
      composed by the analyser.

Dependencies:
    - :mod:`app.parser.ast.statements`       — statement node types.
    - :mod:`app.parser.semantic.context`     — ``SymbolTable``.
    - :mod:`app.parser.semantic.diagnostics` — ``SemanticDiagnostic``, ``SemanticSeverity``.
    - :mod:`app.parser.semantic.symbols`     — ``SymbolKind``.
    - :mod:`app.parser.semantic.visitors`    — ``SemanticVisitor`` base.
    - Loguru for structured logging.

Examples:
    Using the resolver as a standalone second pass::

        from app.parser.semantic.context import SymbolTable
        from app.parser.semantic.reference_resolver import ReferenceResolverVisitor
        from app.parser.semantic.visitors import traverse_program

        # table already populated by SymbolCollectorVisitor
        diagnostics = []
        resolver = ReferenceResolverVisitor(table=table, diagnostics=diagnostics)
        traverse_program(program_node, resolver)

        diagnostics  # any SEM003 / SEM004 / SEM005 errors

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
from app.parser.semantic.symbols import SymbolKind
from app.parser.semantic.visitors import SemanticVisitor

__all__ = ["ReferenceResolverVisitor"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Prefixes that identify a literal value (not a data-name reference).
_LITERAL_PREFIXES: frozenset[str] = frozenset({'"', "'"})

# Numeric literal pattern: any token whose first character is a digit or sign.
_NUMERIC_STARTERS: frozenset[str] = frozenset(
    {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "+", "-"}
)

# Well-known COBOL figurative constants that are not declared variables.
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
    Return ``True`` when *token* is a literal value, not a data-name.

    The following token forms are treated as literals and skipped by
    reference resolution:

    * Quoted string literals — begin with ``"`` or ``'``.
    * Numeric literals       — begin with a digit, ``+``, or ``-``.
    * COBOL figurative constants — ``SPACES``, ``ZEROS``, etc.

    Args:
        token: The raw operand text to classify.

    Returns:
        ``True`` if *token* is a literal; ``False`` if it should be
        resolved as a data-name.

    Examples:
        >>> _is_literal('"HELLO"')
        True
        >>> _is_literal('1')
        True
        >>> _is_literal('SPACES')
        True
        >>> _is_literal('WS-COUNT')
        False
    """
    if not token:
        return True
    if token[0] in _LITERAL_PREFIXES:
        return True
    if token[0] in _NUMERIC_STARTERS:
        return True
    if token.upper() in _FIGURATIVE_CONSTANTS:
        return True
    return False


# ===========================================================================
# ReferenceResolverVisitor
# ===========================================================================


class ReferenceResolverVisitor(SemanticVisitor):
    """
    Public semantic visitor that resolves identifier references against the
    symbol table.

    :class:`ReferenceResolverVisitor` is the second semantic pass.  It
    expects a fully-populated :class:`~app.parser.semantic.context.SymbolTable`
    (produced by :class:`~app.parser.semantic.symbol_collector.SymbolCollectorVisitor`)
    and traverses the AST looking for identifier references in statement
    operands.  For each reference that cannot be resolved a structured
    :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` is appended
    to the *diagnostics* list and traversal continues.

    **Resolution rules**

    - ``MOVE source TO target`` — both *source* and *target* are resolved as
      variable references unless the token is a literal or a figurative
      constant.
    - ``DISPLAY operand`` — the *operand* is resolved as a variable reference
      unless it is a literal or figurative constant.
    - Unknown identifier → ``"SEM003"`` diagnostic.

    **Extensibility**

    The private :meth:`_resolve_identifier` helper is the single resolution
    point.  Future passes can subclass :class:`ReferenceResolverVisitor` and
    override only :meth:`_resolve_identifier` to introduce nested scopes,
    qualified names (``OF``/``IN``), or COPYBOOK merging without touching
    the visitor hooks.

    Attributes:
        _table:
            The populated :class:`~app.parser.semantic.context.SymbolTable`.
        _diagnostics:
            Mutable list of
            :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
            records accumulated during traversal.

    Examples:
        >>> from app.parser.semantic.context import SymbolTable
        >>> from app.parser.semantic.reference_resolver import ReferenceResolverVisitor
        >>> table = SymbolTable()
        >>> resolver = ReferenceResolverVisitor(table=table, diagnostics=[])
        >>> resolver._table is table
        True
    """

    def __init__(
        self,
        table: SymbolTable,
        diagnostics: list[SemanticDiagnostic],
    ) -> None:
        """
        Initialise the resolver with the populated symbol table.

        Args:
            table:
                A :class:`~app.parser.semantic.context.SymbolTable` that has
                already been populated by the symbol-collection pass.
            diagnostics:
                A mutable list to which
                :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic`
                records are appended when unresolved references are detected.
        """
        self._table = table
        self._diagnostics = diagnostics

    # ------------------------------------------------------------------
    # Statement visit hooks
    # ------------------------------------------------------------------

    def visit_move_statement(self, node: MoveStatementNode) -> None:
        """
        Resolve the ``source`` and ``target`` operands of a ``MOVE`` statement.

        Literal and figurative-constant operands are skipped silently.
        Each data-name operand that cannot be found in the symbol table
        produces a ``"SEM003"`` diagnostic.

        Args:
            node: The ``MOVE`` statement node.
        """
        logger.debug(
            "ReferenceResolverVisitor: resolving MOVE '{}' TO '{}' at {}:{}.",
            node.source,
            node.target,
            node.start_position.filename,
            node.start_position.line,
        )
        self._resolve_variable_operand(node.source, node.start_position)
        self._resolve_variable_operand(node.target, node.start_position)

    def visit_display_statement(self, node: DisplayStatementNode) -> None:
        """
        Resolve the ``operand`` of a ``DISPLAY`` statement.

        Literal and figurative-constant operands are skipped silently.
        A data-name operand that cannot be found in the symbol table
        produces a ``"SEM003"`` diagnostic.

        Args:
            node: The ``DISPLAY`` statement node.
        """
        logger.debug(
            "ReferenceResolverVisitor: resolving DISPLAY '{}' at {}:{}.",
            node.operand,
            node.start_position.filename,
            node.start_position.line,
        )
        self._resolve_variable_operand(node.operand, node.start_position)

    # ------------------------------------------------------------------
    # Internal resolution helpers
    # ------------------------------------------------------------------

    def _resolve_variable_operand(
        self,
        token: str,
        position: object,
    ) -> None:
        """
        Resolve *token* as a variable reference.

        If *token* is a literal or figurative constant it is silently
        skipped.  Otherwise :meth:`_resolve_identifier` is called with
        ``expected_kind=SymbolKind.VARIABLE`` and ``code="SEM003"``.

        Args:
            token:
                The raw operand text extracted from the statement node.
            position:
                The source :class:`~app.parser.lexer.position.Position`
                of the statement, used in diagnostics.
        """
        if _is_literal(token.strip()):
            logger.debug(
                "ReferenceResolverVisitor: '{}' is a literal — skipping.", token
            )
            return
        self._resolve_identifier(
            name=token.strip(),
            position=position,
            expected_kind=SymbolKind.VARIABLE,
            code="SEM003",
        )

    def _resolve_paragraph_reference(
        self,
        name: str,
        position: object,
    ) -> None:
        """
        Resolve *name* as a paragraph reference.

        Emits ``"SEM004"`` if the paragraph is not registered.

        Args:
            name:
                The paragraph name to resolve.
            position:
                The source :class:`~app.parser.lexer.position.Position`
                of the reference.
        """
        self._resolve_identifier(
            name=name,
            position=position,
            expected_kind=SymbolKind.PARAGRAPH,
            code="SEM004",
        )

    def _resolve_section_reference(
        self,
        name: str,
        position: object,
    ) -> None:
        """
        Resolve *name* as a section reference.

        Emits ``"SEM005"`` if the section is not registered.

        Args:
            name:
                The section name to resolve.
            position:
                The source :class:`~app.parser.lexer.position.Position`
                of the reference.
        """
        self._resolve_identifier(
            name=name,
            position=position,
            expected_kind=None,  # sections not yet in SymbolKind
            code="SEM005",
        )

    def _resolve_identifier(
        self,
        name: str,
        position: object,
        expected_kind: SymbolKind | None,
        code: str,
        *,
        scope: object = None,
        qualifier: str | None = None,
    ) -> bool:
        """
        Core resolution helper.

        Look up *name* in the symbol table.  If the symbol is found and
        its kind matches *expected_kind* (or *expected_kind* is ``None``),
        the resolution succeeds and ``True`` is returned.  Otherwise a
        :class:`~app.parser.semantic.diagnostics.SemanticDiagnostic` with
        *code* is appended and ``False`` is returned.

        This is the **single resolution point** for the whole pass.
        Future subclasses override this method to introduce:

        - Nested scope walk (use the *scope* parameter).
        - Qualified-name look-up (use the *qualifier* parameter).
        - COPYBOOK or external-program symbol tables.

        Args:
            name:
                The identifier to resolve (case-insensitive).
            position:
                Source :class:`~app.parser.lexer.position.Position`
                of the reference site, used in the diagnostic.
            expected_kind:
                The :class:`~app.parser.semantic.symbols.SymbolKind` the
                resolved symbol must have, or ``None`` to accept any kind.
            code:
                The diagnostic code to emit on resolution failure.
            scope:
                Reserved for future nested-scope look-up.  Currently unused.
            qualifier:
                Reserved for future qualified-name resolution
                (e.g. ``OF``/``IN`` qualifiers).  Currently unused.

        Returns:
            ``True`` if the identifier was resolved successfully.
            ``False`` if resolution failed and a diagnostic was emitted.
        """
        from app.parser.lexer.position import Position

        if not isinstance(position, Position):  # pragma: no cover
            return False

        sym = self._table.lookup(name)
        if sym is not None and (expected_kind is None or sym.kind is expected_kind):
            logger.debug(
                "ReferenceResolverVisitor: resolved {!r} → {}.", name, sym.kind
            )
            return True

        # Symbol missing or wrong kind — emit diagnostic.
        if (
            sym is not None
            and expected_kind is not None
            and sym.kind is not expected_kind
        ):
            msg = (
                f"identifier {name!r} refers to a {sym.kind.value} "
                f"but a {expected_kind.value} was expected"
            )
        else:
            kind_label = expected_kind.value if expected_kind is not None else "symbol"
            msg = f"undefined {kind_label}: {name!r}"

        logger.warning(
            "ReferenceResolverVisitor: {} at {}:{}.",
            msg,
            position.filename,
            position.line,
        )
        self._diagnostics.append(
            SemanticDiagnostic(
                message=msg,
                position=position,
                severity=SemanticSeverity.ERROR,
                code=code,
            )
        )
        return False
