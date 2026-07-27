# Testing Strategy

This document outlines the testing strategy for the AI Mainframe Modernization Assistant.

## Regression Testing

### Philosophy
The compiler utilizes a comprehensive regression testing framework to ensure that existing compiler functionality continues to work correctly as new features are added. The regression suite executes the **full compiler pipeline** end-to-end (from COBOL source code to generated Java source code). This protects every compiler stage from unintended behavioral changes and guarantees deterministic execution without relying on brittle, full-file Java string comparisons.

### Fixture Organization
Regression fixtures are real COBOL programs organized by category under `tests/regression/fixtures/`. 
For example:
- `basic/` - Fundamental programs like Hello World.
- `arithmetic/` - Programs involving mathematical operations (`ADD`, `SUBTRACT`).
- `control_flow/` - Programs testing conditionals and loops (`IF`, `PERFORM`).
- `invalid/` - Programs deliberately containing syntax or semantic errors.

Each `.cbl` fixture is accompanied by a `.json` sidecar file of the exact same name (e.g., `add.cbl` and `add.json`). The JSON file specifies the expected results of the compilation pipeline.

### Adding New Regression Tests
To add a new regression test:
1. Identify the appropriate category in `tests/regression/fixtures/` or create a new directory if needed.
2. Add the `.cbl` source code fixture representing the case to test.
3. Add a corresponding `.json` sidecar file containing the expectations.

**Example sidecar format (`.json`)**:
```json
{
  "success": true,
  "expected_java_constructs": [
    "public class AddTest {",
    "numB += numA;"
  ],
  "expected_diagnostics": []
}
```

- `success`: Whether the pipeline should complete without semantic errors.
- `expected_java_constructs`: An array of substrings that must be present in the generated Java code (if successful).
- `expected_diagnostics`: An array of diagnostic message substrings that must be emitted (if unsuccessful).

The framework automatically discovers any new `.cbl` files in the fixtures directory and includes them in the test suite. No manual registration is necessary.

### Expected Workflow for Future Contributors
1. When fixing a bug, first create a regression fixture that reliably reproduces the bug (it should fail).
2. Fix the bug in the compiler.
3. Verify that the regression test now passes.
4. When adding a new feature, include one or more regression fixtures that exercise it.
5. Always run `pytest tests/regression -v` before committing your code.
