"""
Code Explanation Models.

Defines immutable typed representations of code explanations.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeExplanation:
    """
    Immutable representation of a generated code explanation.

    Attributes:
        summary: A high-level summary of the program's purpose.
        explanation: A detailed explanation of the program's operations and rules.
    """

    summary: str
    explanation: str

    def __post_init__(self) -> None:
        if not self.summary or not self.summary.strip():
            raise ValueError("Explanation summary cannot be empty or whitespace-only.")
        if not self.explanation or not self.explanation.strip():
            raise ValueError("Explanation detail cannot be empty or whitespace-only.")
