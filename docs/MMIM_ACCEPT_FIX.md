# `ACCEPT identifier` (console input)

## Purpose

`ACCEPT` was reported as an unsupported statement (task #108, `SYN100`), so a program that read input lost
those statements from the AST, the IR, and the generated Java, and the Validation Center stayed
`INCONCLUSIVE` on coverage. The AST node (`AcceptStatementNode`) and IR instruction (`IRAccept`) already
existed; the parser, semantic passes and backend did not use them.

## Change

* **Parser** — a plain `ACCEPT identifier` is parsed (`_parse_accept`). `ACCEPT` moved from the
  unsupported set to the parsed set, and every other form is still routed to the `SYN100` skip through
  `_is_unsupported_form` (which generalises the existing `COMPUTE ROUNDED/FUNCTION` pre-check to all five
  statement-list loops, so an unsupported `ACCEPT` inside `IF`/`PERFORM` bodies is skipped, not raised).
* **Semantic** — `visit_accept_statement` on the base visitor and the reference resolver, so an undefined
  target is reported (`SEM003`).
* **Backend** — `emit_accept` assigns from a console-read helper chosen by the target's declared Java type:
  `String` → `_cobolAcceptLine()`, `int` → `_cobolAcceptInt()`, `double` → `_cobolAcceptDouble()`. The
  helpers (a `BufferedReader` over `System.in`) are emitted once, and only in a class that contains an
  `ACCEPT`. End of input gives an empty line; non-numeric text into a numeric field gives zero.

## Diagnostics

| Code | Severity | Trigger |
|------|----------|---------|
| `BE016` | WARNING | `ACCEPT` target whose Java type is unknown or not `String`/`int`/`double`; statement skipped. |
| `BE004` | WARNING | `ACCEPT` with an empty target; statement skipped. |

## Verification

`tests/backend/test_accept_statement.py`, including a real `javac` + `java` run with piped stdin. The three
tests that asserted the old "ACCEPT is unsupported" behaviour now assert it for the forms that remain
unsupported (`FROM DATE`), and assert the new behaviour for the plain form. On
`moderate_sales_report.cbl` the statement-coverage failures drop from 4 to 0 and the program, run with piped
input, produces the expected report.

## Follow-ups this exposed in behavioral testing

Once `ACCEPT` no longer forced every test to `INCONCLUSIVE`, the generated behavioral tests actually ran and
11 of 17 failed on `moderate_sales_report.cbl`. None was a translation defect:

* **Preset overwritten.** The harness presets an input field and runs the whole program. A field that the
  program `ACCEPT`s, or assigns earlier in the same paragraph as the tested condition (`COMPUTE X = ...` then
  `IF X > n`), never keeps the preset. Such tests are now kept as non-executable with a stated reason
  (`_downgrade_overwritten_inputs`) instead of reported as failures. Assignments in *other* paragraphs are not
  considered (that depends on control flow the check does not model).
* **`double` fields.** The harness could not preset a `double` field and compared values as strings, so `500`
  never matched `500.0`. It now presets doubles and compares numbers by value.
* **stdin.** The three subprocess runners (`JavaTestRunner`, `JavaExecutor`, the GnuCOBOL executor) now start the
  program with an empty stdin, so a program that reads input can never block on the parent's terminal.

Result on `moderate_sales_report.cbl`: 5 executable tests, 0 failing, the other 12 recorded with a reason.
`tests/behavioral/test_input_injection_soundness.py` covers each of the above.

## Remaining gaps

* `ACCEPT x FROM DATE` / `TIME` / `DAY` / `DAY-OF-WEEK` (system values, not console input) — still `SYN100`.
* `ACCEPT` with a subscripted target or an `ON EXCEPTION` clause — still `SYN100`.
* Input is not truncated or padded to the PICTURE width, and an unparseable number becomes `0` where a
  mainframe would store whatever bytes were typed.
* Behavioral tests cannot yet feed an injected value through stdin, so tests on `ACCEPT`ed fields stay non-executable.
