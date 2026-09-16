"""
Dependency Models.

Defines immutable typed representations of dependencies.

Exposes ``STRUCTURAL_DEPENDENCY_TYPES`` -- the subset of
``DependencyType`` (CALL, PERFORM, COPY) that names another
program/paragraph/copybook rather than a plain data item, and is
therefore the only subset meaningful to workspace file resolution and
the cross-program dependency graph.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
from app.parser.lexer.position import Position


class DependencyType(Enum):
    """Types of extracted COBOL dependencies."""

    COPY = "COPY"
    CALL = "CALL"
    PERFORM = "PERFORM"

    # Added by task #111 (Dependency Analysis).
    VARIABLE_READ = "VARIABLE_READ"  # an operand whose value is read
    VARIABLE_WRITE = "VARIABLE_WRITE"  # an operand a statement assigns to
    CONDITION = "CONDITION"  # a variable an IF/PERFORM UNTIL condition tests


# The dependency types that name another program, paragraph, or copybook
# -- i.e. a cross-unit control transfer or inclusion, as opposed to a
# reference to a plain data item (VARIABLE_READ/VARIABLE_WRITE/CONDITION).
# Only these are meaningful input to workspace file resolution
# (:class:`~app.analysis.dependencies.resolver.WorkspaceDependencyResolver`)
# and the cross-program dependency graph
# (:class:`~app.analysis.dependencies.graph.DependencyGraph`) built from
# it -- a variable name is never a workspace file to resolve. Review
# finding #2 (post-#111): consumers that build that graph must filter to
# this set rather than passing every extracted Dependency through.
STRUCTURAL_DEPENDENCY_TYPES: frozenset[DependencyType] = frozenset(
    {DependencyType.CALL, DependencyType.PERFORM, DependencyType.COPY}
)


@dataclass(frozen=True)
class Dependency:
    """
    Immutable representation of a COBOL dependency.

    Attributes:
        type:
            The kind of relationship this dependency represents.
        target:
            The identifier this dependency points to -- a paragraph
            name, program name, or variable name, depending on ``type``.
        source_location:
            Where in the source this dependency was found, or ``None``
            if unavailable.
        source:
            The paragraph name this dependency originates from, or
            ``""`` if unknown or not applicable (task #111). Needed
            because two different paragraphs performing or calling the
            same target, or reading/writing the same variable, are two
            distinct dependencies, not one -- see
            :class:`~app.analysis.dependencies.analyzer.DependencyAnalyzer`'s
            deduplication, which is keyed on ``(source, type, target)``.
        confidence:
            How certain this dependency is, from ``0.0`` to ``1.0``
            (task #111). ``1.0`` (the default) for every dependency this
            analyzer currently extracts, since all of them are derived
            directly and unambiguously from AST structure (a MOVE's
            operands, a CALL's literal target, and so on) rather than
            inferred or guessed. The field exists so a future pass that
            *does* need to express uncertainty (e.g. a dynamically
            computed CALL target) has somewhere to record it, without
            requiring every existing dependency to claim a confidence it
            cannot actually justify. Validated to lie within ``[0.0,
            1.0]`` in :meth:`__post_init__` -- an out-of-range value
            (e.g. a future pass passing a raw, unnormalized score) is
            rejected at construction rather than silently accepted.

    Raises:
        ValueError: If ``confidence`` is outside the inclusive ``[0.0,
            1.0]`` range.
    """

    type: DependencyType
    target: str
    source_location: Optional[Position] = None
    source: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"Dependency confidence must be within [0.0, 1.0], "
                f"got {self.confidence!r}."
            )
