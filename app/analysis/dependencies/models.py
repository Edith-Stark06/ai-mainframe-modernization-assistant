"""
Dependency Models.

Defines immutable typed representations of dependencies.
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
            cannot actually justify.
    """

    type: DependencyType
    target: str
    source_location: Optional[Position] = None
    source: str = ""
    confidence: float = 1.0
