# Multi-operand `DISPLAY`

## Purpose

`DISPLAY 'SYSTEM STATUS: ' WS-STATUS` was parsed into one joined operand string
(`'SYSTEM STATUS: ' WS-STATUS`). The Java backend treated that as a single identifier and emitted
`System.out.println(systemstatuswsStatus);`, so the generated program did not compile. The Validation
Center reported `Compilation: FAIL` for any program using the form (found on `moderate_sales_report.cbl`).

## Change

* `DisplayStatementNode` / `IRDisplay` gain `operands` (each operand separately, populated only when there
  are two or more) and a `display_operands` property. `operand` still holds the space-joined text, so
  every existing reader is unaffected.
* Parser: `_read_display_operands`. A lone subscripted reference keeps its structural form. A statement
  with `UPON` / `WITH NO ADVANCING` is left exactly as before (not split).
* Backend: `_emit_multi_operand_display` concatenates the operands into one `System.out.println`, applying
  the existing PICTURE-aware formatting to each operand. The expression starts with `"" +` unless the
  first piece is a string literal, so two numeric operands are concatenated, not added.
* Semantic resolver, type checker and business-rule extractor iterate `display_operands`, so an undefined
  name in any position is reported (`SEM003`).

## Diagnostics

| Code | Severity | Trigger |
|------|----------|---------|
| `BE015` | WARNING | A subscripted reference inside a multi-operand `DISPLAY`; the statement is skipped rather than emitted as uncompilable Java. |

## Verification

`tests/backend/test_multi_operand_display.py` (16 tests, including a real `javac` + `java` run when a JDK
is present). Each guarded behaviour was mutation-checked: removing it makes a test fail.

## Remaining gaps

* Subscripted operands inside a multi-operand list (`BE015`, skipped with a warning).
* `DISPLAY ... UPON` / `WITH NO ADVANCING` clauses are still not modelled.
* `ACCEPT` is still reported as unsupported (`SYN100`, task #108), so programs that use it stay
  `INCONCLUSIVE` in the Validation Center rather than `PASS`.
