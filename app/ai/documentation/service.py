"""
Documentation Generation Service

Provider-agnostic service for generating technical documentation of COBOL source code.
"""

from typing import Any, Optional

from app.ai.documentation.models import Documentation, DocumentationSection
from app.ai.documentation.prompts import build_documentation_prompt
from app.ai.providers import LLMProvider, LLMRequest


class DocumentationGenerationService:
    """
    Service for generating structured documentation of COBOL code.

    Args:
        provider: The provider-agnostic LLM interface to use.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def generate_documentation(
        self, source: str, context: Optional[dict[str, Any]] = None
    ) -> Documentation:
        """
        Generate documentation for the given COBOL source code.

        Args:
            source: The COBOL source code.
            context: Optional structured analysis context (e.g. dependencies).

        Returns:
            A structured Documentation result.

        Raises:
            ValueError: If source is empty or whitespace-only.
            LLMProviderError: If the underlying LLM provider fails.
        """
        if not source or not source.strip():
            raise ValueError("COBOL source cannot be empty or whitespace-only.")

        prompt = build_documentation_prompt(source, context)
        request = LLMRequest(
            prompt=prompt,
            model=None,
            temperature=None,
            max_tokens=None,
        )

        response = self._provider.generate(request)

        return self._parse_documentation_result(response.text)

    def _parse_documentation_result(self, raw_text: str) -> Documentation:
        """Parse the raw text from the LLM into the Documentation model.

        Raises:
            ValueError: If the response is malformed, missing required sections,
                or contains empty sections.
        """
        text = raw_text.strip()
        if not text:
            raise ValueError("Provider response is empty or whitespace-only.")

        if "Title:" not in text or "Overview:" not in text:
            raise ValueError(
                "Provider response is missing required 'Title:' or 'Overview:' sections."
            )

        # Extract title
        parts = text.split("Overview:", 1)
        title_section = parts[0]
        title_part = title_section.split("Title:", 1)[-1].strip()

        # Extract overview and sections
        raw_sections = parts[1].split("Section:")

        # The first element is the overview
        overview_part = raw_sections[0].strip()

        sections = []
        for raw_sec in raw_sections[1:]:
            raw_sec = raw_sec.strip()
            if not raw_sec:
                # We skip empty sections, but maybe we should fail?
                # The requirements say "Reject: malformed sections".
                # An empty section block is arguably malformed.
                raise ValueError("Malformed section: empty section block.")

            sec_lines = raw_sec.split("\n", 1)
            if len(sec_lines) < 2:
                raise ValueError("Malformed section: missing content.")
            heading = sec_lines[0].strip()
            content = sec_lines[1].strip()
            sections.append(DocumentationSection(heading=heading, content=content))

        if not title_part:
            raise ValueError("Parsed title section is empty.")

        if not overview_part:
            raise ValueError("Parsed overview section is empty.")

        return Documentation(
            title=title_part, overview=overview_part, sections=tuple(sections)
        )
