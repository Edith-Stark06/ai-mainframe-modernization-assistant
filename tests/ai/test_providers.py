"""
Tests for the AI Provider Abstraction.
"""

import json

import pytest
from pydantic import ValidationError

from app.ai.providers import (
    FakeLLMProvider,
    LLMConfigurationError,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMRequest,
    LLMResponse,
)


def test_request_model() -> None:
    """Test LLMRequest construction, optional fields, and immutability."""
    # Basic creation
    req = LLMRequest(prompt="Hello, world!")
    assert req.prompt == "Hello, world!"
    assert req.model is None
    assert req.temperature is None
    assert req.max_tokens is None

    # Full creation
    req2 = LLMRequest(
        prompt="Explain this.",
        model="test-model",
        temperature=0.5,
        max_tokens=100,
    )
    assert req2.model == "test-model"
    assert req2.temperature == 0.5
    assert req2.max_tokens == 100

    # Immutability
    with pytest.raises(ValidationError):
        req.prompt = "New prompt"  # type: ignore


def test_response_model() -> None:
    """Test LLMResponse construction, optional fields, and immutability."""
    res = LLMResponse(text="Generated text.")
    assert res.text == "Generated text."
    assert res.model is None
    assert res.usage is None

    res2 = LLMResponse(
        text="Detailed response.",
        model="test-model",
        usage={"tokens": 42},
    )
    assert res2.model == "test-model"
    assert res2.usage == {"tokens": 42}

    # Immutability
    with pytest.raises(ValidationError):
        res.text = "New text"  # type: ignore


def test_fake_provider_deterministic_output() -> None:
    """Test FakeLLMProvider returns deterministic predictable output."""
    provider = FakeLLMProvider(response_text="Predictable answer")
    req = LLMRequest(prompt="What is the answer?", model="custom-model")

    res = provider.generate(req)

    assert res.text == "Predictable answer"
    assert res.model == "custom-model"
    assert res.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    }

    # State inspection
    assert provider.last_request == req


def test_fake_provider_simulated_failure() -> None:
    """Test simulating a provider failure."""
    provider = FakeLLMProvider(simulate_failure=True)
    req = LLMRequest(prompt="Fail me.")

    with pytest.raises(LLMProviderUnavailableError) as exc_info:
        provider.generate(req)

    assert "failure" in str(exc_info.value).lower()


def test_fake_provider_invalid_configuration() -> None:
    """Test simulating an invalid configuration or request."""
    provider = FakeLLMProvider(simulate_invalid_config=True)
    req = LLMRequest(prompt="Bad request.")

    with pytest.raises(LLMConfigurationError) as exc_info:
        provider.generate(req)

    assert "invalid" in str(exc_info.value).lower()


def test_dependency_injection() -> None:
    """Test that a service can accept the LLMProvider abstraction."""

    class DummyExplanationService:
        def __init__(self, provider: LLMProvider) -> None:
            self.provider = provider

        def explain(self, code: str) -> str:
            req = LLMRequest(prompt=f"Explain: {code}")
            res = self.provider.generate(req)
            return res.text

    fake_provider = FakeLLMProvider(response_text="It prints hello.")
    service = DummyExplanationService(provider=fake_provider)

    result = service.explain("print('hello')")

    assert result == "It prints hello."
    assert fake_provider.last_request is not None
    assert fake_provider.last_request.prompt == "Explain: print('hello')"


def test_json_serialization() -> None:
    """Test that the models are JSON serializable and follow expected schema."""
    req = LLMRequest(prompt="Hi", model="gpt-4", temperature=0.7, max_tokens=150)

    # Pydantic v2 serialization
    req_json = req.model_dump_json()
    req_dict = json.loads(req_json)

    assert req_dict["prompt"] == "Hi"
    assert req_dict["model"] == "gpt-4"
    assert req_dict["temperature"] == 0.7
    assert req_dict["max_tokens"] == 150

    res = LLMResponse(text="Hello", model="gpt-4", usage={"total": 5})

    res_json = res.model_dump_json()
    res_dict = json.loads(res_json)

    assert res_dict["text"] == "Hello"
    assert res_dict["model"] == "gpt-4"
    assert res_dict["usage"]["total"] == 5
