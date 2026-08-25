"""
Business Rule Models.

Defines immutable typed representations of extracted business rules.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from app.parser.lexer.position import Position


@dataclass(frozen=True)
class BusinessRule:
    """
    Immutable representation of a business rule.

    A rule contains a condition and one or more actions that execute
    when the condition is met.

    Attributes:
        condition:
            The normalized logic expression that triggers the rule (e.g. 'YEARS-SERVICE > 5').
        actions:
            A tuple of one or more actions to execute (e.g. 'BONUS = SALARY * .20').
        source_location:
            The position in the source code where this rule originates.
    """

    condition: str
    actions: Tuple[str, ...]
    source_location: Optional[Position] = None

    def __post_init__(self) -> None:
        """Validate rule constraints."""
        if not self.condition or not self.condition.strip():
            raise ValueError(
                "Business rule condition cannot be empty or whitespace-only."
            )
        if not self.actions:
            raise ValueError("Business rule must have at least one action.")
        for action in self.actions:
            if not action or not action.strip():
                raise ValueError(
                    "Business rule action cannot be empty or whitespace-only."
                )
