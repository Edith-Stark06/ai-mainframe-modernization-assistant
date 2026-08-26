"""
Tests for the COBOL Code Explanation Engine.
"""

import pytest

from app.ai.explanation import (
    CodeExplanation,
    CodeExplanationService,
    build_explanation_prompt,
)
from app.ai.providers import FakeLLMProvider, LLMProviderUnavailableError


def test_code_explanation_model_validation() -> None:
    """Test CodeExplanation domain model validation and immutability."""
    # Valid
    expl = CodeExplanation(summary="Sum", explanation="Exp")
    assert expl.summary == "Sum"
    assert expl.explanation == "Exp"

    # Empty summary
    with pytest.raises(ValueError, match="summary cannot be empty"):
        CodeExplanation(summary="   ", explanation="Exp")

    # Empty explanation
    with pytest.raises(ValueError, match="detail cannot be empty"):
        CodeExplanation(summary="Sum", explanation="")


def test_build_explanation_prompt_basic() -> None:
    """Test prompt building with no context."""
    source = "MOVE A TO B."
    prompt = build_explanation_prompt(source)

    assert "Please explain the following COBOL program." in prompt
    assert "=== COBOL SOURCE ===" in prompt
    assert "MOVE A TO B." in prompt
    assert "Program Identifier" not in prompt


def test_build_explanation_prompt_with_context() -> None:
    """Test prompt building with structured context."""
    source = "CALL 'SUBPGM'"
    context = {
        "program_id": "MAINPGM",
        "dependencies": ["SUBPGM", "OTHER"],
        "business_rules": ["A > B => MOVE 1 TO X"],
    }

    prompt = build_explanation_prompt(source, context)

    assert "Program Identifier: MAINPGM" in prompt
    assert "- Explain the dependencies" in prompt
    assert "- Explain the business rules" in prompt

    assert "=== DEPENDENCIES ===" in prompt
    assert "- OTHER" in prompt
    assert "- SUBPGM" in prompt  # Alphabetical sort expected

    assert "=== BUSINESS RULES ===" in prompt
    assert "A > B => MOVE 1 TO X" in prompt


def test_service_basic_explanation() -> None:
    """Test basic service operation returning structured CodeExplanation."""
    fake_response = "Summary: A simple test.\nExplanation: It tests the service."
    provider = FakeLLMProvider(response_text=fake_response)
    service = CodeExplanationService(provider=provider)

    source = "DISPLAY 'HELLO'."
    result = service.explain_code(source)

    assert isinstance(result, CodeExplanation)
    assert result.summary == "A simple test."
    assert result.explanation == "It tests the service."

    # Verify request sent to provider
    req = provider.last_request
    assert req is not None
    assert "DISPLAY 'HELLO'." in req.prompt


def test_service_rejects_empty_source() -> None:
    """Test that empty or whitespace-only source is rejected."""
    provider = FakeLLMProvider()
    service = CodeExplanationService(provider=provider)

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.explain_code("")

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.explain_code("   \n\t  ")

    # Provider should not be called
    assert provider.last_request is None


def test_service_rejects_empty_response() -> None:
    """Test that empty response raises an error."""
    provider = FakeLLMProvider(response_text="")
    service = CodeExplanationService(provider=provider)

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.explain_code("DISPLAY 'HELLO'")


def test_service_rejects_whitespace_response() -> None:
    """Test that whitespace-only response raises an error."""
    provider = FakeLLMProvider(response_text="   \n  \t")
    service = CodeExplanationService(provider=provider)

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.explain_code("DISPLAY 'HELLO'")


def test_service_rejects_missing_explanation() -> None:
    """Test that missing explanation section raises an error."""
    provider = FakeLLMProvider(response_text="Summary: A simple program.")
    service = CodeExplanationService(provider=provider)

    with pytest.raises(ValueError, match="missing required"):
        service.explain_code("DISPLAY 'HELLO'")


def test_service_rejects_missing_summary() -> None:
    """Test that missing summary section raises an error."""
    provider = FakeLLMProvider(response_text="Explanation: A simple program.")
    service = CodeExplanationService(provider=provider)

    with pytest.raises(ValueError, match="missing required"):
        service.explain_code("DISPLAY 'HELLO'")


def test_service_rejects_empty_summary() -> None:
    """Test that empty summary section raises an error."""
    provider = FakeLLMProvider(
        response_text="Summary:\n\nExplanation: It displays a message."
    )
    service = CodeExplanationService(provider=provider)

    with pytest.raises(ValueError, match="Parsed summary section is empty"):
        service.explain_code("DISPLAY 'HELLO'")


def test_service_rejects_empty_explanation() -> None:
    """Test that empty explanation section raises an error."""
    provider = FakeLLMProvider(
        response_text="Summary: It displays a message.\n\nExplanation:"
    )
    service = CodeExplanationService(provider=provider)

    with pytest.raises(ValueError, match="Parsed explanation section is empty"):
        service.explain_code("DISPLAY 'HELLO'")


def test_service_provider_failure() -> None:
    """Test that provider errors propagate seamlessly without wrapping."""
    provider = FakeLLMProvider(simulate_failure=True)
    service = CodeExplanationService(provider=provider)

    with pytest.raises(LLMProviderUnavailableError, match="Simulated provider failure"):
        service.explain_code("MOVE A TO B.")
