# TASK-066 — LLM PROVIDER ABSTRACTION

## Objective

Establish a provider-agnostic interface for the AI layer. This abstraction allows future AI capabilities to communicate with an LLM without depending directly on concrete SDKs such as OpenAI, Anthropic, or Ollama. 

This ensures that the AI layer is easily testable, switchable, and resilient to provider changes.

## Architecture

The AI layer follows this dependency direction:

```
AI capability
    ↓
LLM interface (LLMProvider)
    ↓
Concrete Provider Implementation (e.g., FakeLLMProvider)
```

No future AI capabilities should be coupled to concrete external providers directly.

## Provider Contract

The `LLMProvider` protocol defines the base contract for text generation:

```python
class LLMProvider(Protocol):
    def generate(self, request: LLMRequest) -> LLMResponse:
        ...
```

## Request and Response Models

Both `LLMRequest` and `LLMResponse` are highly restrictive, immutable Pydantic `BaseModel`s. They include only essential provider-neutral fields.

### LLMRequest
- `prompt` (str): The prompt to send to the LLM.
- `model` (str | None): Optional model identifier.
- `temperature` (float | None): Optional temperature configuration.
- `max_tokens` (int | None): Optional tokens generation limit.

### LLMResponse
- `text` (str): The generated text.
- `model` (str | None): The model used for generation.
- `usage` (dict[str, Any] | None): Optional provider-neutral usage statistics.

SDK objects (like raw HTTP responses) must never leak into these models.

## Error Model

Defined in `errors.py`, these exceptions map provider-specific errors to common abstractions:

- `LLMProviderError`: Base AI provider exception.
- `LLMProviderUnavailableError`: Raised when the underlying provider is unreachable, times out, or returns a 500.
- `LLMConfigurationError`: Raised when the request is invalid or the provider configuration is incorrect (e.g. invalid API key).

## Fake Provider

A deterministic `FakeLLMProvider` is provided for tests. 
- It requires no network or credentials.
- It returns static predictable text.
- It can optionally simulate `LLMProviderUnavailableError` and `LLMConfigurationError` scenarios.

## Dependency Injection

Future AI services (such as a code explainer) can depend on the `LLMProvider` abstraction directly, allowing tests to inject the `FakeLLMProvider` rather than configuring a real one. 

## Configuration Behavior

No new configuration dependencies were introduced. The application and test suite remain entirely capable of running offline without network access or required API keys.

## Non-Goals

- Implementing actual RAG, embeddings, or code explanation endpoints.
- Introducing concrete SDK integrations (e.g. OpenAI).
- Implementing streaming or chat functionality.

## Validation

All tests cover:
- Protocol contract and types
- Request/Response construction and immutability
- Fake provider determinism and error simulation
- Dependency injection compatibility
- JSON serialization
- Backward compatibility (Phase 1 features remain completely unaffected).