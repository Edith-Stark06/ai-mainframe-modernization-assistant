"""
Code Explanation Service

Provider-agnostic service for explaining COBOL source code.
"""

import re
from typing import Any, Optional

from app.ai.explanation.models import CodeExplanation
from app.ai.explanation.prompts import build_explanation_prompt
from app.ai.providers import LLMProvider, LLMRequest

#: Placeholder ``summary`` for a reply the model did not structure. Never
#: shown to users (CodeExplanation.__str__ prints the reply alone when
#: structured is False); it only satisfies the model's non-empty rule.
_UNSTRUCTURED_LABEL = "Unstructured model response"

#: A markdown bold marker the model left dangling around a section label
#: ("Summary: **" / a lone "**" closing the section). Only a marker set off by
#: whitespace is removed, so real emphasis such as "**bold** text" is kept.
#: ``Summary:`` / ``**Summary:**`` / ``**Summary**:`` at the start of a reply.
_LEADING_SUMMARY_LABEL = re.compile(
    r"^\s*\*{0,2}\s*summary\s*\*{0,2}\s*:\s*\*{0,2}\s*", re.IGNORECASE
)
_ORPHAN_LEADING = re.compile(r"^\*{2,}\s+")
_ORPHAN_TRAILING = re.compile(r"\s+\*{2,}$")


def _strip_orphan_markers(text: str) -> str:
    """Remove dangling ``**`` markers from the ends of a parsed section."""
    text = text.strip()
    if not text.strip("* " + chr(9) + chr(10) + chr(13)):
        return ""  # nothing but markers: the section is empty
    text = _ORPHAN_LEADING.sub("", text)
    text = _ORPHAN_TRAILING.sub("", text)
    return text.strip()


class CodeExplanationService:
    """
    Service for generating structured explanations of COBOL code.

    Args:
        provider: The provider-agnostic LLM interface to use.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def explain_code(
        self,
        source: str,
        context: Optional[dict[str, Any]] = None,
        *,
        allow_unstructured: bool = False,
    ) -> CodeExplanation:
        """
        Explain the given COBOL source code.

        Args:
            source: The COBOL source code.
            context: Optional structured analysis context (e.g. dependencies).
            allow_unstructured: By default a reply that does not follow
                the requested ``Summary:``/``Explanation:`` format is
                rejected with ``ValueError``. When ``True`` (chat, where
                a small or conversational model routinely answers in
                plain prose), such a non-empty reply is instead returned
                as-is with ``structured=False`` -- the model's real
                words, clearly marked as unstructured, never
                reconstructed or invented. An empty reply is still an
                error.

        Returns:
            A structured explanation containing a summary and detailed explanation.

        Raises:
            ValueError: If source is empty or whitespace-only.
            LLMProviderError: If the underlying LLM provider fails.
        """
        if not source or not source.strip():
            raise ValueError("COBOL source cannot be empty or whitespace-only.")

        prompt = build_explanation_prompt(source, context)
        request = LLMRequest(
            prompt=prompt,
            model=None,
            temperature=None,
            max_tokens=None,
        )

        response = self._provider.generate(request)

        try:
            return self._parse_explanation_result(response.text)
        except ValueError:
            text = response.text.strip()
            if not allow_unstructured or not text:
                raise
            # A one-line answer often comes as just "Summary: ..." (no
            # Explanation); show the answer, not the label.
            text = _strip_orphan_markers(_LEADING_SUMMARY_LABEL.sub("", text)) or text
            return CodeExplanation(
                summary=_UNSTRUCTURED_LABEL, explanation=text, structured=False
            )

    def _parse_explanation_result(self, raw_text: str) -> CodeExplanation:
        """Parse the raw text from the LLM into the CodeExplanation model.

        Raises:
            ValueError: If the response is malformed, missing required sections,
                or contains empty sections.
        """
        text = raw_text.strip()
        if not text:
            raise ValueError("Provider response is empty or whitespace-only.")

        if "Summary:" not in text or "Explanation:" not in text:
            raise ValueError(
                "Provider response is missing required 'Summary:' or 'Explanation:' sections."
            )

        parts = text.split("Explanation:", 1)
        summary_part = _strip_orphan_markers(parts[0].split("Summary:", 1)[-1])
        explanation_part = _strip_orphan_markers(parts[1])

        if not summary_part:
            raise ValueError("Parsed summary section is empty.")

        if not explanation_part:
            raise ValueError("Parsed explanation section is empty.")

        return CodeExplanation(summary=summary_part, explanation=explanation_part)
