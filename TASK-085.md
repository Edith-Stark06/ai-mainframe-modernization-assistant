# TASK-085 — Frontend Modernization Integration

## Objective

Begin the frontend phase of the AI Mainframe Modernization Assistant by integrating the existing frontend with the Modernization Intelligence Pipeline implemented in Tasks 080–084.

The frontend should provide a clean experience for analyzing a selected source file and displaying:

* modernization scores;
* generated program flow;
* modernization recommendations;
* modernization-aware Chat context where supported.

The frontend must consume the existing backend APIs and must not duplicate backend modernization logic.

---

## Scope

### 1. Frontend Architecture

Before making changes:

* identify the frontend framework and version;
* identify the package manager;
* inspect routing;
* inspect existing pages;
* inspect the API/client layer;
* inspect workspace/file-selection components;
* inspect Chat components;
* inspect state management;
* inspect existing UI/design system;
* inspect frontend tests;
* inspect build and lint configuration.

Reuse the existing architecture wherever possible.

Do not introduce a new framework or state-management solution.

---

### 2. Source Selection

Provide a way for the user to select a source file using the application's existing workspace/file-selection mechanism.

The UI must:

* display the selected filename;
* prevent empty submissions;
* preserve the selected file during analysis;
* handle invalid selections gracefully.

---

### 3. Modernization Analysis

Provide an action such as:

**Analyze for Modernization**

During analysis:

* show a loading state;
* prevent duplicate submissions;
* preserve the selected source;
* handle API failures.

The frontend must call the existing modernization backend API.

No modernization algorithms should be implemented in the frontend.

---

### 4. Modernization Results

Display the backend modernization response.

#### Score

Display the available modernization metrics clearly.

Do not alter the meaning or calculations of backend scores.

#### Flow

Display the generated flow.

The visualization should support:

* nodes;
* edges;
* node types;
* external/unresolved nodes.

Reuse an existing graph component/library if available.

If no graph visualization exists, implement a minimal maintainable representation appropriate to the existing frontend architecture.

#### Recommendations

Display the recommendations returned by the backend.

Do not invent recommendation text, severity, or priority.

---

### 5. Chat Integration

Where the existing Chat interface supports modernization context, integrate the new capability.

Use the existing backend contract for:

* `workspace_id`;
* `filename`;
* `include_modernization_context`.

The backend remains responsible for generating modernization context.

The frontend must not recreate or calculate modernization data itself.

---

### 6. UI States

Implement clear states for:

* idle;
* loading;
* success;
* error;
* empty results;
* insufficient modernization data;
* empty flow;
* unavailable recommendations.

Do not display misleading success information when the backend reports insufficient data.

---

### 7. Error Handling

Provide user-friendly handling for:

* validation errors;
* missing files;
* forbidden requests;
* server errors;
* network failures.

Never expose:

* stack traces;
* filesystem paths;
* internal exception messages.

---

### 8. Design

Follow the existing application's design system.

Reuse existing:

* typography;
* spacing;
* buttons;
* cards;
* colors;
* icons;
* layouts.

Do not redesign unrelated parts of the application.

The new UI should be responsive and accessible.

---

### 9. Testing

Add tests using the existing frontend testing conventions.

Cover at minimum:

1. component/page rendering;
2. source selection;
3. successful modernization request;
4. loading state;
5. API failure;
6. score rendering;
7. flow rendering;
8. recommendations rendering;
9. empty/insufficient flow;
10. modernization-aware Chat integration where applicable.

Mock backend requests at the existing API/client boundary.

Tests must not depend on a live backend.

---

### 10. Quality

Run the project's existing:

* formatter;
* linter;
* type checker;
* frontend test suite;
* production build.

Avoid unnecessary dependencies.

---

## Constraints

Do not:

* modify modernization algorithms;
* duplicate backend scoring;
* duplicate recommendation generation;
* generate modernization data in the browser;
* invent API fields;
* introduce a second state-management system;
* redesign unrelated pages;
* weaken backend validation or security;
* expose internal backend errors.

Do:

* reuse existing frontend architecture;
* consume existing backend contracts;
* keep API calls isolated in the API/client layer;
* create focused reusable components;
* add appropriate tests;
* preserve existing behavior.

---

## Acceptance Criteria

Task 085 is complete when:

* [ ] Existing frontend architecture has been inspected.
* [ ] Source selection works.
* [ ] Modernization analysis can be triggered.
* [ ] Loading state is displayed.
* [ ] Modernization scores are displayed.
* [ ] Flow is displayed.
* [ ] Recommendations are displayed.
* [ ] Empty/insufficient data states are handled.
* [ ] API errors are handled safely.
* [ ] Modernization context integrates with Chat where supported.
* [ ] Frontend tests are added and passing.
* [ ] Linting passes.
* [ ] Formatting passes.
* [ ] Type checking passes.
* [ ] Production build succeeds.
* [ ] No unrelated backend behavior is changed.

---

## Verification

Before completion:

```bash
git status
git diff --check
git diff main...HEAD
```

The final report must include:

* frontend architecture discovered;
* files changed;
* components/pages added;
* API integration;
* tests and exact results;
* formatter result;
* linter result;
* type-check result;
* production build result;
* any pre-existing failures.
