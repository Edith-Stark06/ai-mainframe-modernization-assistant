# Fixed-format COBOL: source-format detection and position-preserving normalization (Stage 30, `mmim-gen-v25`)

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v24` -> `mmim-gen-v25`

## 1. Summary

`FormatDetector` and `SourceNormalizer` existed, were unit-tested, and were documented as pipeline stages, but
nothing called them: `AnalysisService` handed the raw file text straight to `CobolLexer`. A program in punch-card
layout (sequence numbers in columns 1-6, comment lines, identification text in columns 73-80) therefore parsed to
**nothing**: no PROCEDURE DIVISION, no diagnostics, `success=False`. Comment lines in otherwise plain sources produced
false `SYN003` errors.

`AnalysisService.prepare_source` now detects the format and, for fixed format, calls the new
`SourceNormalizer.normalize_preserving_positions`, which **blanks** non-code columns instead of deleting them. No
character moves, so every token, AST node and diagnostic keeps its original line, column and offset. Free format and
formats the detector cannot decide are passed through byte-for-byte.

## 2. Baseline (before any edit)

* Full suite: 4772 passed, 0 failed (the Stage 29 acceptance run on the identical code).
* 45-source corpus: 45/45 `javac`; 26 sources carry one false `SYN003` each (130 syntax diagnostics in total).
* Representative fixed-format inputs, run against a byte-copy of the pre-fix `app/` tree:

| input | result before |
|---|---|
| full card layout (sequence numbers, `*` comments, IDs in 73-80) | `success=False`, **0 diagnostics, no PROCEDURE DIVISION** |
| same, CRLF line endings | identical failure |
| blank sequence area + `*` comment lines | 4 diagnostics (`SYN001`, `SYN003`) |
| `/` and `D` indicator lines | `success=False`, no PROCEDURE DIVISION |
| literal continuation (`-` in column 7) | `LexerError: unterminated string literal` |
| < 5 non-empty lines (detector -> `UNKNOWN`) | `success=False` |
| the same program with the card decoration already blank | `success=True`, 0 diagnostics |

## 3. Root cause

The stages were built and unit-tested in isolation; the wiring step was never done, and the lexer
kept a compensating rule for a layout it never received: `*` in **column 1** is a comment (the lexer's comment
rule assumes the normalizer has already removed six columns). Untouched real input has the `*` in column 7, so it was
lexed as a multiplication sign followed by the comment's words.

## 4. Investigation findings that shaped the fix

1. **`SourceNormalizer.normalize` cannot be wired as is.** It deletes columns 1-6, shifting every column left by 6
   and every offset by the deleted prefix. Every diagnostic would then point at the wrong column. It is pinned by 24
   existing tests, so it was left untouched; a sibling method that blanks instead of deleting was added.
2. **It also always truncates at column 72.** That is right for a punch card and wrong for this corpus: all 45
   sources are detected `FIXED` (blank sequence area, code from column 8), yet **57 code lines in 17 sources run past
   column 72** (longest: 122 characters; 53 have text in both column 72 and column 73). Blind truncation would have
   silently destroyed code in 17 of 45 sources. The margin is therefore honoured only when the file proves it is an
   80-column card image (section 5).
3. **The corpus shape**: 45/45 `FIXED`, 26 with a column-7 `*` comment, none with sequence numbers, `-`, `D` or `/`
   indicators, none with tabs or CRLF.
4. **Diagnostics can map back exactly** because positions are preserved by construction: the AST of a card-layout
   program equals, node for node including every line/column/offset, the AST of its hand-blanked twin (tested).
5. **`>>SOURCE FREE` files are still unparsed** (the lexer has no directive handling). Detected as `FREE`, they are
   passed through unchanged, exactly as before. Out of scope; listed in section 9.

## 5. Behavior

`normalize_preserving_positions(source, FIXED)`, per line:

* Columns 1-6 blanked when they hold only digits/spaces. Any other content means the line is not card-formatted
  and it is left untouched.
* `*` or `/` in column 7: whole line blanked. `D`/`d` in column 7 followed by a blank (or nothing): debug line,
  blanked (IBM default without `WITH DEBUGGING MODE`). A `D` directly followed by text is code starting in column 7
  and is kept.
* `-` (continuation): left untouched; continuation is not supported by this stage.
* Columns 73-80 blanked, **unless** any code line of the file has text beyond column 80 or a word straddling the
  column 72/73 boundary; then the file is treated as wide-margin and nothing is blanked there. The rule fails safe:
  when in doubt it keeps code. All 17 corpus files with overflow lines trip it (checked directly).
* `FREE` -> returned unchanged; `UNKNOWN` -> `NormalizationError` (as for `normalize`).

`AnalysisService.prepare_source` runs the detector and returns the source unchanged unless the verdict is `FIXED`.

## 6. Tests

* `tests/parser/test_normalizer_position_preserving.py` (new, 25): contract, line/length/terminator preservation for
  `\n`/`\r\n`/`\r`, sequence area, margin rules, indicator column, lexer token positions equal original coordinates.
* `tests/analysis/test_fixed_format_analysis.py` (new, 62): card layout parses to the same AST (with positions) as the
  hand-blanked reference; PROCEDURE DIVISION detected; comment/sequence/ID text never becomes a token; `/` and `D`
  handling; column-7 statement not mistaken for debug; diagnostic line/column equal the original card's; free format
  and `UNKNOWN` returned unchanged; wide-margin file not truncated; continuation stays a loud `LexerError`; for
  each of the 45 corpus sources only column-7 comment lines change and lengths are identical.
  On the isolated pre-fix tree: **59 failed / 3 passed** (the 3 pin behavior that must not change).
* `tests/dataset/test_mmim_v2_dataset.py`: `V24` -> `V25` (5 references), 2 assertions that encoded the false
  `SYN003` updated (`t_packed_decimal` diagnostics 11 -> 10, corpus total 130 -> 104; its `SYNTAX_ERROR` risk
  1 occurrence -> none, test renamed `..._disappears`), and 4 new Stage 30 pins.
* Three more assertions elsewhere encoded the same false `SYN003` (each said so in its own comment) and were updated to
  the corrected value: `tests/modernization/risk/test_unresolved_go_to_target.py` (`t_goto_spaghetti` no longer has a
  `SYNTAX_ERROR` risk), `tests/parser/test_level88_condition_reference_fix.py` and
  `tests/backend/test_level88_java_representation.py` (`t_condition_names_88` now has no syntax diagnostic).
  Nothing weakened or deleted.

## 7. Corpus impact (byte-copy of the pre-fix `app/` vs the fixed tree, isolated subprocesses)

For all 45 sources: **AST, IR, CFG, CFG summary, dependencies, business rules, paragraph list and generated Java are
byte-identical; `javac` 45/45 before and after; `success` unchanged.** Changed: `syntax_diagnostics` (26 sources, the 26
false `SYN003` removed, nothing added), and what is derived from them: `coverage` (26), `risks` (26), `strategy` (8).

## 8. Dataset impact and regeneration

Content genuinely changes, so `MMIM_GENERATOR_VERSION_V25` was added and `data/dataset/mmim-v2` regenerated
(`seed=42`, `strict_eligibility=True`; two independent runs byte-identical):

* 86 of 351 examples change: PROGRAM_UNDERSTANDING 26, RISK_CLASSIFICATION 26, MODERNIZATION_STRATEGY 26,
  TRANSFORMATION_PLANNING 8. COBOL_TO_JAVA, DEPENDENCY_REASONING, BUSINESS_RULE_EXTRACTION, VALIDATION_REASONING
  unchanged.
* Corrected ground truth: 20 false `SYNTAX_ERROR` risks removed (160 -> 140 risks); syntax diagnostics 130 -> 104;
  coverage totals; 4 strategies `REHOST` -> `REFACTOR`, 1 `PHASED_MIGRATION` -> `REHOST`, 3 with new evidence.
* Unchanged: 351 examples, 226/71/54 split, `split_manifest.json`, `leakage_report.json`, `validation_report.json`;
  official `validate_dataset` exits 0.
* The derived `data/dataset/mmim-v2/instruction/` export (`build_instruction_dataset`) was regenerated too
  (deterministic).

## 9. Remaining gaps (deliberately not addressed)

* Continuation lines (`-` in column 7) are unsupported: a continued literal fails with `LexerError`.
* Files with fewer than 5 non-empty lines get `UNKNOWN` from the detector and are not normalized.
* `>>SOURCE FREE`/`>>SOURCE FIXED` directives are not consumed by the lexer.
* A genuine card image whose code fills column 72 and whose identification area abuts it is classified wide-margin
  and keeps the identification text as tokens (baseline behavior; never drops code).
* `app/compiler.py` (standalone driver) and other direct `CobolLexer` users are not routed through
  `prepare_source`.
* Tabs, alphanumeric sequence areas, and COPY/REPLACE/JCL are out of scope.
