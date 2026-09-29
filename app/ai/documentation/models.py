"""
Documentation Models.

Defines immutable typed representations of code documentation.
"""

from dataclasses import dataclass, field


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
        structured: ``True`` when the model replied in the requested
            ``Title:``/``Overview:`` format. ``False`` when it did not
            and the reply is carried as-is in ``overview`` (see
            ``DocumentationGenerationService.generate_documentation``'s
            ``allow_unstructured``); ``title`` is then only a label.
    """

    title: str
    overview: str
    sections: tuple[DocumentationSection, ...] = field(default_factory=tuple)
    structured: bool = True

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ValueError("Documentation title cannot be empty or whitespace-only.")
        if not self.overview or not self.overview.strip():
            raise ValueError(
                "Documentation overview cannot be empty or whitespace-only."
            )

    def __str__(self) -> str:
        """Human-readable text, not the dataclass repr -- this is what
        chat shows the user."""
        if not self.structured:
            return self.overview
        parts = [self.title, "", self.overview]
        for section in self.sections:
            parts += ["", f"{section.heading}", section.content]
        return "\n".join(parts)
