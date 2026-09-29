"""
Statement AST Nodes.

Purpose:
    Define the immutable AST nodes that represent individual executable
    COBOL statements parsed from the PROCEDURE DIVISION.

    Each node carries the structural tokens captured during parsing.
    Nodes are deliberately thin; semantic analysis is a separate concern.

Responsibilities:
    - Provide :class:`StatementNode` — the abstract base for all statement
      nodes.
    - Provide :class:`DisplayStatementNode` — a ``DISPLAY`` statement.
    - Provide :class:`MoveStatementNode`    — a ``MOVE ... TO ...`` statement.
    - Provide :class:`StopRunStatementNode` — a ``STOP RUN`` statement.
    - Provide :class:`GobackStatementNode`  — a ``GOBACK`` statement.
    - Remain immutable after construction (``frozen=True`` dataclasses).

Non-responsibilities:
    - Parsing or lexical analysis.
    - Semantic validation (data types, scope, etc.).
    - IF, EVALUATE, PERFORM, GO TO, CALL statements.
    - ``COMPUTE ROUNDED`` and ``COMPUTE`` with an intrinsic ``FUNCTION``
      operand (task #stage35): recognised but not represented; such a
      COMPUTE is left to the ordinary unsupported-statement path.

Dependencies:
    - :mod:`app.parser.ast.node` — ``ASTNode`` base class.
    - Python standard library only (``dataclasses``).

Examples:
    Creating a DISPLAY statement node::

        from app.parser.ast.statements import DisplayStatementNode
        from app.parser.lexer.position import Position

        pos = Position(line=10, column=4, offset=200, filename="prog.cbl")
        node = DisplayStatementNode(
            start_position=pos,
            end_position=pos,
            operand="\"HELLO\"",
        )
        node.operand  # '"HELLO"'

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.parser.ast.node import ASTNode

__all__ = [
    "AcceptStatementNode",
    "AddStatementNode",
    "ArithmeticExpression",
    "BinaryExpression",
    "CallStatementNode",
    "ComputeStatementNode",
    "ConditionTerm",
    "DisplayStatementNode",
    "DivideStatementNode",
    "GoToStatementNode",
    "GobackStatementNode",
    "IfStatementNode",
    "MoveStatementNode",
    "MultiplyStatementNode",
    "OperandExpression",
    "PerformStatementNode",
    "PerformTargetUntilStatementNode",
    "PerformUntilStatementNode",
    "PerformVaryingStatementNode",
    "ReadStatementNode",
    "StatementNode",
    "StopRunStatementNode",
    "Subscript",
    "SubtractStatementNode",
]


@dataclass(frozen=True)
class Subscript:
    """
    One COBOL table subscript — a single-dimension index into an OCCURS
    item, preserved exactly as written (task #stage32).

    COBOL's own 1-based subscript meaning is never adjusted here: a
    ``WS-ITEM(2)`` reference carries ``value="2"`` unchanged, not ``"1"``.
    The parser's job is to represent the source faithfully; translating a
    subscript into a 0-based Java array index is a Java-generation
    concern (Stage 33), not an AST concern — see
    :mod:`app.ir.instructions`'s parallel ``IRSubscript`` for why the
    ``-1`` adjustment belongs downstream, applied exactly once, rather
    than here or duplicated across multiple backend emitters.

    Attributes:
        kind:
            ``"literal"`` for a bare integer subscript (``WS-ITEM(2)``)
            or ``"identifier"`` for a data-name subscript
            (``WS-ITEM(WS-I)``). An arithmetic subscript
            (``WS-ITEM(WS-I + 1)``) is out of this stage's scope and is
            never represented by this node — such a reference falls back
            to the pre-existing flat-string operand instead (see
            :func:`~app.parser.syntax.procedure_parser.ProcedureDivisionParser._try_read_subscripted_reference`).
        value:
            The subscript's own text: the literal digits (``"2"``) or
            the COBOL data-name (``"WS-I"``), unmodified.

    Examples:
        >>> Subscript(kind="literal", value="2")
        Subscript(kind='literal', value='2')
        >>> Subscript(kind="identifier", value="WS-I")
        Subscript(kind='identifier', value='WS-I')
    """

    kind: str
    value: str


@dataclass(frozen=True)
class StatementNode(ASTNode):
    """
    Abstract base for all PROCEDURE DIVISION statement nodes.

    Every concrete statement node inherits from this class and gains the
    standard ``start_position`` / ``end_position`` span from
    :class:`~app.parser.ast.node.ASTNode`.

    Concrete subclasses must implement :meth:`accept` to call the
    appropriate visitor method.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=1, column=1, offset=0, filename="x.cbl")
        >>> # StatementNode is abstract — instantiate a concrete subclass.
    """

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_statement(self)`` if available.

        Concrete subclasses override this with a more specific method
        name.  The base implementation provides a fallback that works
        with any generic visitor.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class DisplayStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``DISPLAY`` statement.

    Captures all operand tokens from immediately after ``DISPLAY`` up to
    the terminating period as a single concatenated string.

    COBOL syntax example::

        DISPLAY "HELLO".
        DISPLAY WS-COUNT.

    Attributes:
        start_position:
            Source position of the ``DISPLAY`` keyword.
        end_position:
            Source position of the terminating period.
        operand:
            The raw operand text (e.g. ``'"HELLO"'``, ``'WS-COUNT'``).
            For a multi-operand ``DISPLAY`` this is the operands joined
            by single spaces, exactly as it always was.
        operands:
            Each operand as its own string, populated only when the
            statement has two or more (``DISPLAY 'TOTAL: ' WS-TOTAL``
            gives ``("'TOTAL: '", "WS-TOTAL")``); empty otherwise. Kept
            separately because the joined ``operand`` cannot tell where
            one operand ends and the next begins.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=10, column=4, offset=200, filename="x.cbl")
        >>> node = DisplayStatementNode(
        ...     start_position=pos, end_position=pos, operand='"HELLO"',
        ... )
        >>> node.operand
        '"HELLO"'
    """

    operand: str
    operand_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    operands: tuple[str, ...] = field(default=(), metadata={"omit_if_empty": True})

    @property
    def display_operands(self) -> tuple[str, ...]:
        """
        Every operand this ``DISPLAY`` writes, in source order.

        ``operands`` when the statement has two or more operands
        (``DISPLAY 'TOTAL: ' WS-TOTAL``); otherwise the single
        ``operand`` -- so a consumer can iterate one uniform list
        without caring which shape the parser produced.
        """
        return self.operands or (self.operand,)

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_display_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_display_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class AcceptStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``ACCEPT`` statement.

    Captures the target operand token from immediately after ``ACCEPT`` up to
    the terminating period as a single string.

    COBOL syntax example::

        ACCEPT WS-DATE.
        ACCEPT WS-INPUT.

    Attributes:
        start_position:
            Source position of the ``ACCEPT`` keyword.
        end_position:
            Source position of the terminating period.
        target:
            The raw operand text (e.g. ``'WS-DATE'``).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=11, column=4, offset=220, filename="x.cbl")
        >>> node = AcceptStatementNode(
        ...     start_position=pos, end_position=pos, target="WS-DATE",
        ... )
        >>> node.target
        'WS-DATE'
    """

    target: str

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_accept_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_accept_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class MoveStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``MOVE ... TO ...`` statement.

    Captures the source operand (everything between ``MOVE`` and ``TO``)
    and the target operand (everything between ``TO`` and the period).

    COBOL syntax example::

        MOVE 1 TO WS-COUNT.
        MOVE WS-NAME TO DISPLAY-NAME.

    Attributes:
        start_position:
            Source position of the ``MOVE`` keyword.
        end_position:
            Source position of the terminating period.
        source:
            The source operand text (e.g. ``'1'``, ``'WS-NAME'``).
        target:
            The target data-name text (e.g. ``'WS-COUNT'``).

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=5, column=4, offset=80, filename="x.cbl")
        >>> node = MoveStatementNode(
        ...     start_position=pos, end_position=pos,
        ...     source="1", target="WS-COUNT",
        ... )
        >>> node.source
        '1'
        >>> node.target
        'WS-COUNT'
    """

    source: str
    target: str
    source_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    target_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_move_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_move_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class AddStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``ADD ... TO ...`` statement.
    """

    left: str
    right: str
    left_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_add_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class SubtractStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``SUBTRACT ... FROM ...`` statement.
    """

    left: str
    right: str
    left_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_subtract_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class MultiplyStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``MULTIPLY ... BY ...`` statement.
    """

    left: str
    right: str
    left_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_multiply_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class DivideStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``DIVIDE ... INTO ...`` statement.
    """

    left: str
    right: str
    left_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_divide_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class OperandExpression:
    """
    One leaf of a ``COMPUTE`` arithmetic expression tree (task #stage35):
    a numeric literal or an identifier, optionally subscripted.

    A COMPUTE expression's operand shape is identical to every other
    arithmetic statement's operand — the same numeric-literal-or-identifier
    text, and the same single-dimension ``Subscript`` (task #stage32) when
    subscripted. It is wrapped in its own node here only because an
    expression *tree* has more than the one flat operand pair
    :class:`AddStatementNode` and its siblings carry.

    Attributes:
        value:
            The operand's raw text: a numeric literal (``"100.00"``) or a
            data-name (``"WS-PRICE"``), unmodified — classified as one or
            the other downstream, the same way every other arithmetic
            operand already is (:meth:`app.ir.builder.IRBuilder.build_operand`).
        subscript:
            A single-dimension subscript (literal or identifier) when
            ``value`` names a table element, empty otherwise. Reuses
            :class:`Subscript` unchanged — Stage 32/33's subscript
            representation is not duplicated or redesigned here.

    Examples:
        >>> OperandExpression(value="WS-PRICE")
        OperandExpression(value='WS-PRICE', subscript=())
        >>> OperandExpression(value="WS-PRICE", subscript=(Subscript(kind="identifier", value="WS-I"),))
        OperandExpression(value='WS-PRICE', subscript=(Subscript(kind='identifier', value='WS-I'),))
    """

    value: str
    subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )


@dataclass(frozen=True)
class BinaryExpression:
    """
    One ``left operator right`` node of a ``COMPUTE`` arithmetic
    expression tree (task #stage35).

    Parenthesization and operator precedence are represented purely by
    tree shape — a parenthesized sub-expression is simply a nested
    :class:`BinaryExpression`/:class:`OperandExpression`, exactly the way
    the source grouped it — there is no separate "this was parenthesized"
    flag. Rendering a tree back to source-equivalent text (Java generation,
    task #stage35) reconstructs parentheses only where evaluation order
    would otherwise change, via a standard precedence-aware printer; see
    :meth:`app.ir.instructions.IRCompute.expression_text` and
    :func:`app.backend.java.statement_emitter.emit_compute`.

    Attributes:
        operator:
            One of ``"+"``, ``"-"``, ``"*"``, ``"/"`` — the only
            arithmetic operators evidenced in the 45-source training
            corpus (see docs/MMIM_V2_DATASET_AUDIT.md's Stage 35 entry).
            Exponentiation, and any other COBOL arithmetic operator, is
            out of scope: never produced by this parser.
        left:
            The left operand — an :class:`OperandExpression` or a nested
            :class:`BinaryExpression`.
        right:
            The right operand — an :class:`OperandExpression` or a nested
            :class:`BinaryExpression`.

    Examples:
        >>> expr = BinaryExpression(
        ...     operator="+",
        ...     left=OperandExpression(value="WS-A"),
        ...     right=OperandExpression(value="WS-B"),
        ... )
        >>> expr.operator
        '+'
    """

    operator: str
    left: "ArithmeticExpression"
    right: "ArithmeticExpression"


#: A COMPUTE expression node: either a leaf operand or a binary operation
#: on two further expression nodes (task #stage35).
ArithmeticExpression = OperandExpression | BinaryExpression


@dataclass(frozen=True)
class ComputeStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``COMPUTE target = expression``
    statement (task #stage35).

    Unlike :class:`AddStatementNode` and its siblings — a fixed pair of
    flat operand strings, because their COBOL grammar only ever has two
    operands — ``COMPUTE``'s right-hand side is an arbitrary arithmetic
    expression, so it is carried as a structured :data:`ArithmeticExpression`
    tree rather than flattened into text (task #stage35's explicit
    architectural rule: no string-flattened expressions).

    ``COMPUTE ROUNDED`` and a ``FUNCTION`` intrinsic-function operand are
    recognised by the parser but never produce this node — see
    :meth:`~app.parser.syntax.procedure_parser.ProcedureDivisionParser._compute_has_supported_syntax`.

    Attributes:
        target:
            The assignment target's data-name, unmodified.
        expression:
            The right-hand-side expression tree.
        target_subscript:
            A single-dimension subscript when ``target`` names a table
            element (e.g. ``COMPUTE EXTENDED-LINE-VAL(1) = ...``), empty
            otherwise. Reuses :class:`Subscript` unchanged.

    Examples:
        >>> node = ComputeStatementNode(
        ...     start_position=None,  # doctest: +SKIP
        ...     end_position=None,  # doctest: +SKIP
        ...     target="WS-TOTAL",
        ...     expression=BinaryExpression(
        ...         operator="+",
        ...         left=OperandExpression(value="WS-A"),
        ...         right=OperandExpression(value="WS-B"),
        ...     ),
        ... )
        >>> node.target
        'WS-TOTAL'
    """

    target: str
    expression: ArithmeticExpression
    target_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_compute_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class StopRunStatementNode(StatementNode):
    """
    Immutable AST node for the COBOL ``STOP RUN`` statement.

    ``STOP RUN`` terminates program execution and transfers control
    back to the operating system.

    COBOL syntax example::

        STOP RUN.

    Attributes:
        start_position:
            Source position of the ``STOP`` keyword.
        end_position:
            Source position of the terminating period.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=20, column=4, offset=400, filename="x.cbl")
        >>> node = StopRunStatementNode(start_position=pos, end_position=pos)
    """

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_stop_run_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_stop_run_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class GobackStatementNode(StatementNode):
    """
    Immutable AST node for the COBOL ``GOBACK`` statement.

    ``GOBACK`` transfers control back to the caller of the current
    program or sub-program.

    COBOL syntax example::

        GOBACK.

    Attributes:
        start_position:
            Source position of the ``GOBACK`` keyword or identifier.
        end_position:
            Source position of the terminating period.

    Examples:
        >>> from app.parser.lexer.position import Position
        >>> pos = Position(line=25, column=4, offset=500, filename="x.cbl")
        >>> node = GobackStatementNode(start_position=pos, end_position=pos)
    """

    def accept(self, visitor: object) -> object:
        """
        Dispatch to ``visitor.visit_goback_statement(self)`` if available.

        Args:
            visitor: Any visitor object.

        Returns:
            The return value of the visitor method, or ``None``.
        """
        visit = getattr(visitor, "visit_goback_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class ConditionTerm:
    """
    One ``<connector> <left> <operator> <right>`` term of a compound
    ``IF`` condition, beyond the first (which stays in
    :class:`IfStatementNode`'s own ``condition_left``/``condition_operator``/
    ``condition_right`` for backward compatibility with every existing
    consumer of that triple).

    ``connector`` is always ``"AND"`` or ``"OR"`` — the keyword that joined
    this term to the one before it, in source order.

    Precedence convention: ``AND`` binds tighter than ``OR`` (COBOL's own
    rule, and the one this parser now follows) — ``A AND B OR C`` parses
    as ``(A AND B) OR C``, never ``A AND (B OR C)``. ``extra_conditions``
    stores the flat left-to-right sequence of terms exactly as written;
    a consumer that needs to *evaluate* a compound condition must group
    consecutive ``AND``-connected terms before splitting on ``OR``, per
    that convention — nothing currently does, so no evaluator is invented
    here (see docs/MMIM_PARSER_VALIDATION_FIX.md).

    Parenthesised sub-conditions (e.g. ``A AND (B OR C)``) are not
    represented by this node — they remain unsupported and are reported
    as a parse error, not silently misparsed as a flat term sequence.

    ``left_subscript``/``right_subscript`` (task #stage32) carry a
    structured subscript for ``left``/``right`` when either operand is a
    single-dimension, literal- or identifier-subscripted table reference
    (``WS-ITEM(2)``/``WS-ITEM(WS-I)``); empty for a plain operand, which
    is every term before this stage and remains so for anything this
    stage does not model (multi-dimensional/arithmetic subscripts).
    """

    connector: str
    left: str
    operator: str
    right: str
    left_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    left_expression: "ArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )
    right_expression: "ArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )


@dataclass(frozen=True)
class IfStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``IF`` statement.

    ``condition_left``/``condition_operator``/``condition_right`` are the
    *first* simple condition — unchanged in meaning and populated exactly
    as before for a plain (non-compound) ``IF``. ``extra_conditions``
    holds any further ``AND``/``OR``-joined comparisons, empty for a plain
    ``IF``. See :class:`ConditionTerm` for the precedence convention.

    ``condition_left_subscript``/``condition_right_subscript`` (task
    #stage32) mirror :class:`ConditionTerm`'s own subscript fields for
    this statement's first condition term — see there for what they
    carry and when they are empty. A subscripted condition
    (``IF WS-ITEM(WS-I) > 100``) used to make the parser drop this
    entire ``IfStatementNode`` (a ``(`` where a comparison operator was
    expected raised ``SYN005``); it is now recognised as a structured
    reference instead.

    ``condition_left_expression``/``condition_right_expression`` (task
    #stage38) carry a structured :data:`ArithmeticExpression` tree —
    reusing Stage 35's ``COMPUTE`` expression representation unchanged —
    when that operand is a parenthesized arithmetic expression (e.g.
    ``IF (CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY) > WAREHOUSE-CAPACITY``).
    When either is populated, the corresponding
    ``condition_left``/``condition_right`` string is ``""`` — the two are
    mutually exclusive representations of the same operand position, not
    a redundant parallel one (mirroring how :class:`ComputeStatementNode`
    has no separate flattened-string field alongside its own
    ``expression``). Empty for every condition this stage does not
    change. Before this stage, this exact operand shape made
    :meth:`~app.parser.syntax.procedure_parser.ProcedureDivisionParser
    ._parse_simple_condition` raise ``SYN005`` ("expected operand for IF
    condition"), and panic-mode recovery discarded the entire enclosing
    paragraph.
    """

    condition_left: str
    condition_operator: str
    condition_right: str
    then_statements: tuple[StatementNode, ...]
    else_statements: tuple[StatementNode, ...] = ()
    extra_conditions: tuple[ConditionTerm, ...] = ()
    condition_left_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    condition_right_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    condition_left_expression: "ArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )
    condition_right_expression: "ArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_if_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class PerformStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``PERFORM`` statement.

    Attributes:
        target:
            The paragraph (or section) name performed. For ``PERFORM A
            THRU C``, this is the range's first name, ``A``.
        thru_target:
            The range's last name (``C`` in ``PERFORM A THRU C``), or
            ``""`` for an ordinary ``PERFORM A`` with no ``THRU``/
            ``THROUGH`` clause (task #stage16). Omitted from the
            serialized AST while empty, so an ordinary PERFORM
            serializes exactly as it always did.
    """

    target: str
    thru_target: str = field(default="", metadata={"omit_if_empty": True})

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_perform_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class PerformTargetUntilStatementNode(StatementNode):
    """
    Immutable AST node for an out-of-line ``PERFORM paragraph-name UNTIL
    condition`` statement (task #stage37).

    Unlike :class:`PerformUntilStatementNode` (the *inline* ``PERFORM
    UNTIL ... END-PERFORM`` form, whose loop body is written directly
    inside the statement), this form has no body in the source at all
    and no ``END-PERFORM``: COBOL repeatedly transfers control to the
    named paragraph and re-tests the condition after each execution.
    The "body" is therefore represented purely as :attr:`target` — a
    reference to an existing paragraph, lowered into an ``IRCall``
    exactly like a plain :class:`PerformStatementNode` already is
    (:meth:`~app.ir.builder.IRBuilder.build_perform_target_until_statement`)
    — never duplicated into a second, inline copy of that paragraph's
    own statements. Stage 36's paragraph outlining resolves this call
    identically whether it appears at the top level or, as here, as the
    single statement inside a loop.

    Attributes:
        target:
            The paragraph performed repeatedly, exactly as written. A
            ``THRU``/``THROUGH`` range is not represented here — no real
            corpus occurrence combines ``THRU`` with this form, so a
            ``PERFORM A THRU C UNTIL ...`` is left to the ordinary
            :class:`PerformStatementNode` (``THRU``) parsing path, whose
            existing "dangling UNTIL" ``SYN001`` behaviour is unchanged.
        condition_left:
            Left-hand operand of the ``UNTIL`` exit condition.
        condition_operator:
            The ``UNTIL`` condition's comparison operator.
        condition_right:
            Right-hand operand of the ``UNTIL`` exit condition.

    The condition is parsed via the same
    :meth:`~app.parser.syntax.procedure_parser.ProcedureDivisionParser
    ._parse_condition_term` machinery :class:`IfStatementNode` and
    :class:`PerformVaryingStatementNode` already use — no second
    condition parser. A subscripted condition operand is deliberately not
    represented here (mirroring :class:`PerformUntilStatementNode`'s own
    identical simple-condition-only shape): no real corpus occurrence
    subscripts this condition, and this node's IR target,
    :class:`~app.ir.instructions.IRPerformUntil`, carries no subscript
    fields either.
    """

    target: str
    condition_left: str
    condition_operator: str
    condition_right: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_perform_target_until_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class PerformUntilStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``PERFORM UNTIL`` statement.
    """

    condition_left: str
    condition_operator: str
    condition_right: str
    statements: tuple[StatementNode, ...]

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_perform_until_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class PerformVaryingStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``PERFORM VARYING ... FROM ... BY ...
    UNTIL ...`` statement (task #stage34).

    Grammar covered::

        PERFORM VARYING identifier-1
            FROM {identifier-2 | literal-1}
            BY {identifier-3 | literal-2}
            UNTIL condition-1
            <body>
        END-PERFORM

    The source is represented faithfully — no COBOL-to-Java semantic
    translation happens here (no ``-1``/loop-continuation inversion; that
    is a Java-generation concern, applied by the backend, mirroring how
    :class:`Subscript` defers its own ``-1`` adjustment). This node
    otherwise follows :class:`PerformUntilStatementNode`'s exact shape
    (``condition_left``/``condition_operator``/``condition_right``/
    ``statements``), with the three fields ``PERFORM VARYING`` adds on
    top of a plain ``PERFORM UNTIL``.

    Attributes:
        varying_variable:
            The loop-control variable's COBOL name, exactly as written
            (e.g. ``"CURRENT-IDX"``).
        from_value:
            The ``FROM`` clause's operand text — a literal (``"1"``,
            possibly signed, e.g. ``"-1"``) or an identifier. A single
            token only; an arithmetic ``FROM`` expression is out of scope
            (not present anywhere in the real corpus) and is never
            represented by this node.
        by_value:
            The ``BY`` clause's operand text, same shape as
            :attr:`from_value`.
        condition_left:
            Left-hand operand of the ``UNTIL`` exit condition.
        condition_operator:
            The ``UNTIL`` condition's comparison operator.
        condition_right:
            Right-hand operand of the ``UNTIL`` exit condition.
        condition_left_subscript:
            A structured subscript (task #stage32) for
            :attr:`condition_left`, when it is a single-dimension,
            literal- or identifier-subscripted table reference; empty
            otherwise. Parsed the same way an ``IF`` condition's operand
            is (:meth:`~app.parser.syntax.procedure_parser
            .ProcedureDivisionParser._parse_condition_term`), so the
            ``UNTIL`` condition gets subscript support "for free" from
            the same machinery, even though no real corpus occurrence
            currently subscripts it.
        condition_right_subscript:
            The mirrored field for :attr:`condition_right`.
        statements:
            The loop body's statements, in source order — parsed with the
            exact same statement-list mechanism
            :class:`PerformUntilStatementNode` and :class:`IfStatementNode`
            already use, so nested ``IF``, ``EXIT``, ``COMPUTE``, and
            subscripted table references inside the body are handled
            exactly as they already are elsewhere (no parallel
            mini-language).
    """

    varying_variable: str
    from_value: str
    by_value: str
    condition_left: str
    condition_operator: str
    condition_right: str
    statements: tuple[StatementNode, ...]
    condition_left_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    condition_right_subscript: tuple[Subscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_perform_varying_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class ReadStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``READ file-name [INTO identifier]
    [AT END imperative-statement...] [NOT AT END imperative-statement...]
    [END-READ]`` statement (task #stage40).

    Grammar covered, matching every shape evidenced in the 45-source
    corpus plus the one additional legal form already pinned by
    ``tests/fixtures/phase5/file_processing.cbl``::

        READ file-name [INTO identifier]
            [AT END imperative-statement-1 imperative-statement-2 ...]
            [NOT AT END imperative-statement-1 imperative-statement-2 ...]
        [END-READ]

    Without ``END-READ``, COBOL closes the ``AT END``/``NOT AT END``
    clause at the sentence's own terminating period -- so at most one
    *sentence's worth* of statements is collected in that form (the
    parser detects this by noticing that a statement it just parsed
    already consumed the terminating period itself, via
    :meth:`~app.parser.syntax.procedure_parser.ProcedureDivisionParser
    ._parse_read_clause_body`, exactly the ambiguity real COBOL resolves
    the same way).

    There is no actual file-reading capability in this backend (task
    #stage40's own explicit scope decision, since nothing in the corpus
    demands one -- see the Stage 40 discovery report): this node
    therefore does not model ``READ`` as ever successfully fetching a
    record. Only ``at_end_statements`` is ever lowered to IR
    (:meth:`~app.ir.builder.IRBuilder.build_read_statement`) -- a program
    that cannot truthfully read a record honestly reaches end-of-file
    immediately every time. ``not_at_end_statements`` is still captured
    here in full, for AST fidelity and any future stage that adds a real
    file runtime, but is deliberately never lowered.

    Attributes:
        target:
            The file name being read, exactly as written (not resolved
            against any ``SELECT``/``FD`` declaration -- neither is
            represented by this parser yet).
        into_target:
            The ``INTO`` clause's identifier, or ``""`` when absent (not
            evidenced as ever absent in the real corpus, but legal COBOL
            and present in the ``file_processing.cbl`` fixture).
        at_end_statements:
            The ``AT END`` clause's statement list, in source order,
            empty when the clause is absent.
        not_at_end_statements:
            The ``NOT AT END`` clause's statement list, in source order,
            empty when the clause is absent. Never lowered to IR -- see
            above.
    """

    target: str
    into_target: str = field(default="", metadata={"omit_if_empty": True})
    at_end_statements: tuple[StatementNode, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    not_at_end_statements: tuple[StatementNode, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_read_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class GoToStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``GO TO`` statement.
    """

    target: str

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_go_to_statement", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class CallStatementNode(StatementNode):
    """
    Immutable AST node for a COBOL ``CALL`` statement.
    """

    target: str
    arguments: tuple[str, ...] = ()

    def accept(self, visitor: object) -> object:
        visit = getattr(visitor, "visit_call_statement", None)
        if callable(visit):
            return visit(self)
        return None
