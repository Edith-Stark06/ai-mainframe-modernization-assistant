# TASK-061 — Business Rule Domain Model

## Objective

Introduce a typed domain representation for business rules extracted from
COBOL analysis.

The model must represent a normalized business condition and the action
or actions associated with that condition.

## Example

COBOL:

IF YEARS-SERVICE > 5
    COMPUTE BONUS = SALARY * .20
ELSE
    COMPUTE BONUS = SALARY * .10
END-IF

Domain representation:

Rule 1:
condition: YEARS-SERVICE > 5
actions:
- BONUS = SALARY * .20

Rule 2:
condition: YEARS-SERVICE <= 5
actions:
- BONUS = SALARY * .10

## Scope

Create a typed immutable domain model.

The model should support:

- condition
- actions
- source location
- rule metadata required by existing architecture

Use existing Position/source-location models where appropriate.

Rules must be deterministic and structurally comparable.

## Non-Goals

Do not:

- implement extraction
- call an LLM
- add RAG
- add API endpoints
- modify parser behavior
- modify AST structure
- modify IR semantics
- modify frontend

## Validation

Add focused unit tests for:

- condition must contain non-whitespace content
- every action must contain non-whitespace content
- valid rule
- multiple actions
- source location
- equality
- immutability
- deterministic representation
- invalid/empty required values

Run the complete project validation suite.

## Expected Files

Domain model under the existing analysis/domain conventions.
Tests under the existing analysis tests.
TASK-061.md.

No unrelated changes.

## Branch

feat/task-061-business-rule-domain-model

## Commit

feat: add business rule domain model

## PR

Title:
feat: Task-061 business rule domain model

Base:
main

Do not merge.

## Definition of Done

- typed rule model exists
- immutable where appropriate
- source location supported
- tests pass
- static checks pass
- no parser/AST/API changes
- TASK-061.md exists
- PR created
- PR OPEN
- PR NOT MERGED