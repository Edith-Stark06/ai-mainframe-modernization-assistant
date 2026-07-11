# TASK-004

# Title

Enterprise Workspace Intelligence

---

## Objective

Implement a workspace scanning and inventory subsystem.

Do NOT implement COBOL parsing.

Only discover, classify and inventory uploaded files.

---

## Read

- AGENTS.md
- PROJECT_SPEC.md
- ROADMAP.md
- CONTRIBUTING.md

---

## Create

app/workspace/

scanner.py

classifier.py

inventory.py

summary.py

models.py

app/api/routers/workspace.py

tests/workspace/

---

## Scanner

Implement recursive project scanning.

Support nested folders.

Support ZIP workspace extraction.

---

## Classification

Recognize

- COBOL
- Copybook
- JCL
- PROC
- BMS
- XML
- JSON
- Text
- Unknown

---

## Inventory

Generate metadata for every discovered file.

Store

- path
- filename
- extension
- hash
- size
- type

---

## Summary

Generate project statistics.

Example

412 COBOL

218 Copybooks

87 JCL

---

## API

GET

/workspaces/{workspace_id}/summary

GET

/workspaces/{workspace_id}/inventory

---

## Tests

Scanner

Classifier

Inventory

Summary

API

---

## Git

Branch

feature/workspace-intelligence

Commit

feat(workspace): implement enterprise workspace intelligence

Create PR

Title

feat(workspace): implement enterprise workspace intelligence

Closes #6

---

## Constraints

Do not implement parser.

Do not modify ingestion.

Do not modify AI.

Implement only workspace intelligence.