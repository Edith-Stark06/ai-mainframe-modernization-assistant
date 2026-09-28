"""
Dependency Analyzer.

Purpose:
    Extract COBOL dependencies from the AST as a structured list of
    :class:`~app.analysis.dependencies.models.Dependency` records:
    paragraph transitions (PERFORM), external program references
    (CALL), variable reads/writes, and condition dependencies (task
    #111). COPY statements are not currently represented in the parsed
    AST and thus cannot be extracted here.

Responsibilities:
    - Track which paragraph is currently being visited, so every
      dependency records where it came from
      (:attr:`~app.analysis.dependencies.models.Dependency.source`) --
      needed because two different paragraphs performing the same
      target, or reading/writing the same variable, are two distinct
      dependencies, not one.
    - Extract PERFORM/CALL dependencies (pre-existing behaviour,
      unchanged in shape; now source-attributed).
    - Extract VARIABLE_READ/VARIABLE_WRITE dependencies from MOVE and
      arithmetic (ADD/SUBTRACT/MULTIPLY/DIVIDE) statement operands.
    - Extract VARIABLE_WRITE (target) and VARIABLE_READ (every operand
      and subscript in the expression tree) dependencies from COMPUTE
      (task #stage35).
    - Extract CONDITION dependencies from IF and PERFORM UNTIL
      condition operands.
    - Classify each operand as a literal or a variable reference before
      emitting anything for it, so a quoted string or a numeric literal
      never becomes a fabricated "variable" dependency.
    - Provide :func:`compute_transitive_dependencies`, a read-only query
      over an already-extracted dependency list that discovers
      multi-hop PERFORM/CALL chains (``A -> B -> C`` implies ``A`` can
      reach ``C``) without mutating the direct list and without
      infinite traversal on cycles.

Non-responsibilities:
    - COPY statement extraction (no AST representation exists yet).
    - File dependencies (OPEN/CLOSE/READ/WRITE have no AST
      representation -- task #105/#108's parser audit; there is nothing
      here to extract them from, so none are fabricated).
    - Business-rule dependency extraction (task #112's concern; this
      module derives only dependencies that are directly and
      deterministically readable from AST structure).
    - Cross-program/workspace resolution
      (:mod:`app.analysis.dependencies.resolver`'s concern).

Dependencies:
    - app.analysis.dependencies.models -- Dependency, DependencyType.
    - app.parser.ast.* -- the AST node hierarchy and visitor protocol.
    - Python standard library only.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.analysis.dependencies.models import Dependency, DependencyType
from app.parser.ast.node import ASTNode
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.statements import (
    AddStatementNode,
    ArithmeticExpression,
    CallStatementNode,
    ComputeStatementNode,
    DivideStatementNode,
    IfStatementNode,
    MoveStatementNode,
    MultiplyStatementNode,
    OperandExpression,
    PerformStatementNode,
    PerformTargetUntilStatementNode,
    PerformUntilStatementNode,
    PerformVaryingStatementNode,
    ReadStatementNode,
    Subscript,
    SubtractStatementNode,
)
from app.parser.ast.visitor import ASTVisitor

__all__ = [
    "DependencyAnalyzer",
    "is_literal_operand",
    "compute_transitive_dependencies",
]


def is_literal_operand(text: str) -> bool:
    """
    Return ``True`` if *text* is a COBOL literal rather than a variable name.

    Mirrors the exact two rules
    :meth:`~app.ir.builder.IRBuilder.build_operand` already uses to make
    the same distinction for IR lowering (a quoted string, or a
    plain/signed/decimal number) -- kept as an independent, small
    predicate here rather than importing ``IRBuilder`` for it, since
    dependency analysis is a pure AST-level pass with no
    :class:`~app.parser.semantic.context.SemanticContext` of its own,
    and reaching into another class's underscore-prefixed static method
    would be a worse coupling than duplicating two well-defined,
    stable rules.

    This is the guard that keeps literal operands (``'00'``, ``42``,
    figurative constants written as bare words like ``SPACES``... note:
    a bare word like ``SPACES`` is NOT caught by either rule and is
    therefore treated as a variable reference here, exactly as
    :meth:`~app.ir.builder.IRBuilder.build_operand` also treats it --
    this is a known, shared limitation, not one this module invents) from
    ever being reported as a fabricated variable dependency.

    Args:
        text: The raw operand text from an AST statement field.

    Returns:
        ``True`` if *text* is a quoted string or numeric literal.
    """
    stripped = text.strip()
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
        return True
    if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        return True
    candidate = stripped.lstrip("+-")
    if not candidate:
        return False
    parts = candidate.split(".")
    if len(parts) > 2:
        return False
    return all(p.isdigit() for p in parts if p)


class DependencyAnalyzer(ASTVisitor):
    """
    Traverses the AST to extract dependencies.
    """

    def __init__(self) -> None:
        self._dependencies: list[Dependency] = []
        self._seen: set[tuple[str, DependencyType, str]] = set()
        self._current_paragraph: str = ""

    def analyze(self, node: ASTNode) -> list[Dependency]:
        """
        Analyze a node and its children, returning a list of extracted dependencies.
        """
        self._dependencies = []
        self._seen = set()
        self._current_paragraph = ""
        node.accept(self)
        return self._dependencies

    def _add_dependency(
        self,
        dep_type: DependencyType,
        target: str,
        position: Any,
    ) -> None:
        """
        Add a dependency if it hasn't been seen before (deduplication).

        Deduplication is keyed on ``(source, type, target)`` -- not
        ``(type, target)`` alone (task #111's confirmed fix) -- so that
        two different paragraphs performing/calling the same target, or
        reading/writing the same variable, are both retained as
        distinct dependencies rather than the second occurrence being
        silently dropped. The first occurrence's source location is
        preserved, matching the pre-#111 behaviour for CALL/PERFORM.
        """
        key = (self._current_paragraph, dep_type, target)
        if key in self._seen:
            return
        self._seen.add(key)
        self._dependencies.append(
            Dependency(
                type=dep_type,
                target=target,
                source_location=position,
                source=self._current_paragraph,
            )
        )

    def _maybe_add_operand_dependency(
        self, dep_type: DependencyType, operand: str, position: Any
    ) -> None:
        """Add *operand* as a dependency only if it is not a literal."""
        if is_literal_operand(operand):
            return
        self._add_dependency(dep_type, operand.upper(), position)

    def _maybe_add_subscript_dependency(
        self, subscripts: tuple[Subscript, ...], position: Any
    ) -> None:
        """
        Register a ``VARIABLE_READ`` dependency for each identifier
        subscript in *subscripts* (task #stage32).

        For ``WS-ITEM(WS-I)``, the index variable ``WS-I`` is read to
        determine which element of ``WS-ITEM`` is accessed -- a
        dependency distinct from, and in addition to, whatever
        read/write dependency the containing statement already registers
        for ``WS-ITEM`` itself (the base name, never a fabricated
        combined name like ``"WS-ITEM ( WS-I )"`` -- that corruption is
        fixed at the AST layer, by construction, not by anything in this
        module: ``node.source``/``node.target``/etc. are already the
        clean base name by the time they reach here).

        A literal subscript (``WS-ITEM(2)``) contributes no dependency --
        there is no variable to read, matching task #stage32's own
        explicit requirement.
        """
        for sub in subscripts:
            if sub.kind == "identifier":
                self._add_dependency(
                    DependencyType.VARIABLE_READ, sub.value.upper(), position
                )

    # ------------------------------------------------------------------
    # Structural traversal
    # ------------------------------------------------------------------

    def visit_program(self, node: ProgramNode) -> Any:
        if node.procedure_division:
            node.procedure_division.accept(self)
        # Note: COPY statements might appear in other divisions if supported in the future.
        return None

    def visit_procedure_division(self, node: ProcedureDivisionNode) -> Any:
        for paragraph in node.paragraphs:
            paragraph.accept(self)
        return None

    def visit_paragraph(self, node: ParagraphNode) -> Any:
        previous_paragraph = self._current_paragraph
        self._current_paragraph = node.name
        try:
            for statement in node.statements:
                statement.accept(self)
        finally:
            self._current_paragraph = previous_paragraph
        return None

    # ------------------------------------------------------------------
    # Paragraph / external-program dependencies (pre-existing, now
    # source-attributed)
    # ------------------------------------------------------------------

    def visit_call_statement(self, node: CallStatementNode) -> Any:
        self._add_dependency(DependencyType.CALL, node.target, node.start_position)
        return None

    def visit_perform_statement(self, node: PerformStatementNode) -> Any:
        self._add_dependency(DependencyType.PERFORM, node.target, node.start_position)
        return None

    def visit_read_statement(self, node: ReadStatementNode) -> Any:
        """
        ``READ file-name [INTO ...] AT END ... [NOT AT END ...]`` (task
        #stage40). Recurses into ``at_end_statements`` only, mirroring
        exactly what :meth:`~app.ir.builder.IRBuilder.build_read_statement`
        itself lowers -- this backend models every ``READ`` as always
        reaching end-of-file (no file-reading runtime exists), so
        ``not_at_end_statements`` is provably unreachable and contributes
        no dependency, matching the IR precisely rather than fabricating
        a read/write edge for code that can never run.

        Neither the file name nor the ``INTO`` target is registered as a
        dependency -- no file-content source exists to read into the
        latter, and the former is not resolved against any ``SELECT``/
        ``FD`` declaration by this parser (task #stage40's own scope).
        """
        for statement in node.at_end_statements:
            statement.accept(self)
        return None

    def visit_perform_target_until_statement(
        self, node: PerformTargetUntilStatementNode
    ) -> Any:
        """
        Out-of-line ``PERFORM paragraph-name UNTIL condition`` (task
        #stage37). Registers exactly the union of what
        :meth:`visit_perform_statement` and
        :meth:`visit_perform_until_statement` each register on their own
        -- a ``PERFORM`` dependency on the named target (the same
        paragraph transition a plain ``PERFORM`` records) plus a
        ``CONDITION`` dependency on each condition operand (the same
        read the inline form records for its own ``UNTIL``). There is no
        loop body to recurse into here (unlike the inline form) -- see
        :class:`PerformTargetUntilStatementNode`'s docstring for why.
        """
        self._add_dependency(DependencyType.PERFORM, node.target, node.start_position)
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_left, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_right, node.start_position
        )
        return None

    def visit_perform_until_statement(self, node: PerformUntilStatementNode) -> Any:
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_left, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_right, node.start_position
        )
        for statement in node.statements:
            statement.accept(self)
        return None

    def visit_perform_varying_statement(self, node: PerformVaryingStatementNode) -> Any:
        """
        ``PERFORM VARYING var FROM f BY b UNTIL cond ... END-PERFORM``
        (task #stage34).

        Dependencies registered, mirroring
        :meth:`visit_perform_until_statement` plus the three things
        ``PERFORM VARYING`` adds on top of a plain ``PERFORM UNTIL``:

        * ``varying_variable`` is written -- the loop's own initialisation
          (``FROM``) and every iteration's increment (``BY``) assign to
          it, exactly like a MOVE target.
        * ``from_value``/``by_value`` are read when they name a variable
          (a literal, the shape every real corpus occurrence actually
          uses, contributes no dependency -- same literal-filtering rule
          every other operand dependency already applies).
        * The ``UNTIL`` condition's operands (and any subscript index
          variable, task #stage32) are read, exactly like
          ``PERFORM UNTIL``/``IF``.
        * Every body statement is visited recursively, exactly like
          ``PERFORM UNTIL``.
        """
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_WRITE, node.varying_variable, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_READ, node.from_value, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_READ, node.by_value, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_left, node.start_position
        )
        self._maybe_add_subscript_dependency(
            node.condition_left_subscript, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_right, node.start_position
        )
        self._maybe_add_subscript_dependency(
            node.condition_right_subscript, node.start_position
        )
        for statement in node.statements:
            statement.accept(self)
        return None

    def _visit_condition_operand(
        self,
        text: str,
        subscript: tuple[Subscript, ...],
        expression: "ArithmeticExpression | None",
        position: Any,
    ) -> None:
        """
        Register the dependency/dependencies for one IF-condition operand
        (task #stage38): every identifier leaf of a parenthesized
        arithmetic expression as a ``VARIABLE_READ`` -- reusing
        :meth:`_visit_expression`, the exact walker
        :meth:`visit_compute_statement` already uses, unchanged -- or,
        for a plain operand exactly as before this stage, a
        ``CONDITION`` dependency (plus any subscript index variable).
        Mutually exclusive, mirroring the AST's own representation.
        """
        if expression is not None:
            self._visit_expression(expression, position)
            return
        self._maybe_add_operand_dependency(DependencyType.CONDITION, text, position)
        self._maybe_add_subscript_dependency(subscript, position)

    def visit_if_statement(self, node: IfStatementNode) -> Any:
        self._visit_condition_operand(
            node.condition_left,
            node.condition_left_subscript,
            node.condition_left_expression,
            node.start_position,
        )
        self._visit_condition_operand(
            node.condition_right,
            node.condition_right_subscript,
            node.condition_right_expression,
            node.start_position,
        )
        # Every operand of every AND/OR-joined term is read by the
        # condition too; literals are filtered exactly as for the first term.
        for term in node.extra_conditions:
            self._visit_condition_operand(
                term.left,
                term.left_subscript,
                term.left_expression,
                node.start_position,
            )
            self._visit_condition_operand(
                term.right,
                term.right_subscript,
                term.right_expression,
                node.start_position,
            )
        for statement in node.then_statements:
            statement.accept(self)
        for statement in node.else_statements:
            statement.accept(self)
        return None

    # ------------------------------------------------------------------
    # Variable read/write dependencies (task #111)
    # ------------------------------------------------------------------

    def visit_move_statement(self, node: MoveStatementNode) -> Any:
        # MOVE source TO target: target is fully overwritten (write
        # only, no read-before-write); source is read only. A
        # subscripted source/target (task #stage32) additionally reads
        # its own index variable, if any -- see
        # _maybe_add_subscript_dependency.
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_READ, node.source, node.start_position
        )
        self._maybe_add_subscript_dependency(node.source_subscript, node.start_position)
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_WRITE, node.target, node.start_position
        )
        self._maybe_add_subscript_dependency(node.target_subscript, node.start_position)
        return None

    def _visit_arithmetic(
        self,
        left: str,
        right: str,
        position: Any,
        left_subscript: tuple[Subscript, ...] = (),
        right_subscript: tuple[Subscript, ...] = (),
    ) -> None:
        """
        Shared handling for ADD/SUBTRACT/MULTIPLY/DIVIDE.

        In every one of these four statement shapes, ``left`` is the
        operand supplying a value (read only) and ``right`` is the
        accumulator the result is stored into -- which COBOL both reads
        (its prior value participates in the arithmetic) and writes
        (the result replaces it). Both effects on ``right`` are
        represented, per task #111's explicit example ("For `ADD A TO
        B` capture both the read of A and read/write effect on B where
        the model supports it"). ``left_subscript``/``right_subscript``
        (task #stage32) additionally read their own index variable, if
        any, exactly once each regardless of ``right`` being both read
        and written.
        """
        self._maybe_add_operand_dependency(DependencyType.VARIABLE_READ, left, position)
        self._maybe_add_subscript_dependency(left_subscript, position)
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_READ, right, position
        )
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_WRITE, right, position
        )
        self._maybe_add_subscript_dependency(right_subscript, position)

    def visit_add_statement(self, node: AddStatementNode) -> Any:
        self._visit_arithmetic(
            node.left,
            node.right,
            node.start_position,
            node.left_subscript,
            node.right_subscript,
        )
        return None

    def visit_subtract_statement(self, node: SubtractStatementNode) -> Any:
        self._visit_arithmetic(
            node.left,
            node.right,
            node.start_position,
            node.left_subscript,
            node.right_subscript,
        )
        return None

    def visit_multiply_statement(self, node: MultiplyStatementNode) -> Any:
        self._visit_arithmetic(
            node.left,
            node.right,
            node.start_position,
            node.left_subscript,
            node.right_subscript,
        )
        return None

    def visit_divide_statement(self, node: DivideStatementNode) -> Any:
        self._visit_arithmetic(
            node.left,
            node.right,
            node.start_position,
            node.left_subscript,
            node.right_subscript,
        )
        return None

    def _visit_expression(
        self, expression: ArithmeticExpression, position: Any
    ) -> None:
        """
        Register a ``VARIABLE_READ`` dependency for every operand leaf in
        a COMPUTE expression tree, and for each leaf's own subscript
        (task #stage35).

        A recursive generalization of the two-operand handling
        :meth:`_visit_arithmetic` already does for ADD/SUBTRACT/MULTIPLY/
        DIVIDE — COMPUTE's expression is an N-ary tree rather than a
        fixed pair, so every leaf (however deeply nested inside
        :class:`~app.parser.ast.statements.BinaryExpression` nodes) is
        walked and registered the same way a single flat operand already
        is, never a flattened combined name.
        """
        if isinstance(expression, OperandExpression):
            self._maybe_add_operand_dependency(
                DependencyType.VARIABLE_READ, expression.value, position
            )
            self._maybe_add_subscript_dependency(expression.subscript, position)
            return
        self._visit_expression(expression.left, position)
        self._visit_expression(expression.right, position)

    def visit_compute_statement(self, node: ComputeStatementNode) -> Any:
        """
        Register the target as ``VARIABLE_WRITE`` (plus its own subscript
        as a read, task #stage32) and every operand/subscript in the
        expression tree as ``VARIABLE_READ`` (task #stage35).

        Example: ``COMPUTE TOTAL(WS-I) = PRICE(WS-I) * QUANTITY(WS-I)``
        registers reads on ``PRICE``, ``QUANTITY``, and ``WS-I`` (once
        per occurrence, deduplicated by :meth:`_add_dependency`'s
        ``(source, type, target)`` key), and a write on ``TOTAL``.
        """
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_WRITE, node.target, node.start_position
        )
        self._maybe_add_subscript_dependency(node.target_subscript, node.start_position)
        self._visit_expression(node.expression, node.start_position)
        return None


# ----------------------------------------------------------------------
# Transitive dependency queries (task #111)
# ----------------------------------------------------------------------


def compute_transitive_dependencies(
    dependencies: list[Dependency],
    start: str,
    dependency_types: frozenset[DependencyType] | None = None,
) -> set[str]:
    """
    Discover every target transitively reachable from *start*.

    Given direct edges such as ``A -> B`` (``A`` PERFORMs ``B``) and
    ``B -> C``, this answers "what does ``A`` transitively depend on?"
    (``{B, C}``) by walking ``Dependency.source -> Dependency.target``
    edges as a graph, without mutating *dependencies* or the direct
    dependency list the caller holds -- this is a pure, read-only query
    over the already-extracted edges, not a new extraction pass.

    Only edges whose paragraph/program identity forms a coherent chain
    are followed: a dependency's ``source`` is the paragraph that
    contains it, so traversal here means "starting from paragraph
    *start*, what paragraphs/targets do its PERFORM/CALL chains
    eventually reach". Restricting *dependency_types* to
    ``{PERFORM, CALL}`` (the default) is what makes this a structural
    reachability query rather than one that also chases variable
    read/write or condition edges, which are not "A depends on B"
    chains in the same sense.

    Cycle-safe: a visited set prevents revisiting any node, so a cycle
    such as ``A -> B -> A`` terminates after discovering ``{A, B}``
    (via ``B``) without infinite traversal.

    Args:
        dependencies:
            The flat list of extracted Dependency objects to traverse.
            Never modified.
        start:
            The paragraph/program identifier to begin traversal from.
        dependency_types:
            Which dependency types count as traversable edges. Defaults
            to ``{DependencyType.PERFORM, DependencyType.CALL}`` -- the
            two relationship kinds that represent "control transfers
            to" and therefore compose transitively.

    Returns:
        The set of all targets transitively reachable from *start*.
        *start* itself is never included unless it is also reachable
        via a cycle back to itself.
    """
    if dependency_types is None:
        dependency_types = frozenset({DependencyType.PERFORM, DependencyType.CALL})

    edges_by_source: dict[str, list[str]] = {}
    for dep in dependencies:
        if dep.type not in dependency_types:
            continue
        edges_by_source.setdefault(dep.source, []).append(dep.target)

    visited: set[str] = set()
    stack: list[str] = list(edges_by_source.get(start, []))

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(edges_by_source.get(current, []))

    return visited
