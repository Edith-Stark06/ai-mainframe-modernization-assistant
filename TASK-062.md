# TASK-062 — Business Rule Extractor

## Objective

Extract business rules from the existing parsed/semantic representation.

The extractor converts supported COBOL control-flow/business-logic constructs
into BusinessRule domain objects.

## Initial Supported Patterns

At minimum:

- IF / ELSE
- nested IF where existing AST supports it
- COMPUTE actions
- MOVE actions where semantically appropriate
- DISPLAY/action statements where appropriate

The first priority is conditional business logic.

## Example

IF YEARS-SERVICE > 5
    COMPUTE BONUS = SALARY * .20
ELSE
    COMPUTE BONUS = SALARY * .10
END-IF

Produces two BusinessRule objects.

## Requirements

- consume existing AST/IR structures
- do not parse source text directly
- preserve source locations
- deterministic output
- no LLM dependency
- no filesystem dependency
- no API dependency

## Non-Goals

Do not modify parser or AST.

Do not normalize beyond what is necessary to create valid domain rules.

Do not add LLM/RAG/frontend functionality.

## Tests

Cover:

- simple IF
- IF/ELSE
- nested IF if supported
- multiple actions
- source locations
- deterministic ordering
- unsupported constructs
- empty input

## Validation

Run full repository validation.

## Branch

feat/task-062-business-rule-extractor

## Commit

feat: implement business rule extractor

## PR

feat: Task-062 business rule extractor

Do not merge.