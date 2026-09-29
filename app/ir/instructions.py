"""
IR Instruction Hierarchy.

Purpose:
    Define the immutable instruction types that populate
    :class:`~app.ir.blocks.IRBasicBlock` instances.  Instructions represent
    the atomic executable operations of the IR — data movement, function
    calls, control flow, and return from a function.

    The instruction hierarchy is designed as a set of frozen dataclasses so
    that instructions can be compared, hashed, and safely shared across
    analyses.

Responsibilities:
    - :class:`IRInstruction` — abstract base for all instructions; carries a
      ``result`` operand name (empty string if the instruction produces no value)
      and an optional human-readable ``comment``.
    - :class:`IRAssignment` — assigns a constant or computed value to a name.
    - :class:`IRMove`       — copies the value of one named operand to another.
    - :class:`IRDisplay`    — writes one operand value to the console (DISPLAY).
    - :class:`IRAccept`     — reads one value from the console into a variable
      (ACCEPT).
    - :class:`IRCall`       — represents a (potentially impure) function call
      with zero or more arguments; result may be discarded.
    - :class:`IRReturn`     — terminates the enclosing function; carries an
      optional return operand name.
    - :class:`IRBranch`     — unconditional or conditional transfer of control
      to a target label.

Non-responsibilities:
    - Instruction scheduling or register allocation.
    - COBOL-specific semantics.
    - Java code generation.
    - Optimisation passes.

Dependencies:
    - :mod:`app.ir.nodes` — ``IRNode``, ``IRNodeKind``.
    - Python standard library only (``abc``, ``dataclasses``).

Examples:
    Constructing a MOVE instruction::

        from app.ir.instructions import IRMove
        mv = IRMove(result="WS-TARGET", source="WS-SOURCE")
        mv.kind.value  # 'instruction'
        mv.result      # 'WS-TARGET'
        mv.source      # 'WS-SOURCE'

    Constructing a CALL instruction::

        from app.ir.instructions import IRCall
        call = IRCall(result="RETVAL", target="PROCESS-RECORD", args=("ARG1",))

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.ir.nodes import IRNode, IRNodeKind
from app.parser.lexer.position import Position

__all__ = [
    "IRAccept",
    "IRAdd",
    "IRArithmeticExpression",
    "IRAssignment",
    "IRBinaryExpression",
    "IRCall",
    "IRCompute",
    "IRConditionTerm",
    "IRConditionalBranch",
    "IRDisplay",
    "IRDivide",
    "IRElse",
    "IREndIf",
    "IREndPerform",
    "IRIf",
    "IRInstruction",
    "IRJump",
    "IRMove",
    "IRMultiply",
    "IROperandExpression",
    "IRPerformUntil",
    "IRPerformVarying",
    "IRReturn",
    "IRSubscript",
    "IRSubtract",
]


@dataclass(frozen=True)
class IRSubscript:
    """
    IR image of :class:`app.parser.ast.statements.Subscript` (task
    #stage32) — a single-dimension COBOL table subscript, carried through
    unchanged from the AST.

    COBOL's own 1-based subscript meaning is preserved exactly as the
    parser captured it: ``value`` is never adjusted to a 0-based Java
    array index here. That translation is a Java-generation concern
    (Stage 33), applied exactly once, at the single point the Java
    backend renders an indexed reference — never in the IR, and never
    duplicated across more than one backend emitter.

    Attributes:
        kind:
            ``"literal"`` for a bare integer subscript or
            ``"identifier"`` for a data-name subscript — mirrors
            :attr:`app.parser.ast.statements.Subscript.kind` exactly.
        value:
            The subscript's own operand text, already lowered by
            :meth:`~app.ir.builder.IRBuilder.build_subscripts` the same
            way any other operand is (symbol-table canonicalisation for
            an identifier, unchanged text for a literal).

    Examples:
        >>> from app.ir.instructions import IRSubscript
        >>> IRSubscript(kind="literal", value="2")
        IRSubscript(kind='literal', value='2')
    """

    kind: str = field(default="")
    value: str = field(default="")


def _render_operand(name: str, subscripts: tuple[IRSubscript, ...]) -> str:
    """Render *name* with its subscript (task #stage32), e.g.
    ``WS-ITEM(WS-I)``, or just *name* unchanged when *subscripts* is
    empty — used only for human-readable text
    (:meth:`IRIf.condition_text`), never for Java generation (Stage 33)."""
    if not subscripts:
        return name
    return f"{name}({','.join(s.value for s in subscripts)})"


@dataclass(frozen=True)
class IROperandExpression:
    """
    IR image of :class:`app.parser.ast.statements.OperandExpression`
    (task #stage35) — one leaf of a ``COMPUTE`` expression tree.

    ``value`` is already lowered by :meth:`~app.ir.builder.IRBuilder.build_operand`
    (canonical variable reference or literal text), the same as every
    other arithmetic instruction's operand.

    Attributes:
        value:
            The operand's lowered text.
        subscript:
            A single-dimension subscript (task #stage32) when ``value``
            names a table element, empty otherwise.

    Examples:
        >>> IROperandExpression(value="WS-PRICE")
        IROperandExpression(value='WS-PRICE', subscript=())
    """

    value: str = field(default="")
    subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )


@dataclass(frozen=True)
class IRBinaryExpression:
    """
    IR image of :class:`app.parser.ast.statements.BinaryExpression`
    (task #stage35) — one ``left operator right`` node of a ``COMPUTE``
    expression tree.

    Attributes:
        operator:
            One of ``"+"``, ``"-"``, ``"*"``, ``"/"``.
        left:
            The left operand: an :class:`IROperandExpression` or a
            nested :class:`IRBinaryExpression`.
        right:
            The right operand: an :class:`IROperandExpression` or a
            nested :class:`IRBinaryExpression`.

    Examples:
        >>> expr = IRBinaryExpression(
        ...     operator="+",
        ...     left=IROperandExpression(value="WS-A"),
        ...     right=IROperandExpression(value="WS-B"),
        ... )
        >>> expr.operator
        '+'
    """

    operator: str
    left: "IRArithmeticExpression"
    right: "IRArithmeticExpression"


#: A COMPUTE expression node in the IR: either a leaf operand or a binary
#: operation on two further expression nodes (task #stage35).
IRArithmeticExpression = IROperandExpression | IRBinaryExpression

#: Arithmetic operator precedence: ``*``/``/`` bind tighter than ``+``/``-``,
#: matching both COBOL's and Java's standard precedence — no translation
#: between the two languages is ever needed (task #stage35).
_ARITHMETIC_PRECEDENCE: dict[str, int] = {"+": 1, "-": 1, "*": 2, "/": 2}


def render_arithmetic_expression(
    expression: IRArithmeticExpression, parent_precedence: int = 0
) -> str:
    """
    Render an :data:`IRArithmeticExpression` tree back to text, inserting
    parentheses only where evaluation order would otherwise change
    (task #stage35).

    This is a standard precedence-climbing printer: a node is wrapped in
    parentheses exactly when its own operator binds *less* tightly than
    the context it is printed in requires — never more, never less — so
    the output is always semantically equivalent to the tree, whether or
    not the original source used the same parentheses. This is used both
    for human-readable IR text (:meth:`IRCompute.expression_text`) and,
    with the same tree walked a second time for 0-based subscript
    translation, for Java generation
    (:func:`app.backend.java.statement_emitter.emit_compute`) — COBOL's
    and Java's arithmetic-operator precedence are identical, so nothing
    about this printer's parenthesization logic is COBOL- or
    Java-specific.

    A left operand is printed against its own operator's precedence (an
    equal-precedence left child never needs parentheses, since ``+``/
    ``-``/``*``/``/`` are all left-associative and print left-to-right
    unambiguously); a right operand is printed against one more than its
    own operator's precedence, so ``A - (B - C)`` keeps its parentheses
    (dropping them would silently change the result to ``(A - B) - C``).

    Args:
        expression: The expression tree to render.
        parent_precedence: The precedence level of the context this
            expression is being printed into; ``0`` (the default) for a
            top-level expression, which is never parenthesized.

    Returns:
        The expression as text, e.g. ``"B * (C + D)"``.

    Examples:
        >>> render_arithmetic_expression(
        ...     IRBinaryExpression(
        ...         operator="*",
        ...         left=IROperandExpression(value="B"),
        ...         right=IRBinaryExpression(
        ...             operator="+",
        ...             left=IROperandExpression(value="C"),
        ...             right=IROperandExpression(value="D"),
        ...         ),
        ...     )
        ... )
        'B * (C + D)'
    """
    if isinstance(expression, IROperandExpression):
        return _render_operand(expression.value, expression.subscript)

    precedence = _ARITHMETIC_PRECEDENCE[expression.operator]
    left_text = render_arithmetic_expression(expression.left, precedence)
    right_text = render_arithmetic_expression(expression.right, precedence + 1)
    text = f"{left_text} {expression.operator} {right_text}"
    if precedence < parent_precedence:
        return f"({text})"
    return text


# ---------------------------------------------------------------------------
# Abstract instruction base
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRInstruction(IRNode):
    """
    Abstract base for all IR instructions.

    An instruction is an atomic executable operation that belongs to a
    :class:`~app.ir.blocks.IRBasicBlock`.  Every instruction has:

    * a ``kind`` fixed to :attr:`~app.ir.nodes.IRNodeKind.INSTRUCTION`.
    * an optional ``result`` — the name of the operand that receives the
      output (empty string if no value is produced).
    * an optional ``comment`` for debugging and documentation.

    Subclasses provide instruction-specific operand fields.

    Attributes:
        kind:
            Always :attr:`~app.ir.nodes.IRNodeKind.INSTRUCTION`.
        result:
            Name of the operand that receives the instruction's output.
            Empty string if the instruction produces no value (e.g.
            :class:`IRReturn`, void :class:`IRCall`).
        comment:
            Optional human-readable annotation for logging and dumps.
        source_position:
            The :class:`~app.parser.lexer.position.Position` of the AST
            statement this instruction was lowered from, or ``None`` if
            unavailable (task #109 source-mapping requirement).
            Excluded from equality comparison (``compare=False``) so
            existing tests asserting instruction equality by operand
            values are unaffected by this addition.
        paragraph:
            The uppercased name of the COBOL paragraph this instruction
            was lowered from, or ``""`` if it did not originate from a
            paragraph.  This is how paragraph identity survives AST -> IR
            lowering despite every paragraph's statements being
            flattened into a single :class:`~app.ir.blocks.IRBasicBlock`
            (task #109; the block structure itself is not split further
            because the Java backend and CFG-relevant tooling currently
            read only ``function.blocks[0]`` -- see
            :mod:`app.ir.builder`'s module docstring).  Also excluded
            from equality comparison.
        result_subscript:
            A structured subscript for ``result`` when the write-target
            it names is a single-dimension, literal- or identifier-
            subscripted table reference (task #stage32) — e.g. for
            :class:`IRMove`/:class:`IRAdd`/:class:`IRSubtract`/
            :class:`IRMultiply`/:class:`IRDivide`, whichever of them
            uses ``result`` as its own write-target. Empty for a plain
            (unsubscripted) result, which every instruction produced
            before this stage, and every instruction whose ``result``
            names something other than a table element.

    Examples:
        >>> from app.ir.instructions import IRMove
        >>> mv = IRMove(result="WS-OUT", source="WS-IN")
        >>> mv.kind.value
        'instruction'
        >>> mv.result
        'WS-OUT'
    """

    kind: IRNodeKind = field(default=IRNodeKind.INSTRUCTION, init=False)
    result: str = field(default="")
    comment: str = field(default="")
    source_position: Position | None = field(default=None, compare=False)
    paragraph: str = field(default="", compare=False)
    result_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    @abstractmethod
    def accept(self, visitor: Any) -> Any:
        """
        Dispatch to the visitor method appropriate for this instruction.

        Args:
            visitor: An :class:`~app.ir.visitors.IRVisitor` or compatible object.

        Returns:
            The visitor method's return value, or ``None``.
        """


# ---------------------------------------------------------------------------
# Concrete instructions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRAssignment(IRInstruction):
    """
    Assign a literal or constant value to a named result operand.

    Use :class:`IRAssignment` when the value being stored is a literal
    constant (an integer, string literal, or COBOL figurative constant)
    rather than the content of another operand.

    Attributes:
        result:
            Name of the target operand (e.g. ``"WS-COUNT"``).
        value:
            The literal value as a string (e.g. ``"0"``, ``'"HELLO"'``,
            ``"SPACES"``).
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRAssignment
        >>> a = IRAssignment(result="WS-COUNT", value="0")
        >>> a.value
        '0'
        >>> a.result
        'WS-COUNT'
    """

    value: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_assignment(self)``."""
        visit = getattr(visitor, "visit_assignment", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRAdd(IRInstruction):
    """
    Compute the sum of two operands.
    """

    left: str = field(default="")
    right: str = field(default="")
    left_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_add", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRSubtract(IRInstruction):
    """
    Compute the difference between two operands.
    """

    left: str = field(default="")
    right: str = field(default="")
    left_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_subtract", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRMultiply(IRInstruction):
    """
    Compute the product of two operands.
    """

    left: str = field(default="")
    right: str = field(default="")
    left_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_multiply", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRDivide(IRInstruction):
    """
    Compute the quotient of two operands.
    """

    left: str = field(default="")
    right: str = field(default="")
    left_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_divide", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRCompute(IRInstruction):
    """
    Assign an arbitrary arithmetic expression to a target (COBOL
    ``COMPUTE target = expression``, task #stage35).

    Unlike :class:`IRAdd`/:class:`IRSubtract`/:class:`IRMultiply`/
    :class:`IRDivide` — each a fixed two-operand compound-assignment
    effect (``result op= left``), because that is COMPUTE's siblings'
    entire COBOL grammar — ``COMPUTE`` assigns a freshly evaluated
    expression tree to ``result``, so it carries a structured
    :data:`IRArithmeticExpression` rather than a second flat operand.

    ``result``/``result_subscript`` (inherited from :class:`IRInstruction`)
    are the target and its subscript, e.g. for
    ``COMPUTE EXTENDED-LINE-VAL(1) = ...`` (task #stage32/33's structured
    subscript, unchanged).

    Attributes:
        expression:
            The right-hand-side expression tree, or ``None`` only as the
            dataclass default (never left unset by
            :meth:`~app.ir.builder.IRBuilder.build_compute_instruction`).

    Examples:
        >>> from app.ir.instructions import IRCompute, IRBinaryExpression, IROperandExpression
        >>> instr = IRCompute(
        ...     result="WS-TOTAL",
        ...     expression=IRBinaryExpression(
        ...         operator="+",
        ...         left=IROperandExpression(value="WS-A"),
        ...         right=IROperandExpression(value="WS-B"),
        ...     ),
        ... )
        >>> instr.expression_text()
        'WS-A + WS-B'
    """

    expression: IRArithmeticExpression | None = field(
        default=None, metadata={"omit_if_empty": True}
    )

    def expression_text(self) -> str:
        """The right-hand-side expression as text, e.g. ``"B * (C + D)"``."""
        if self.expression is None:
            return ""
        return render_arithmetic_expression(self.expression)

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_compute(self)``."""
        visit = getattr(visitor, "visit_compute", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRConditionTerm:
    """
    One ``<connector> <left> <operator> <right>`` term of a compound
    ``IF`` condition beyond the first -- the IR image of
    :class:`~app.parser.ast.statements.ConditionTerm`.

    ``connector`` is ``"AND"`` or ``"OR"`` and is the keyword that joined
    this term to the one before it, in source order. Precedence is the
    parser's (and COBOL's): ``AND`` binds tighter than ``OR``. The operands
    are already lowered by ``IRBuilder.build_operand``.

    ``left_subscript``/``right_subscript`` (task #stage32) mirror
    :class:`app.parser.ast.statements.ConditionTerm`'s own subscript
    fields — a structured subscript when ``left``/``right`` names a
    single-dimension, literal- or identifier-subscripted table element;
    empty otherwise.

    Examples:
        >>> from app.ir.instructions import IRConditionTerm
        >>> IRConditionTerm(connector="OR", left="WS-B", operator="=", right="2")
        IRConditionTerm(connector='OR', left='WS-B', operator='=', right='2')
    """

    connector: str = field(default="")
    left: str = field(default="")
    operator: str = field(default="")
    right: str = field(default="")
    left_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    left_expression: "IRArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )
    right_expression: "IRArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )


@dataclass(frozen=True)
class IRIf(IRInstruction):
    """
    Open a structured conditional block (COBOL IF statement).

    Carries the first condition as three fields so the backend can
    translate each operand independently via its operand-translation
    helpers, plus ``extra_terms`` for any further ``AND``/``OR``-joined
    comparisons of a compound ``IF``.

    Attributes:
        result:
            Always ``""``; inherited from :class:`IRInstruction`.
        left:
            Left-hand operand of the comparison (variable name or literal).
        operator:
            Comparison operator string: one of ``"=="``, ``"!="``, ``">"``,
            ``">="``, ``"<"``, ``"<="``.
        right:
            Right-hand operand of the comparison.
        extra_terms:
            Further ``AND``/``OR``-joined terms, in source order, empty for
            a plain ``IF``. Omitted from the serialized IR when empty, so a
            plain ``IF`` serializes exactly as it always did.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRIf
        >>> instr = IRIf(left="WS-COUNT", operator=">", right="0")
        >>> instr.left
        'WS-COUNT'
        >>> instr.operator
        '>'
        >>> instr.right
        '0'
        >>> instr.condition_text()
        'WS-COUNT > 0'
    """

    left: str = field(default="")
    operator: str = field(default="")
    right: str = field(default="")
    extra_terms: tuple[IRConditionTerm, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    left_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    left_expression: "IRArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )
    right_expression: "IRArithmeticExpression | None" = field(
        default=None, metadata={"omit_if_empty": True}
    )

    def condition_text(self) -> str:
        """The whole condition as source-ordered text, e.g.
        ``"WS-A > 5 OR WS-B = 2"`` (a plain IF gives ``"WS-A > 5"``).

        An operand with a structured subscript (task #stage32) renders
        with it, e.g. ``"WS-ITEM(WS-I) > 100"`` — this was never
        possible before this stage (a subscripted condition operand
        dropped the whole ``IRIf`` rather than reaching this method at
        all), so there is no pre-existing rendering to stay compatible
        with; every previously-representable (unsubscripted) condition
        renders exactly as before.

        An operand that is a parenthesized arithmetic expression (task
        #stage38) renders via :func:`render_arithmetic_expression` —
        the same precedence-aware printer :meth:`IRCompute.expression_text`
        uses — wrapped in one outer pair of parentheses to mirror the
        source shape, e.g. ``"(CURRENT-STOCK-QTY + SUGGESTED-ORDER-QTY)
        > WAREHOUSE-CAPACITY"``.
        """

        def _render_side(
            text: str,
            subscript: tuple[IRSubscript, ...],
            expression: "IRArithmeticExpression | None",
        ) -> str:
            if expression is not None:
                return f"({render_arithmetic_expression(expression)})"
            return _render_operand(text, subscript)

        left = _render_side(self.left, self.left_subscript, self.left_expression)
        right = _render_side(self.right, self.right_subscript, self.right_expression)
        parts = [f"{left} {self.operator} {right}"]
        parts.extend(
            f"{t.connector} "
            f"{_render_side(t.left, t.left_subscript, t.left_expression)} "
            f"{t.operator} "
            f"{_render_side(t.right, t.right_subscript, t.right_expression)}"
            for t in self.extra_terms
        )
        return " ".join(parts)

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_if(self)``."""
        visit = getattr(visitor, "visit_if", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRElse(IRInstruction):
    """
    Switch to the ``else`` branch of the current conditional block.

    :class:`IRElse` is a marker instruction that carries no operands.
    It must appear after one or more body instructions of an :class:`IRIf`
    and before the closing :class:`IREndIf`.

    Attributes:
        result:
            Always ``""``; inherited from :class:`IRInstruction`.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRElse
        >>> IRElse().result
        ''
    """

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_else(self)``."""
        visit = getattr(visitor, "visit_else", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IREndIf(IRInstruction):
    """
    Close the current structured conditional block.

    :class:`IREndIf` is a marker instruction that carries no operands.
    It must appear once for every :class:`IRIf` in the same scope.

    Attributes:
        result:
            Always ``""``; inherited from :class:`IRInstruction`.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IREndIf
        >>> IREndIf().result
        ''
    """

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_end_if(self)``."""
        visit = getattr(visitor, "visit_end_if", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRMove(IRInstruction):
    """
    Copy the value of one named operand to another.

    :class:`IRMove` corresponds to a COBOL ``MOVE source TO target`` statement
    where both operands are data-name references (after type checking has
    verified compatibility).

    Attributes:
        result:
            Name of the destination operand (``target`` in COBOL terms).
        source:
            Name of the source operand.
        source_subscript:
            A structured subscript for ``source`` (task #stage32) when it
            is a single-dimension, literal- or identifier-subscripted
            table reference; empty otherwise. See
            :attr:`IRInstruction.result_subscript` for the mirrored
            field covering ``result`` (the MOVE target).
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRMove
        >>> mv = IRMove(result="WS-TARGET", source="WS-SOURCE")
        >>> mv.source
        'WS-SOURCE'
        >>> mv.result
        'WS-TARGET'
    """

    source: str = field(default="")
    source_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_move(self)``."""
        visit = getattr(visitor, "visit_move", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRCall(IRInstruction):
    """
    Invoke a named function or paragraph with zero or more arguments.

    :class:`IRCall` captures a call to a named target (a COBOL paragraph,
    sub-program, or a generated Java method).  The call may produce a result
    value (stored in ``result``) or may be void (``result = ""``).

    Attributes:
        result:
            Name of the operand that receives the return value.  Set to
            ``""`` for void calls.
        target:
            Name of the function or paragraph to invoke. For ``PERFORM A
            THRU C``, this is the range's first paragraph, ``A``.
        args:
            Positional argument names, in order.  Default: empty tuple.
        thru_target:
            The range's last paragraph name (``C`` in ``PERFORM A THRU
            C``), or ``""`` for an ordinary ``PERFORM``/``CALL`` with no
            ``THRU``/``THROUGH`` clause (task #stage16). Omitted from the
            serialized IR while empty, so a non-THRU call/PERFORM
            serializes exactly as it always did.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRCall
        >>> call = IRCall(target="PROCESS-RECORD", args=("EMP-ID", "EMP-NAME"))
        >>> call.target
        'PROCESS-RECORD'
        >>> call.args
        ('EMP-ID', 'EMP-NAME')
    """

    target: str = field(default="")
    args: tuple[str, ...] = field(default_factory=tuple)
    thru_target: str = field(default="", metadata={"omit_if_empty": True})

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_call(self)``."""
        visit = getattr(visitor, "visit_call", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRReturn(IRInstruction):
    """
    Terminate the enclosing function and optionally return a value.

    :class:`IRReturn` corresponds to a COBOL ``STOP RUN`` or ``GOBACK``
    statement.  The optional ``operand`` names the value to return; for
    void functions it is left empty.

    Attributes:
        result:
            Unused (always ``""``); inherited from :class:`IRInstruction`.
        operand:
            Name of the operand whose value is returned, or ``""`` for
            void returns.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRReturn
        >>> ret = IRReturn(operand="WS-RESULT")
        >>> ret.operand
        'WS-RESULT'
        >>> IRReturn().operand
        ''
    """

    operand: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_return(self)``."""
        visit = getattr(visitor, "visit_return", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRConditionalBranch(IRInstruction):
    """
    Conditionally transfer control to one of two target blocks.

    Attributes:
        result:
            Unused (always ``""``); inherited from :class:`IRInstruction`.
        condition:
            Name of the operand that controls the branch.
        then_target:
            Name of the basic block to jump to if condition is true.
        else_target:
            Name of the basic block to jump to if condition is false.
        comment:
            Optional annotation.
    """

    condition: str = field(default="")
    then_target: str = field(default="")
    else_target: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_conditional_branch", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRJump(IRInstruction):
    """
    Unconditionally transfer control to a target block.

    Attributes:
        result:
            Unused (always ``""``); inherited from :class:`IRInstruction`.
        target:
            Name of the basic block to jump to.
        comment:
            Optional annotation.
    """

    target: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_jump", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRDisplay(IRInstruction):
    """
    Write one operand value to the standard output console.

    :class:`IRDisplay` corresponds to a COBOL ``DISPLAY operand`` statement.
    The operand may be a string literal, a numeric literal, or a variable
    reference.  The instruction produces no result value (``result = ""``).

    Attributes:
        result:
            Always ``""``; inherited from :class:`IRInstruction`.
        operand:
            The IR operand to display (a variable name or literal text).
        operand_subscript:
            A structured subscript for ``operand`` (task #stage32) when
            it is a single-dimension, literal- or identifier-subscripted
            table reference; empty otherwise.
        operands:
            Each operand separately when the ``DISPLAY`` has two or more
            (``DISPLAY 'TOTAL: ' WS-TOTAL``); empty otherwise. ``operand``
            still holds the space-joined text.
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRDisplay
        >>> d = IRDisplay(operand='"HELLO WORLD"')
        >>> d.operand
        '"HELLO WORLD"'
        >>> d.result
        ''
        >>> d2 = IRDisplay(operand="WS-NAME")
        >>> d2.operand
        'WS-NAME'
    """

    operand: str = field(default="")
    operand_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    operands: tuple[str, ...] = field(default=(), metadata={"omit_if_empty": True})

    @property
    def display_operands(self) -> tuple[str, ...]:
        """Every operand written, in order: ``operands`` when there are
        two or more, otherwise the single ``operand``."""
        return self.operands or (self.operand,)

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_display(self)``."""
        visit = getattr(visitor, "visit_display", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRAccept(IRInstruction):
    """
    Read one value from the standard input console into a variable.

    :class:`IRAccept` corresponds to a COBOL ``ACCEPT identifier`` statement.
    The instruction reads a value into the named ``result`` operand; there is
    no source operand (the source is always the console / system environment).

    Attributes:
        result:
            Name of the variable that receives the input (e.g. ``"WS-NAME"``).
        comment:
            Optional annotation.

    Examples:
        >>> from app.ir.instructions import IRAccept
        >>> a = IRAccept(result="WS-NAME")
        >>> a.result
        'WS-NAME'
        >>> IRAccept().result
        ''
    """

    def accept(self, visitor: Any) -> Any:
        """Dispatch to ``visitor.visit_accept(self)``."""
        visit = getattr(visitor, "visit_accept", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRPerformUntil(IRInstruction):
    """
    Open a structured PERFORM UNTIL block.

    Attributes:
        left:
            The left operand of the exit condition.
        operator:
            The comparison operator (e.g. ``"=="``, ``">="``).
        right:
            The right operand of the exit condition.
        comment:
            Optional annotation.
    """

    left: str = field(default="")
    operator: str = field(default="")
    right: str = field(default="")

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_perform_until", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IRPerformVarying(IRInstruction):
    """
    Open a structured ``PERFORM VARYING ... FROM ... BY ... UNTIL ...``
    loop block (task #stage34).

    Closed by the same :class:`IREndPerform` a :class:`IRPerformUntil`
    is -- COBOL's own ``END-PERFORM`` closes either form identically, and
    the Java backend's depth-tracking/nesting machinery
    (:func:`~app.backend.java.generator._collect_statements`) already
    treats any structured-loop opener uniformly, so no second closer type
    is introduced.

    Attributes:
        varying_variable:
            The loop-control variable's canonicalised name (looked up in
            the symbol table like any other identifier operand).
        from_value:
            The ``FROM`` operand, lowered like any other operand (an
            identifier is canonicalised; a literal, e.g. a signed ``"-1"``,
            is carried unchanged).
        by_value:
            The ``BY`` operand, lowered the same way.
        left:
            Left-hand operand of the ``UNTIL`` exit condition -- same
            role as :attr:`IRPerformUntil.left`.
        operator:
            The ``UNTIL`` condition's comparison operator.
        right:
            Right-hand operand of the ``UNTIL`` exit condition.
        left_subscript:
            A structured subscript (task #stage32/#stage33) for
            :attr:`left`, when it is a single-dimension, literal- or
            identifier-subscripted table reference; empty otherwise.
        right_subscript:
            The mirrored field for :attr:`right`.
        comment:
            Optional annotation.
    """

    varying_variable: str = field(default="")
    from_value: str = field(default="")
    by_value: str = field(default="")
    left: str = field(default="")
    operator: str = field(default="")
    right: str = field(default="")
    left_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )
    right_subscript: tuple[IRSubscript, ...] = field(
        default=(), metadata={"omit_if_empty": True}
    )

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_perform_varying", None)
        if callable(visit):
            return visit(self)
        return None


@dataclass(frozen=True)
class IREndPerform(IRInstruction):
    """
    Close a structured PERFORM block.

    It must appear once for every :class:`IRPerformUntil` in the same scope.

    Attributes:
        comment:
            Optional annotation.
    """

    def accept(self, visitor: Any) -> Any:
        visit = getattr(visitor, "visit_end_perform", None)
        if callable(visit):
            return visit(self)
        return None
