# TASK-063 — Business Rule Normalization

## Objective

Normalize extracted BusinessRule objects into a stable, canonical
representation suitable for API and future AI/RAG processing.

## Requirements

Normalization must:

- preserve semantic meaning
- produce deterministic output
- normalize condition representation
- normalize action representation
- preserve source location
- avoid changing business meaning
- normalizes whitespace
- normalizes identifiers/keywords according to the existing contract
- preserves string literal contents
- preserves numeric literal representation
- does not change semantic meaning

Do not use an LLM.

## Examples

Equivalent representations of:

YEARS-SERVICE > 5

should produce the same canonical condition representation where
the existing AST semantics prove equivalence.

Do not perform speculative algebraic transformations.

## Non-Goals

Do not:

- modify parser
- modify AST
- modify IR
- extract new rules
- add API
- add LLM
- add RAG
- add frontend

## Tests

Cover:

- canonical condition
- canonical actions
- multiple actions
- source locations
- deterministic output
- semantic preservation
- unsupported/invalid input

## Branch

feat/task-063-business-rule-normalization

## Commit

feat: normalize business rule representations

## PR

feat: Task-063 business rule normalization

Do not merge.