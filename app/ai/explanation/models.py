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
        structured: ``True`` when the model replied in the requested
            ``Summary:``/``Explanation:`` format. ``False`` when it did
            not and the reply is carried as-is in ``explanation`` (see
            ``CodeExplanationService.explain_code``'s
            ``allow_unstructured``); ``summary`` is then only a label.
    """

    summary: str
    explanation: str
    structured: bool = True

    def __post_init__(self) -> None:
        if not self.summary or not self.summary.strip():
            raise ValueError("Explanation summary cannot be empty or whitespace-only.")
        if not self.explanation or not self.explanation.strip():
            raise ValueError("Explanation detail cannot be empty or whitespace-only.")

    def __str__(self) -> str:
        """Human-readable text, not the dataclass repr -- this is what
        chat shows the user."""
        if not self.structured:
            return self.explanation
        return f"Summary: {self.summary}\n\nExplanation: {self.explanation}"
