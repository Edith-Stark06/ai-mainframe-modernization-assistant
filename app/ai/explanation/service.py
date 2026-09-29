"""
Code Explanation Service

Provider-agnostic service for explaining COBOL source code.
"""

from typing import Any, Optional

from app.ai.explanation.models import CodeExplanation
from app.ai.explanation.prompts import build_explanation_prompt
from app.ai.providers import LLMProvider, LLMRequest

#: Placeholder ``summary`` for a reply the model did not structure. Never
#: shown to users (CodeExplanation.__str__ prints the reply alone when
#: structured is False); it only satisfies the model's non-empty rule.
_UNSTRUCTURED_LABEL = "Unstructured model response"


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
        summary_part = parts[0].split("Summary:", 1)[-1].strip()
        explanation_part = parts[1].strip()

        if not summary_part:
            raise ValueError("Parsed summary section is empty.")

        if not explanation_part:
            raise ValueError("Parsed explanation section is empty.")

        return CodeExplanation(summary=summary_part, explanation=explanation_part)
