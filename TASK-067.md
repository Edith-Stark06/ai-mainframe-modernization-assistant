# TASK-067 — COBOL CODE EXPLANATION ENGINE

## Objective

Implement the first real AI capability of Phase 2: a provider-agnostic COBOL code explanation service. The service accepts COBOL analysis context and uses the existing `LLMProvider` abstraction from Task-066 to generate a structured explanation of the COBOL program. The implementation remains deterministic and testable without network access by using the existing fake LLM provider in tests.

## Architecture

The AI explanation domain follows this flow:

```
COBOL source / analysis context
        ↓
CodeExplanationService
        ↓
Explanation request construction (build_explanation_prompt)
        ↓
LLMProvider (abstract interface)
        ↓
LLMResponse
        ↓
CodeExplanation (structured result)
```

The explanation service depends **exclusively** on `LLMProvider`. It does not directly depend on OpenAI, Anthropic, Ollama, provider SDKs, or HTTP clients.

## Code Explanation Model

`CodeExplanation` is a typed, immutable dataclass (`frozen=True`) representing the provider-neutral explanation result. It contains two required fields:
- `summary`: A high-level summary of the program's purpose.
- `explanation`: A detailed explanation of the program's operations and rules.

Empty or whitespace-only fields are rejected on initialization via a post-init check.

## Explanation Service

`CodeExplanationService` exposes `explain_code(source: str, context: Optional[dict] = None) -> CodeExplanation`.

### Error Behavior
- **Empty Input:** Rejects empty or whitespace-only source code immediately with a standard `ValueError`.
- **Provider Failures:** Transparently propagates `LLMProviderError` (e.g. `LLMProviderUnavailableError`) thrown by the provider layer. Does not fabricate explanation results.
- **Unstructured Response:** If the LLM generates a response missing the requested 'Summary:' / 'Explanation:' structure, the service falls back gracefully by applying a default summary and retaining the entire response as the detailed explanation.

## Prompt Construction

The prompt logic is encapsulated in `build_explanation_prompt`, a deterministic builder that injects context into the request string.
- Explicitly separates instructions from supplied COBOL source/context.
- Alphabetically sorts dependencies to guarantee determinism.
- Does not inject randomness, timestamps, conversation history, or external API requirements (e.g., embeddings).

## Non-Goals

The following are explicitly omitted from this implementation:
- Concrete LLM provider integrations (OpenAI/Anthropic SDKs).
- API endpoint integrations (no modifications to the existing `/analyze` route).
- Advanced AI flows (RAG, embeddings, vector databases, memory, tool calling, autonomous agents).
- Re-architecting Phase-1 capabilities (parser, AST, rules extractor, dependency analyzer).

## Testing

Comprehensive, focused tests (`tests/ai/test_explanation.py`) use the `FakeLLMProvider` to run offline with zero network dependency. Tests cover:
- Basic code explanation mapping
- Provider injection
- Empty/whitespace source rejection
- Fallback processing for unstructured LLM output
- Provider failure handling
- Deterministic prompt construction with dynamic context injection