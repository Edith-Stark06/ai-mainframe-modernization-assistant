# Phase 6 controlled source corpus — provenance & licensing

Every COBOL program used to build the Phase 6 dataset (#118) and the
frozen benchmark (#119) is listed here with its origin and license.

## Corpus policy

* **Only material whose provenance and license are verifiable is used.**
* The repository's own test fixtures are MIT-licensed (see `/LICENSE`,
  © 2026 Edith Stark) and were authored inside this project — they are
  used directly (`provenance: repository_fixture`).
* New programs written specifically for Phase 6 are `provenance:
  synthetic`, MIT-licensed, and live under `data/sources/phase6/`.
* **The Open Mainframe Project COBOL Programming Course was NOT
  ingested.** Its license/provenance could not be verified from this
  build environment, and the task's rule is explicit: *"If the
  repository's license/provenance cannot be verified, leave the material
  out and document why."* The repository's own MIT-licensed fixtures
  already provide a controlled, deterministic corpus sufficient for a
  trustworthy experimental foundation. If that course material is later
  cleared for use, add it here with its verified license before
  ingesting.

## Repository fixtures used (`provenance: repository_fixture`, license: MIT)

| source_id | path | notes |
|---|---|---|
| fx_hello_world | tests/fixtures/hello_world.cbl | trivial DISPLAY + STOP RUN |
| fx_move_display | tests/golden/move_display.cbl | MOVE + DISPLAY; golden Java pair |
| fx_arithmetic | tests/golden/arithmetic.cbl | ADD/SUB/MUL/DIV; golden Java pair |
| fx_if_else | tests/golden/if_else.cbl | IF/ELSE; golden Java pair |
| fx_call | tests/golden/call.cbl | external CALL; golden Java pair |
| fx_perform_until | tests/golden/perform_until.cbl | PERFORM + STOP RUN; golden Java pair |
| fx_combined | tests/golden/combined_program.cbl | PERFORM UNTIL + IF; golden Java pair |
| fx_eligibility | tests/fixtures/phase4/eligibility_rules.cbl | multiple business rules |
| fx_simple_proc | tests/fixtures/phase5/simple_procedural.cbl | several paragraphs |
| fx_complex_proc | tests/fixtures/phase5/complex_procedural.cbl | nested IF, PERFORM UNTIL, deps |
| fx_highly_coupled | tests/fixtures/phase5/highly_coupled.cbl | many CALLs + shared state |
| fx_file_processing | tests/fixtures/phase5/file_processing.cbl | unsupported file I/O |
| fx_unsupported | tests/fixtures/phase5/unsupported_syntax.cbl | COMP-3, GO TO |
| fx_incomplete | tests/fixtures/phase5/incomplete_parsing.cbl | parser stops before EOF |
| fx_acctbatch | workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl | ~500-line batch program |

The golden Java pairs (`tests/golden/*.java`) are used as
`cobol_to_java` labels with `ground_truth_status: executable_verified`
(they compile with `javac` — verified in `tests/golden/` and the Phase 3
review) or `reviewed`.

## Synthetic programs (`provenance: synthetic`, license: MIT)

Written for Phase 6 to give the benchmark controlled difficulty and
adversarial coverage. See `data/sources/phase6/*.cbl`.

| source_id | file | designed for |
|---|---|---|
| syn_status_machine | status_machine.cbl | MEDIUM — status-transition rules |
| syn_misleading_names | misleading_names.cbl | ADVERSARIAL — identifier `WS-FRAUD-SCORE` is just a loop counter |
| syn_misleading_comments | misleading_comments.cbl | ADVERSARIAL — comment claims a discount the code never applies |
| syn_ambiguous_question | ambiguous_question.cbl | ADVERSARIAL — QA question is not answerable from the source |
| syn_limit_check | limit_check.cbl | MEDIUM — numeric limit rule |
