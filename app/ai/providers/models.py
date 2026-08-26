"""
AI Provider Models

Immutable request and response models for the LLM abstraction.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMRequest(BaseModel):
    """A provider-agnostic request for text generation."""

    model_config = ConfigDict(frozen=True)

    prompt: str = Field(..., description="The prompt to send to the LLM.")
    model: str | None = Field(None, description="Optional model identifier.")
    temperature: float | None = Field(None, ge=0.0, description="Optional temperature.")
    max_tokens: int | None = Field(
        None, gt=0, description="Optional maximum tokens to generate."
    )


class LLMResponse(BaseModel):
    """A provider-agnostic response from text generation."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(..., description="The generated text.")
    model: str | None = Field(None, description="The model used for generation.")
    usage: dict[str, Any] | None = Field(
        None, description="Optional provider-neutral usage statistics."
    )
