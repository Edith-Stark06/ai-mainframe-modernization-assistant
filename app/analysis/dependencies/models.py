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


@dataclass(frozen=True)
class Dependency:
    """
    Immutable representation of a COBOL dependency.
    """

    type: DependencyType
    target: str
    source_location: Optional[Position] = None
