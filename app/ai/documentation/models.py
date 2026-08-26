"""
Documentation Models.

Defines immutable typed representations of code documentation.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class DocumentationSection:
    """
    Immutable representation of a section within documentation.

    Attributes:
        heading: The heading of the section.
        content: The content of the section.
    """

    heading: str
    content: str

    def __post_init__(self) -> None:
        if not self.heading or not self.heading.strip():
            raise ValueError(
                "Documentation section heading cannot be empty or whitespace-only."
            )
        if not self.content or not self.content.strip():
            raise ValueError(
                "Documentation section content cannot be empty or whitespace-only."
            )


@dataclass(frozen=True)
class Documentation:
    """
    Immutable representation of generated COBOL documentation.

    Attributes:
        title: The title of the documentation.
        overview: A high-level overview.
        sections: A list of documentation sections.
    """

    title: str
    overview: str
    sections: List[DocumentationSection] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ValueError("Documentation title cannot be empty or whitespace-only.")
        if not self.overview or not self.overview.strip():
            raise ValueError(
                "Documentation overview cannot be empty or whitespace-only."
            )
