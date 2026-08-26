# TASK-064 — BUSINESS RULE API INTEGRATION

## Objective

Integrate the existing BusinessRule domain capability into the existing
analysis API.

Task-064 connects:

COBOL source
    ↓
Parser / AST
    ↓
BusinessRuleExtractor
    ↓
BusinessRule
    ↓
BusinessRule normalization
    ↓
Analysis API
    ↓
JSON response

The goal is to expose deterministic business rules to API consumers while
preserving the existing analysis response contract.

---

## Prerequisites

Task-061 — BusinessRule domain model — MUST be merged.

Task-062 — BusinessRuleExtractor — MUST be merged.

Task-063 — BusinessRule normalization — MUST be merged.

If any prerequisite is not present in `origin/main`, STOP.

---

## Objective

Add business rules to the existing analysis response.

The existing analysis endpoint should expose an optional:

`business_rules`

field.

The API must use the existing BusinessRule domain model and existing
BusinessRuleExtractor.

The API layer must NOT duplicate business-rule extraction logic.

---

# API CONTRACT

## Response field

Add:

```json
{
  "business_rules": []
}