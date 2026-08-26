# TASK-069 — AI ANALYSIS ORCHESTRATION

## Objective

Create a provider-agnostic AI analysis orchestration service that coordinates
the existing Phase-1 intelligence and Phase-2 AI capabilities.

The orchestrator must combine:

- source code
- analysis context
- dependency information
- business rules
- diagnostics
- COBOL explanation
- documentation generation

into one deterministic AI analysis workflow.

Task-069 is an orchestration/service-layer task.

It must NOT introduce a new HTTP endpoint.

---

## Existing Capabilities

The repository already contains:

### Phase 1

- Dependency analysis
- Dependency graph
- Dependency summary
- Business rule extraction
- Business rule normalization
- Analysis API

### Phase 2

- LLM provider abstraction
- CodeExplanationService
- DocumentationGenerationService

Task-069 connects these capabilities.

---

# Scope

Implement an `AIAnalysisOrchestrator` that:

1. accepts source and analysis context
2. prepares a stable AI analysis context
3. invokes the explanation service
4. invokes the documentation service
5. returns a structured combined result

The orchestrator must use dependency injection for:

- LLM provider
- explanation service
- documentation service

Do not instantiate concrete providers internally.

---

# Domain Model

Create a structured result model.

Recommended:

```python
AIAnalysisResult