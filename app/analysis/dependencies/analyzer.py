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
    CallStatementNode,
    DivideStatementNode,
    IfStatementNode,
    MoveStatementNode,
    MultiplyStatementNode,
    PerformStatementNode,
    PerformUntilStatementNode,
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

    def visit_if_statement(self, node: IfStatementNode) -> Any:
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_left, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.CONDITION, node.condition_right, node.start_position
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
        # only, no read-before-write); source is read only.
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_READ, node.source, node.start_position
        )
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_WRITE, node.target, node.start_position
        )
        return None

    def _visit_arithmetic(self, left: str, right: str, position: Any) -> None:
        """
        Shared handling for ADD/SUBTRACT/MULTIPLY/DIVIDE.

        In every one of these four statement shapes, ``left`` is the
        operand supplying a value (read only) and ``right`` is the
        accumulator the result is stored into -- which COBOL both reads
        (its prior value participates in the arithmetic) and writes
        (the result replaces it). Both effects on ``right`` are
        represented, per task #111's explicit example ("For `ADD A TO
        B` capture both the read of A and read/write effect on B where
        the model supports it").
        """
        self._maybe_add_operand_dependency(DependencyType.VARIABLE_READ, left, position)
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_READ, right, position
        )
        self._maybe_add_operand_dependency(
            DependencyType.VARIABLE_WRITE, right, position
        )

    def visit_add_statement(self, node: AddStatementNode) -> Any:
        self._visit_arithmetic(node.left, node.right, node.start_position)
        return None

    def visit_subtract_statement(self, node: SubtractStatementNode) -> Any:
        self._visit_arithmetic(node.left, node.right, node.start_position)
        return None

    def visit_multiply_statement(self, node: MultiplyStatementNode) -> Any:
        self._visit_arithmetic(node.left, node.right, node.start_position)
        return None

    def visit_divide_statement(self, node: DivideStatementNode) -> Any:
        self._visit_arithmetic(node.left, node.right, node.start_position)
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
