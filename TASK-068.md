# TASK-068 — COBOL DOCUMENTATION GENERATION ENGINE

## Objective
Create a reusable AI service for generating structured technical documentation for COBOL programs using a provider-agnostic approach.

## Architecture
This implementation adheres to the boundaries established in Task-066 and Task-067. The documentation engine is isolated within `app.ai.documentation`, decoupled from both specific LLM providers and the core parsing infrastructure.

### Models
- `Documentation`: An immutable dataclass representing the overall documentation result (title, overview, and sections).
- `DocumentationSection`: An immutable dataclass representing individual sections with headings and content.

### Service
- `DocumentationGenerationService`: A lightweight, provider-agnostic service.
- Requires an `LLMProvider` instance via dependency injection.
- Implements strict validation on input source code and output structure.
- Rejects malformed responses rather than fabricating fallback documentation.

### Prompt
- `build_documentation_prompt`: A deterministic function to construct prompts.
- Clearly separates instructions, source code, and analysis context.
- Allows optional contextual injection (dependencies, business rules, diagnostics).
- Demands a strict structured format (`Title:`, `Overview:`, `Section:`).

## Validation & Error Handling
- Empty or whitespace-only source inputs are rejected pre-flight.
- Provider failures result in provider-neutral exceptions (`LLMProviderError`, `LLMProviderUnavailableError`).
- Malformed provider outputs (missing sections, empty titles) raise `ValueError` during parsing.

## Testing
- Tested comprehensively using `FakeLLMProvider` without network access.
- Tests cover prompt determinism, context injection, model immutability, and robust response validation.

## Non-Goals
This task does not implement:
- Concrete LLM integrations (OpenAI, Anthropic, Ollama).
- RAG or embeddings functionality.
- Modifications to the existing Phase-1 analysis API.
- End-user chat interfaces or conversational memory.