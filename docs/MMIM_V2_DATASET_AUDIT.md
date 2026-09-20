# MMIM v2 Dataset Quality Audit

`dataset_version = mmim-v2` · `generator_version = mmim-gen-v24` · `prompt_version = mmim-prompt-v2`
Generated from the 45-source expanded training corpus (`docs/MMIM_CORPUS_EXPANSION.md`), via
`app/dataset/mmim_builder.py::MMIMDatasetBuilder(strict_eligibility=True)`.

**Revision note — this is the twenty-third regeneration of `mmim-v2`.** `dataset_version` has stayed
`"mmim-v2"` throughout (same 45-source corpus, same 8-task contract); only `generator_version`
has moved, each time because a *deterministic pipeline* change altered some task's ground truth:

| Generator version | What changed | Where documented |
|---|---|---|
| `mmim-gen-v2` | Original build: 45-source corpus, strict task eligibility | `docs/MMIM_V2_DATASET_AUDIT.md` (this doc, earlier revision) |
| `mmim-gen-v3` | + deterministic `PERFORM UNTIL` loop/accumulator behavioral-test extractor (`app/behavioral/extraction/loops.py`) — `VALIDATION_REASONING` only, 22/45 → 24/45 | `docs/MMIM_VALIDATION_EXTRACTOR_AUDIT.md` |
| `mmim-gen-v4` | + parser/lexer fix: decimal-literal tokenization + compound AND/OR `IF`-condition parsing — every AST/business-rule-derived task, `VALIDATION_REASONING` 24/45 → 29/45 | `docs/MMIM_PARSER_VALIDATION_FIX.md` |
| `mmim-gen-v5` | + parser recovery fix: `COMPUTE`/`EVALUATE` inside `IF`/`ELSE` blocks no longer discard the rest of the paragraph — `VALIDATION_REASONING` 29/45 → 30/45, zero-statement paragraphs corpus-wide 32 → 17 | `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` |
| `mmim-gen-v6` | + decimal-literal condition extraction fix: `parse_condition` now accepts fixed-point decimal literals (`0.00`, `12.50`, ...) in a comparison condition — `VALIDATION_REASONING` only, 30/45 → 34/45 | `docs/MMIM_DECIMAL_CONDITION_FIX.md` |
| `mmim-gen-v7` | + two upstream parser-grammar fixes for level-88 condition names: `data_parser.py` now supports the plural `VALUES lit lit ...` form, and `procedure_parser.py` now permits a bare/`NOT`-prefixed condition-name reference as an `IF` condition — every AST/business-rule-derived task for the single affected source (`t_condition_names_88`: 0 → 8 business rules); `VALIDATION_REASONING` unchanged at 34/45 at the time (`conditions.py` deliberately not touched that cycle) | `docs/MMIM_LEVEL88_CONDITION_AUDIT.md`, `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md` |
| `mmim-gen-v8` | + `conditions.py`/`extractor.py` extended to recognise the `IS-TRUE`/`IS-FALSE` condition operators the `mmim-gen-v7` parser fix introduced, with declared-domain-aware boundary generation sourced from the real DATA DIVISION AST — `VALIDATION_REASONING` only, 34/45 → **35/45** (`t_condition_names_88` newly eligible, 9 real evidence-backed tests) | `docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md` |
| `mmim-gen-v9` | + compound `AND`/`OR` condition extraction: `conditions.py` gained `parse_compound_condition`/`generate_compound_boundary_values`/`evaluate_compound`, composing the existing single-term `parse_condition`; compound evidence is keyed on the real underlying data item and every case is verified by re-evaluation — `VALIDATION_REASONING` only, 35/45 → **36/45** (`t_batch_acct_update` newly eligible, 4 tests); **17 sources** gain tests in total (§ VALIDATION_REASONING), `t_condition_names_88` 9 → 21 | `docs/MMIM_COMPOUND_CONDITION_FIX.md` |
| `mmim-gen-v10` | + business-rule engine now consumes `IfStatementNode.extra_conditions` — the `AND`/`OR` terms of a single `IF` were silently dropped from every rule condition (11 IFs, 8 sources, 5 with `OR`). UPSTREAM change: 18 rule conditions change (rule counts, diagnostics, statement counts unchanged); 39 examples across exactly those 8 sources change (BUSINESS_RULE_EXTRACTION 8, MODERNIZATION_STRATEGY 8, RISK_CLASSIFICATION 7, TRANSFORMATION_PLANNING 8, VALIDATION_REASONING 8); coverage stays 36/45; example counts and splits unchanged | `docs/MMIM_EXTRA_CONDITIONS_FIX.md` |
| `mmim-gen-v11` | + every downstream consumer of `IfStatementNode.extra_conditions`: the IR builder (`IRIf.extra_terms`, omitted from the serialized IR while empty so plain IFs are byte-identical), the Java emitter (`&&`/`\|\|`), the dependency analyzer, the CFG decision label and the legacy `app/analysis/rules/extractor.py` (active: used by the `/analysis` API). Exactly the same 8 sources change (54 examples: COBOL_TO_JAVA, DEPENDENCY_REASONING, PROGRAM_UNDERSTANDING, MODERNIZATION_STRATEGY, RISK_CLASSIFICATION, TRANSFORMATION_PLANNING 8 each, BUSINESS_RULE_EXTRACTION 6 via its embedded dependency list); rule counts, conditions, coverage (36/45), example counts, splits and ground-truth statuses unchanged | `docs/MMIM_EXTRA_CONDITIONS_DOWNSTREAM_FIX.md` |
| `mmim-gen-v12` | + two Java-backend fixes: COBOL's `=` is emitted as Java `==` (it was rejected as unsupported, skipping the header of every `IF`/`PERFORM UNTIL` using it), and an untranslatable header now omits the whole construct instead of emitting its body and closing `}` without the header. Only COBOL_TO_JAVA changes, for exactly 5 sources (`t_batch_acct_update`, `t_daily_trans_report`, `t_fallthrough_flow`, `t_goto_spaghetti`, `t_policy_redefines`); Java brace balance 40 -> 45 of 45; `javac` compile count and every ground-truth status unchanged; example counts, splits and coverage unchanged | `docs/MMIM_JAVA_IF_EMISSION_FIX.md` |
| `mmim-gen-v13` | + `_translate_operand` now recognises COBOL's own `'...'` string-literal delimiter (it previously recognised only Java's `"..."`), emitting it as a Java string literal instead of an undeclared identifier (`'Y'` was `y`, now `"Y"`). Only COBOL_TO_JAVA changes, for exactly 7 sources (`t_batch_acct_update`, `t_daily_trans_report`, `t_fallthrough_flow`, `t_goto_spaghetti`, `t_inventory_extract`, `t_payroll_file_post`, `t_policy_redefines`); 3 newly compile (38 -> 41 of 45, ground truth 3 sources `reference` -> `deterministic`); example counts, splits and coverage unchanged | `docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md` |
| `mmim-gen-v14` | + `ProcedureDivisionParser` gained a dedicated `_skip_read_statement`: `READ`'s `AT END`/`NOT AT END` clauses were not protected from the generic "stop at the first statement-verb token" skip (unlike `EVALUATE`'s `WHEN`), so a nested `MOVE`/`ADD` leaked the clause's remaining words into that statement's own operand text as a corrupted identifier (`MoveStatementNode(target="WS-EOF-FLAG NOT AT END")` -> Java `wsEofFlagnotatend`). Parser-layer fix: touches the AST for exactly the 4 sources with a real `READ` (`t_batch_acct_update`, `t_daily_trans_report`, `t_inventory_extract`, `t_payroll_file_post`); rule counts, VALIDATION_REASONING test counts, `javac` compile count and every ground-truth status unchanged; example counts, splits and coverage unchanged | `docs/MMIM_READ_AT_END_PARSING_FIX.md` |
| `mmim-gen-v15` | + `FlowGenerationVisitor` (CFG/flow generator) now treats paragraph *existence* (from the AST's paragraph list) as independent of whether that paragraph produced any IR instruction: an existing-but-statement-empty paragraph (e.g. a `READ`- or `OPEN`-only one) resolves to a cached `NodeType.PROCESS` anchor node instead of being misclassified the same as a genuinely nonexistent target (`ext_...`, `EXTERNAL`), which was producing a false `UNRESOLVED_PERFORM_TARGET` risk finding. CFG/risk-layer fix: touches CFG- and risk-derived ground truth for exactly **12 sources** (`t_account_eligibility`, `t_batch_acct_update`, `t_billing_engine`, `t_daily_trans_report`, `t_insurance_claim`, `t_inventory_extract`, `t_inventory_reorder`, `t_order_hierarchy`, `t_packed_decimal`, `t_payroll_file_post`, `t_pricing_tier`, `t_transitive_fx`); every false `UNRESOLVED_PERFORM_TARGET` occurrence drops to 0 (node/edge counts unchanged — a pure node-type reclassification); genuinely external `CALL` targets remain `EXTERNAL`; 52 examples change (DEPENDENCY_REASONING 12, MODERNIZATION_STRATEGY 12, PROGRAM_UNDERSTANDING 12, RISK_CLASSIFICATION 12, TRANSFORMATION_PLANNING 4); business-rule counts, VALIDATION_REASONING, COBOL_TO_JAVA, example counts, splits and ground-truth statuses unchanged | `docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md` |
| `mmim-gen-v16` | + `PerformStatementNode`/`IRCall` gained a `thru_target` field, and `ProcedureDivisionParser`'s inline-PERFORM branch now parses an optional `THRU`/`THROUGH` clause: `PERFORM A THRU C` previously captured only `target="A"` (the trailing `THRU C` was discarded by `SYN001` panic-mode recovery, which — for the one real source with no period until its sentence's end — also silently dropped the *following* `MOVE`/`GOBACK` statements). `FlowGenerationVisitor` now resolves a THRU range to the ordered slice of the program's real paragraphs (by physical source position) from the start to the end name inclusive, adding one `PERFORMS` edge per paragraph in the range. Verified directly against the corpus: exactly **1 source** contains a real `PERFORM ... THRU ...` (`t_fallthrough_flow`), and it is the only source whose ground truth changes (8 examples: PROGRAM_UNDERSTANDING, DEPENDENCY_REASONING, RISK_CLASSIFICATION — a new genuine `SHARED_MUTABLE_STATE` finding surfaces, `SYNTAX_ERROR` occurrence_count drops 2→1 — BUSINESS_RULE_EXTRACTION, MODERNIZATION_STRATEGY, TRANSFORMATION_PLANNING, COBOL_TO_JAVA — generated Java text changes, `compiles` stays `True`; VALIDATION_REASONING's `expected_output` is byte-identical, only its embedded raw AST dump differs); rule counts (157), coverage (36/45), compile count (41), example counts, splits and ground-truth statuses unchanged | `docs/MMIM_PERFORM_THRU_FIX.md` |
| `mmim-gen-v17` | + `"GO"` moved from `_UNSUPPORTED_STATEMENT_LEXEMES` to `_STATEMENT_LEXEMES`, and a new `ProcedureDivisionParser._parse_go_to_statement` parses the single-target `GO TO paragraph-name` form (the only form anywhere in the corpus — no `DEPENDING ON`/multi-target usage exists). `GoToStatementNode`, `IRBuilder.build_go_to_statement` -> `IRJump`, `FlowGenerationVisitor.visit_jump`, its `GOES_TO`-edge resolution (reusing the same per-target logic PERFORM already shares), and `RiskAnalyzer._detect_complex_control_flow`'s GO-TO-transfer counting all already existed and were already correctly wired — confirmed unreachable only at the parser boundary; no IR/CFG/risk code changed. Verified directly against the corpus: exactly **1 source** contains real `GO TO` usage (`t_goto_spaghetti`, 7 occurrences, 4 of them nested inside `IF` THEN/ELSE branches and 3 top-level; the earlier "5 of them nested" was a miscount, corrected in Stage 19), and it is the only source whose ground truth changes (7 examples: PROGRAM_UNDERSTANDING, DEPENDENCY_REASONING, RISK_CLASSIFICATION — the `UNSUPPORTED_SYNTAX` risk for this source disappears entirely, and `COMPLEX_CONTROL_FLOW` rises from LOW/3 to MEDIUM/10 as its already-existing GO-TO-transfer counting becomes non-trivial for the first time — BUSINESS_RULE_EXTRACTION, MODERNIZATION_STRATEGY, TRANSFORMATION_PLANNING, COBOL_TO_JAVA — the Java backend's pre-existing `// TODO: translate IRJump` placeholder is emitted for the first time at each GO TO site, `compiles` stays `True`); `t_goto_spaghetti` has no VALIDATION_REASONING example in either version (skipped, `no_derivable_behavioral_tests`, in both — only that skip record's own `parser_status.unsupported_codes` field changes). Rule counts (157), coverage (36/45), compile count (41), example counts, splits and ground-truth statuses unchanged | `docs/MMIM_GO_TO_FIX.md` |
| `mmim-gen-v18` | + the Java backend now translates `IRJump` (`GO TO`). Java has no `goto` and the backend's flat model has no paragraphs, so a program containing a translatable `GO TO` is lowered as a paragraph dispatcher (`while`/`switch` on a paragraph index; every paragraph a `case`, so Java `switch` fall-through is COBOL's sequential fall-through; a jump is a labeled `continue`, emitted as `if (true) { … }` so dead code after it never becomes a javac "unreachable statement" error); a program with no such jump takes the unchanged flat path, byte for byte. `AnalysisService` also passes the AST's paragraph *names* so a `GO TO` to an empty paragraph (invisible in the IR) can be told from a missing one (that one stays a `// TODO` + `BE012`). Only **COBOL_TO_JAVA** changes, for exactly **1 source** — `t_goto_spaghetti`'s `expected_output.java` (7 `// TODO: translate IRJump` → a dispatcher); verified: the other 44 Java texts are hash-identical, `compiles` stays `True` (41/45), status stays `deterministic`, and 351 examples / 226-71-54 splits / leakage / 157 rules are unchanged. Behavior is verified by *executing* the generated Java (real `javac`/`java`) against an independent COBOL-semantics interpreter of the IR, from identical seeded state | `docs/MMIM_GO_TO_FIX.md` §10 |
| `mmim-gen-v19` | + COBOL `VALUE` clauses become Java field initializers. The parser always captured the literal, but it was dropped at symbol creation (`VariableSymbol` had no field for it) and `build_fields_from_symbols` hardcoded `initial_value=None`, so every generated field started at the Java default. `VariableSymbol.value` now carries it and a new `translate_value_literal` renders it per Java type: numbers are re-emitted from their *value* (Java reads a leading `0` as octal — in the real corpus `VALUE 028` and `VALUE 09` would not compile and 9 more, e.g. `VALUE 035`, would silently be wrong), quoted strings are re-escaped, `SPACE(S)` is `""`, and anything without a provably correct Java form (`ZERO` on a `String`, `HIGH-VALUES`, `int` overflow, a kind/type mismatch) keeps no initializer. The architecture builder's field pattern also had to learn an optional initializer, or every initialized field silently vanished from `transformation_planning`'s data model (caught in the first regeneration diff). Only **COBOL_TO_JAVA** changes, for **all 45 sources** — exactly **270** field declarations gain an initializer and *no other line* of any Java text differs; verified: `compiles` unchanged (41 `True` / 4 `False`), TODO and diagnostic counts unchanged, `transformation_planning` and every other task type unchanged, and 351 examples / 226-71-54 splits / leakage / 157 rules / 345-2-4 statuses are unchanged. Behavior is verified by *executing* the generated Java unseeded: `t_goto_spaghetti` now ends `accumulator=30, stepIndex=4, retryCounter=2, terminalState=COMPLETED` (was `accumulator=50`) | `docs/MMIM_VALUE_INITIALIZER_FIX.md` |
| `mmim-gen-v20` | + signed numeric `VALUE` literals parse. The lexer emits `+`/`-` as their own `UNKNOWN` tokens everywhere (deliberately — they are also the arithmetic operators, and `VALUE -1` / `B - C` are pinned that way), and the `VALUE` clause took only the token after `VALUE` as the whole literal: for `VALUE +000450000.00` it took `+`, the digits left behind failed the terminating-period check, and the **entire data item was abandoned** (`SYN005`). A sign sitting directly against a following `NUMBER` on the same line is now joined into one literal in `data_parser.py`'s `VALUE` branch only (a detached `+ 5` is still not accepted, as COBOL requires); the lexer, level-88 parsing and the procedure division are untouched. Exactly **1 source** is affected — `t_packed_decimal` recovers its 5 `COMP-3` items (8 → 13 data items, all 5 `SYN005` gone, syntax diagnostics 16 → 11, AST coverage 13/23 → 18/28), which become Java `double` fields with their COBOL initial values (`450000.00`, `85200.50`, `62100.25`, `0.00`, `0.00`) via the Stage 20 translator. Only that source's **8 examples** change (one per task type); verified: the other 44 sources are fingerprint-identical (AST items, syntax/semantic/backend diagnostics, IR, Java text, `javac`), `javac` stays 41/45, and 351 examples / 226-71-54 splits / leakage / 157 rules / 345-2-4 statuses are unchanged. Executed: the generated Java compiles and holds the values | `docs/MMIM_SIGNED_VALUE_FIX.md` |
| `mmim-gen-v21` | + level-88 condition-names are no longer emitted as Java storage fields, and the 88 `VALUE`/`VALUES` parser accepts more literal forms. A level-88 is a *named condition on its parent data item*: the AST keeps it as `ConditionNameNode` metadata, the behavioral extractor maps it to its parent and reads its `values`, the procedure parser resolves `IF NAME` through `known_condition_names`, and the backend deliberately refuses the `IS-TRUE`/`IS-FALSE` sentinel (`BE007`) — yet `build_fields_from_symbols` declared each one as an uninitialized `private String` nothing ever read or wrote. It now skips level 88 (no diagnostic; the symbol stays registered and the values stay on the AST). Parser: `_read_condition_literal` joins signed (`-1`), leading-decimal (`.5`, `-.5`) and mixed literals when each piece sits directly against the next, and skips the optional `IS`/`ARE` (previously `VALUES IS 1 2` silently captured `IS` as a value and `VALUE IS 1` dropped the entry); `THRU` ranges, comma separators and detached signs stay rejected, and the elementary-item `VALUE` code is untouched. The corpus has exactly 11 level-88 entries (all in `t_condition_names_88`, all plain strings), so the parser part changes no output; only that source is affected — Java fields 19 → 8, and only its **COBOL_TO_JAVA** and **TRANSFORMATION_PLANNING** examples change (data model 19 → 8; the embedded AST of every example is identical). Verified: every other source is fingerprint-identical, `javac` stays 41/45, and 351 examples / 226-71-54 splits / leakage / 157 rules / 345-2-4 statuses are unchanged. Executed: the generated classes compile and hold exactly their storage fields | `docs/MMIM_LEVEL88_VALUE_FIX.md` |
| `mmim-gen-v22` | + COBOL text-comparison semantics and level-88 condition translation in the Java backend. `IF WS-CODE = 'AUTO'` was `wsCode == "AUTO"`: Java `==` on two `String` references compares object identity, so it held only while the field still contained its compile-time literal (both sides one interned constant) and failed for an equal string from anywhere else — executed on the isolated pre-fix tree, a distinct-but-equal `String` made `IF` miss where COBOL hits. `_build_condition` — the only place a Java comparison is produced (`IF`, compound terms, `PERFORM UNTIL`) — had no type information; it now takes an optional context (declared field types + level-88 condition-names). `=`/`!=` between two operands that are *known text* (a quoted literal or a `String` field) is `_cobolEquals(a, b)`: COBOL's space-padded alphanumeric equality (trailing spaces never matter, a never-set field is blank), a small package-private static helper the class carries only when it uses it (package-private so the method-name scanners in behavioral extraction / the Java project generator / the chunker, which read `public`/`private`/`protected` methods as paragraphs, never see it). Numeric, mixed, unknown-typed (FILE SECTION fields) and ordering comparisons are unchanged. The same context lets `IF <condition-name>` / `IF NOT` translate — the parent item (nearest preceding non-88 item) compared with each declared value, from AST metadata the IR never carried, passed by `AnalysisService` like Stage 19's `paragraph_order`; text/number/decimal/signed/multi-value forms translate, anything not provably correct (`ZERO` on a text parent, `HIGH-VALUES`, a kind/type mismatch, an undeclared parent, a compound with an untranslatable term) keeps `BE007`. No IR change. Only 4 text comparisons reach generated Java in the corpus (the rest sit in paragraph bodies skipped after `STOP RUN`), and only **1 source** is affected — `t_policy_redefines`, whose 2 conditions change and whose class gains the helper; no corpus level-88 reference is in reachable code. Only that source's **COBOL_TO_JAVA** example changes; verified: AST, IR, CFG, dependencies, rules, risks, strategy and every diagnostic of all 45 sources identical, `javac` 41/45 unchanged, and 351 examples / 226-71-54 splits / leakage / 157 rules / 345-2-4 statuses unchanged. Executed against an independent COBOL-semantics oracle (text: 11 seeds × 9 comparisons; level-88: 8 seeds × 15 conditions; `PERFORM UNTIL <condition>`; the real source) | `docs/MMIM_STRING_COMPARISON_FIX.md` |
| `mmim-gen-v23` | + the procedure-division parser learned COBOL's own "not equal" relational-operator forms. `relational-operator ::= [NOT] { = | > | < | >= | <= | <> }` — a `NOT` between the two operands negates the operator that follows it (`IF X NOT = 'A'`), and `<>` is COBOL's own not-equal spelling; neither was recognised (the lexer split `<>` into two separate operator tokens, and a mid-condition `NOT` was never consumed), so the whole `IF` was dropped by panic-mode recovery. Both now collapse to the already-supported plain spelling (`NOT =`/`<>` → `<>`, aliased to Java `!=` exactly like `=`→`==`; `NOT >`/`NOT <`/`NOT >=`/`NOT <=` negate to `<=`/`>=`/`<`/`>`) — no IR change, no new backend case. Exactly **4 sources** have a `NOT =` comparison (`t_account_eligibility`, `t_batch_acct_update`, `t_insurance_claim`, `t_payment_gateway` — the same 4 an earlier cycle's gap note already named, docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md §4, §6); their embedded AST/IR/CFG/dependencies/business rules/risks/strategy/syntax diagnostics change to represent the previously-dropped `IF`s (rule total 157 → 167; in `account_eligibility` and `insurance_claim` a `NOT =` deep inside a *nested* IF had silently dropped that whole top-level statement — including every sibling condition in it — via cascading `ParserError` propagation, un-emptying 2 paragraphs previously misclassified as PERFORM targets with no representable statements). Only **1** of the 4 (`t_batch_acct_update` — reachable only because a separate, pre-existing, unrelated parser gap drops its entry paragraph's `GOBACK`) has its generated Java text change at all (one new comparison plus the `_cobolEquals` helper). Verified directly: the other 41 sources are fingerprint-identical, `javac` stays 41/45, and 351 examples / 226-71-54 splits / leakage are unchanged. Executed against an independent oracle (5 seeds × 5 comparison forms; the real `t_batch_acct_update` condition, extracted from its own IR and translated with the real backend, executed across 4 statuses) | `docs/MMIM_NEGATED_COMPARISON_FIX.md` |
| **`mmim-gen-v24`** (current) | + the DATA DIVISION parser learned the FILE SECTION. `FD <file-name>. <record>` now parses with the exact same data-item grammar a WORKING-STORAGE `01` record already uses (previously the whole section was skipped, `SYN101`), so every downstream consumer already generic over any registered symbol — Java field construction, condition-type awareness — needed no FILE-SECTION-specific code at all; only the AST traversal needed to walk the new section. Exactly **4 sources** have a FILE SECTION (`t_batch_acct_update`, `t_daily_trans_report`, `t_inventory_extract`, `t_payroll_file_post` — the same 4 sources every prior cycle back to Stage 12 named as the reason they failed `javac`); their generated Java text changes (FD fields are declared; `t_batch_acct_update`'s and `t_daily_trans_report`'s text comparisons over a previously-unknown-typed FD field now correctly reach Stage 24's `_cobolEquals` too, `t_daily_trans_report` becoming a third helper user), their `SYN101` diagnostic disappears, and their risks/strategy/ground-truth-status change accordingly (`DATA_COMPLEXITY` and one `UNSUPPORTED_SYNTAX` risk both driven directly off it; `t_payroll_file_post`'s `success` flips `False` → `True`). AST/dependency/business-rule *counts* for these 4 are unchanged. Verified directly: the other 41 sources are fingerprint-identical on every dimension that matters (the raw serialized-AST hash moves for all 45, but only because `DataDivisionNode` gained a new `file_section` field that serialises as `null` for a program without one — a schema-shape artifact, not a content change), `javac` moves from 41/45 to **45/45**, and 351 examples / 226-71-54 splits / leakage are unchanged | `docs/MMIM_FILE_SECTION_FIELDS_FIX.md` |

Each prior build is superseded in place (not kept as a separate snapshot directory); the twenty-three
companion documents above are the historical record of exactly what changed at each step and are
not overwritten by this revision. All example counts, task tables, and distributions below are
**current (`mmim-gen-v24`)** values; §"Task-by-task quality assessment" below notes v1→v2 deltas
alongside the v16 numbers where that comparison is informative.

`mmim-v1` (18 sources, 144 examples, `mmim-gen-v1`) is unmodified. This is a parallel version
namespace, not a mutation of v1: `data/dataset/mmim-v1/**` was not written to at any point in
this run (verified below, §6).

---

## 1. Total source count

**45** training sources (`app.dataset.corpus.load_training_corpus()`), all distinct from the 17
`BENCHMARK_SOURCE_IDS` held out for `benchmark-v1`.

## 2. Total example count

**351** `DatasetExample` rows in `data/dataset/mmim-v2/all.jsonl`.

This is below the naive 45 × 8 = 360 ceiling by exactly **9**, all of them
`VALIDATION_REASONING` tasks skipped because the deterministic behavioral-test extractor could
not derive any test case for that source (see §12, §16, and the full root-cause classification
in `docs/MMIM_VALIDATION_EXTRACTOR_AUDIT.md` §2, `docs/MMIM_PARSER_VALIDATION_FIX.md` §7,
`docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §7–8, `docs/MMIM_DECIMAL_CONDITION_FIX.md` §7–8, and
`docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md` §10, and — for the 9 skips that remain after the
compound-condition fix — `docs/MMIM_COMPOUND_CONDITION_FIX.md` §8). No task was skipped for any other
reason on this corpus. Every skip is machine-recorded in `manifest.json["skipped"]` with
`source_id`, `task_type`, `reason`, and a `parser_status` block (`parse_complete`, `ast_present`,
`syntax_diagnostic_count`, `unsupported_codes`).

## 3. Examples per task

| Task | v2 examples | v2 sources covered | v1 examples (18-source baseline) |
|---|---:|---:|---:|
| `program_understanding` | 45 | 45 / 45 | 18 |
| `business_rule_extraction` | 45 | 45 / 45 | 18 |
| `dependency_reasoning` | 45 | 45 / 45 | 18 |
| `risk_classification` | 45 | 45 / 45 | 18 |
| `modernization_strategy` | 45 | 45 / 45 | 18 |
| `transformation_planning` | 45 | 45 / 45 | 18 |
| `cobol_to_java` | 45 | 45 / 45 | 18 |
| `validation_reasoning` | **36** | **36 / 45** | 18 |
| **Total** | **351** | — | **144** |

## 4. Examples per source

Every one of the 45 sources contributes **7 or 8** examples (8 for the 36 sources with a
derivable behavioral-test suite, 7 for the 9 without). No source is silently dropped — this is
enforced by `test_no_source_totally_silently_dropped` in
`tests/dataset/test_mmim_v2_dataset.py`, which checks `manifest["source_ids"]` (sources that
contributed ≥1 example) against the full 45-source corpus.

## 5. Train / validation / test counts

Source-grouped split (`app.dataset.splitting.split_dataset`, seed 42, target 70/15/15):

| Split | Sources | Examples | % of examples |
|---|---:|---:|---:|
| train | 29 / 45 (64.4%) | 226 | 64.4% |
| validation | 9 / 45 (20.0%) | 71 | 20.2% |
| test | 7 / 45 (15.6%) | 54 | 15.4% |

Source→split assignment is unchanged since the very first `mmim-gen-v2` build (a pure function of
`(dataset_version, seed, source_id)`, independent of which tasks a source contributes) — every
newly-covered source's extra `VALIDATION_REASONING` example simply landed in the split its source
already belonged to. Verified directly: `t_batch_acct_update` (the one source this cycle's fix
newly unlocked) was already assigned to `validation` and remains there — the `validation +1`
delta versus `mmim-gen-v8` is exactly and only its one new example; `train`/`test` example
counts are unchanged (226/54). No source moved.

Percentages deviate from the 70/15/15 target because assignment is **source-grouped** (a hash
bucket per `source_id`, never a per-example shuffle) — with only 45 buckets, exact ratios are not
achievable. This is expected and matches the corpus-expansion report's own guidance ("exact
percentages may vary").

## 6. Source-level split verification

**PASS.** `test_splits_are_source_disjoint` confirms `train ∩ validation = train ∩ test =
validation ∩ test = ∅` at the `source_id` level. No source's examples are split across two
partitions.

`data/dataset/mmim-v1/**` was read only (via `test_mmim_v1_directory_untouched` /
`test_mmim_v1_instruction_files_untouched`, which assert `mmim-v1`'s own manifest still reports
`dataset_version=mmim-v1`, `example_count=144`, `source_count=18`) — no v2 code path writes into
that directory.

## 7. Benchmark leakage verification

**PASS**, on all three axes, for both the structured dataset and the instruction dataset:

- **Source ID overlap**: `{45 mmim-v2 source_ids} ∩ {17 BENCHMARK_SOURCE_IDS} = ∅`
- **SHA-256 overlap**: 0 exact source-hash collisions against `benchmark-v1`
- **Normalized-source overlap**: 0 collisions after whitespace normalization

`data/dataset/mmim-v2/instruction/manifest.json["benchmark_leakage"] = {"overlap_count": 0,
"clean": true}`.

## 8. Exact duplicate verification

**PASS.** `test_corpus_has_no_duplicate_or_near_duplicate_sources` hashes all 45 raw sources —
0 exact SHA-256 collision groups within the corpus itself (in addition to the 0 collisions
against the benchmark from §7).

## 9. Normalized duplicate verification

**PASS.** Same test, whitespace-normalized SHA-256 — 0 collision groups.

## 10. Ground-truth status distribution

| `ground_truth_status` | v2 count | Where it occurs |
|---|---:|---|
| `deterministic` | 345 | All tasks except the 2 reviewed golden Java pairs and 7 non-compiling generated Java pairs |
| `executable_verified` | 2 | `cobol_to_java` for `fx_arithmetic`-style reviewed golden fixtures (human-reviewed, `javac`-verified) |
| `reference` | 7 | `cobol_to_java` where the deterministically generated Java did **not** compile with `javac` — explicitly downgraded, never reported as passing |

No example anywhere reports `reviewed` without a human-reviewed source, and no
`executable_verified` example lacks a passing `javac` compilation — enforced by
`test_ground_truth_status_safety` (both v1 and v2 test files).

## 11. Parser completeness distribution

Computed directly from `AnalysisService` / `build_analysis_bundle` over the 45 sources (not
inferred, not fabricated):

- **`parse_complete = True`** (no unsupported statement was silently skipped mid-parse): 38 / 45
- **`parse_complete = False`**: 7 / 45 — `t_batch_acct_update`, `t_daily_trans_report`,
  `t_inventory_extract`, `t_order_hierarchy`, `t_payroll_file_post`, `t_policy_redefines`,
  `t_table_indexed`. AST is still produced for **100% of sources** (`ast_present = True`,
  45 / 45) — the parser recovers and continues past the unsupported construct rather than
  aborting.
- **Diagnostic codes observed across the corpus**: `SYN100` (unsupported statement, e.g. `OPEN`,
  `READ`, `WRITE`, `COMPUTE`, `EVALUATE`) on 19 sources (up from 16 pre-`mmim-gen-v5` — the
  COMPUTE/EVALUATE-inside-IF-block fix, `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md`, correctly
  surfaces `SYN100` for `t_credit_approval`, `t_insurance_claim`, and `t_policy_redefines`, whose
  `COMPUTE`/`EVALUATE` usage was previously invisible — the whole paragraph was silently discarded
  with a vague, differently-coded diagnostic instead — rather than reducing coverage), `SYN101`
  (unsupported `DATA DIVISION` section, i.e. `FILE SECTION`) on 4 sources, `SYN200` (`OCCURS` /
  `REDEFINES` / `COMP` clause present but not represented in the AST) on 4 sources.
- Every `PROGRAM_UNDERSTANDING` example carries `parser_diagnostics: {parse_complete,
  syntax_diagnostic_count, diagnostic_codes}` and `unsupported_constructs` in its
  `expected_output`, and every skip record in the manifest carries the same `parser_status`
  block — this is the explicit, per-example representation of parser limitation the task
  required (no unsupported construct is ever silently converted into fabricated IR or a
  fabricated arithmetic result; the affected statements simply do not appear downstream).

**Decimal-literal limitation** (flagged in the corpus expansion report): **the lexer-level cause
is fixed** as of `mmim-gen-v4` (`docs/MMIM_PARSER_VALIDATION_FIX.md`) — a decimal literal like
`4500.00` now tokenizes as one `NUMBER` token everywhere, DATA DIVISION included, instead of
splitting at the `.`. Re-checked directly against `t_packed_decimal`: its `SYN005` diagnostics
now report the *correctly merged* literal (`got '000450000.00'`, not a stray fragment), but the
diagnostic itself **persists** — a different, still-open `data_parser.py`-level issue (most
originally suspected to be a `COMP-3`/`VALUE` clause-ordering interaction (**diagnosed in Stage 20 and fixed in Stage 21**: it is the sign of `VALUE +000450000.00` — the lexer emits `+` as a separate `UNKNOWN` token and the single-token `VALUE` capture takes it, docs/MMIM_VALUE_INITIALIZER_FIX.md §5); not diagnosed here since it is
outside this parser task's two-item scope) causes the parser to still expect a period where this
now-whole literal sits. `t_packed_decimal`'s overall diagnostic count nonetheless dropped
21 → 16 from other, in-scope improvements. No arithmetic result for the still-affected statements
is fabricated anywhere downstream (the statement is simply absent from IR/business
rules/behavioral tests for that fragment) — the honesty guarantee holds regardless of which
layer the remaining limitation lives in.

## 12. Empty-target counts

Counting only the (source, task) pairs that were **actually emitted** (skips already excluded
by construction):

| Task | Empty/trivial targets | Notes |
|---|---:|---|
| `program_understanding` | 0 / 45 | always structurally populated |
| `business_rule_extraction` | 8 / 45 | `rule_count = 0`; **allowed** — 8 sources genuinely have no detectable conditional business logic (e.g. straight-line arithmetic, `DISPLAY`-only programs, or reachable code with no `IF`/`PERFORM UNTIL`). Not a defect: an empty rule set is the honest answer for those sources. Down from 21/45 three cycles ago — 13 sources' rules were simply unreachable before (§ task-by-task below), most recently `t_condition_names_88` (0 → 8 rules, `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md`). |
| `dependency_reasoning` | 0 / 45 | every source has ≥1 PERFORM/CALL/variable dependency |
| `risk_classification` | 0 / 45 (as `risk_count=0`) | — but see §16: `highest_severity` legitimately reaches `NONE`-equivalent for only 0 sources; all 45 have ≥1 finding |
| `modernization_strategy` | 0 / 45 | `primary` always populated |
| `transformation_planning` | **0 / 45** | every architecture has ≥1 component (§16) — the eligibility gate (`strict_eligibility=True`) would have skipped any source with an empty architecture; none triggered it on this corpus |
| `cobol_to_java` | 0 / 45 | Java is always generated; honesty comes from `compiles` (38 True / 7 False), not from omission |
| `validation_reasoning` | **0 / 36 emitted** (9 skipped instead, see §2) | the gate that used to allow "0 tests" as a normal answer was removed for v2 — enforced by `test_validation_reasoning_never_has_zero_tests`; unchanged by any extractor/parser upgrade — they just changed which sources clear the gate |

## 13. Unique-target counts

| Task | Unique `expected_output` values | / emitted examples |
|---|---:|---:|
| `program_understanding` | 45 | / 45 (every source structurally distinct) |
| `business_rule_extraction` | 38 | / 45 (the 8 empty-rule sources collapse to 1 shared `{business_rules:[],rule_count:0}` value — a legitimate convergence between different simple programs, explicitly exempted from leakage scoring, see §16) |
| `dependency_reasoning` | 45 | / 45 |
| `risk_classification` | 44 | / 45 |
| `modernization_strategy` | 37 | / 45 |
| `transformation_planning` | 45 | / 45 |
| `cobol_to_java` | 45 | / 45 |
| `validation_reasoning` | 36 | / 36 |

## 14. Target collision rates

Cross-split identical-`expected_output` collisions (the only ones that matter for leakage,
since within-split collisions don't inflate eval scores): **5 warnings**, 0 errors, all
pre-filtered by the leakage detector's "trivial expected" exemption logic to exclude the benign
empty-rule/empty-risk convergence in §12–13. All 5 are two *different, unrelated* programs that
happen to receive the same non-trivial deterministic risk/strategy finding (e.g. two distinct
sources both scoring a single `MEDIUM` "undocumented business rule" risk) — inspected
individually, none pairs a train example with its own held-out counterpart.
`leakage_report.json["ok"] = true`, `error_count = 0`.

## 15. Token / character statistics

From `data/dataset/mmim-v2/instruction/manifest.json`:

| Metric | v1 (144 ex.) | v2 (351 ex.) |
|---|---:|---:|
| User tokens (avg / max) | 293 / 389 | 581 / 1056 |
| Assistant tokens (avg / max) | 339 / 2465 | 726 / 14011 |
| Total tokens (avg / max) | 632 / 2801 | 1307 / 15010 |
| Total chars (avg / max) | — | 4962 / 57036 |

**Correction of earlier revisions' "fits inside an 8k context window" claim.** It no longer holds:
4 examples now exceed 8192 estimated tokens, all `VALIDATION_REASONING` (their targets grow with
the number of derivable tests): `t_pricing_tier` 15 010 (32 tests), `t_condition_names_88` 10 592,
`t_credit_approval` 9 625, `t_payroll_deduct` 9 123; 11 examples exceed 4096. The compound-condition
fix (`mmim-gen-v9`) is what pushed these over — each of those sources roughly doubled its test count
(`mmim-gen-v10` moved `t_pricing_tier` from 13 814 to 15 010 and `t_account_eligibility` back under
8192 as two of its rules became non-testable). A fine-tuning run must use a context of at least 16k,
or truncate/drop these four examples deliberately; nothing in the dataset itself is malformed.
User-prompt size grew with v2 because the 27 new sources are larger and more structurally complex
(`docs/MMIM_CORPUS_EXPANSION.md` §B: avg lines/program +106%).

## 16. Difficulty distribution

| Difficulty | v1 | v2 |
|---|---:|---:|
| easy | 8 | 7 |
| medium | 104 | 164 |
| difficult | 32 | 180 |
| adversarial | 0 | 0 |

v2 shifts sharply toward `difficult` (180/351 = 51.3%, vs 32/144 = 22.2% in v1) — expected, since
all 27 new Category A–E sources were purpose-built as `MEDIUM`/`DIFFICULT` (multi-paragraph,
multi-CALL, file-I/O, anti-pattern programs), not `EASY` baselines. The `difficult`/`medium` split
has shifted slightly release-over-release as `VALIDATION_REASONING` coverage grew (each
newly-covered source's difficulty rating determines which bucket its extra example lands in) —
not a change in any source's own declared difficulty.

## 17. Evidence coverage

`source_locations` (the structured, schema-validated evidence channel) is populated for:

- `program_understanding`: 45 / 45 (paragraph-level locations)
- `business_rule_extraction`: 37 / 45 (exactly the sources with ≥1 rule — every rule carries
  exact line evidence; 0 fabricated evidence IDs)
- all other tasks: evidence lives **inline** in `expected_output` instead of the top-level
  `source_locations` field — e.g. each risk item carries its own `evidence` list, each
  dependency edge carries a `source_location`, each architecture component carries
  `source_refs` with `paragraph`/`line_start`/`line_end`. This mirrors mmim-v1's design exactly;
  it is not a v2 regression.

No example anywhere contains a fabricated evidence ID: `source_refs`/`source_locations`/
`evidence` entries are either populated with a real line/paragraph pointer traced back to the
deterministic analyzer, or explicitly `null`/absent (e.g. a `DTO` "state" component has no
single owning paragraph, so its `source_refs[].paragraph` is `null` rather than invented).

---

## Task-by-task quality assessment

For each task: total examples, unique sources, non-empty targets, empty targets, unique targets,
ground-truth breakdown, parser-limited count, and a **READY / AUXILIARY ONLY / NEEDS MORE DATA /
HOLD** call.

### PROGRAM_UNDERSTANDING
- 45 examples, 45 sources, 45 non-empty, 0 empty, 45 unique targets, 45 `deterministic`.
- Parser-limited (source has ≥1 unsupported-construct diagnostic): 19/45 (up from 16 — see §11;
  `t_credit_approval`, `t_insurance_claim`, `t_policy_redefines` now correctly show a `SYN100`
  diagnostic for `COMPUTE`/`EVALUATE` that was previously entirely invisible), all explicitly
  flagged in `unsupported_constructs` and `parser_diagnostics`.
- **READY.**

### BUSINESS_RULE_EXTRACTION
- 45 examples, 45 sources, 37 non-empty, 8 empty (genuine), 38 unique targets, 45
  `deterministic`.
- v1→v2: 39 → 157 total rules extracted (+303%), rule-bearing-source ratio 13/18 (72%) → 37/45
  (82%). Within v2 itself, three successive parser fixes each added meaningfully: decimal-literal +
  compound AND/OR (`mmim-gen-v3` → `mmim-gen-v4`, `docs/MMIM_PARSER_VALIDATION_FIX.md`) added +52
  rules (71 → 123); COMPUTE/EVALUATE-inside-IF-block recovery (`mmim-gen-v4` → `mmim-gen-v5`,
  `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md`) added a further +26 rules (123 → 149) and moved 5 more
  sources from 0 rules to non-trivial counts (`t_batch_acct_update` 0→2, `t_billing_engine` 0→1,
  `t_daily_trans_report` 0→2, `t_payroll_file_post` 0→1, `t_shared_state_hazard` 0→3) plus
  substantial growth in already-nonzero sources (`t_credit_approval` 4→11, `t_tax_withhold` 4→6,
  `t_payroll_deduct` 10→11, `t_transitive_fx` — unchanged at this step); the level-88 condition-name
  parser-grammar fix (`mmim-gen-v6` → `mmim-gen-v7`, `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md`)
  added a further +8 rules (149 → 157), all from a single source moving 0→8
  (`t_condition_names_88`). These were not rule-sparse sources; their rules were simply unreachable
  behind a paragraph the old parser silently abandoned.
- **READY.**

### DEPENDENCY_REASONING
- 45 examples, 45 sources, 45 non-empty, 0 empty, 45 unique targets, 45 `deterministic`.
- Unique external `CALL` targets: 2 (`CHKDIGIT`, `FRAUDCHK`) → 13 (+`BANKAUTH`, `CREDITVAL`,
  `DISCENG1`, `FEECALC`, `FXRATES`, `GEOLOC01`, `RATECALC`, `SCOREENG`, `TAXENG01`, `TOKENGW`,
  `VELOCITY`; unchanged this cycle — `t_condition_names_88`'s new edges are all `CONDITION`/
  `PERFORM`/`VARIABLE_WRITE` type, no new external `CALL`). Dependency-type coverage
  (CONDITION/VARIABLE_READ/VARIABLE_WRITE/PERFORM/CALL) unchanged in kind, +408% in volume overall
  (90 → 457 edges) from the three parser fixes (307 → 385 from the decimal/AND-OR fix, 385 → 447
  from the COMPUTE/EVALUATE-in-IF-block fix, 447 → 457 from this cycle's level-88 fix — all +10 from
  `t_condition_names_88`, whose two previously-empty paragraphs now contribute 6 new `CONDITION`-type
  edges naming the level-88 identifiers themselves).
- **READY.**

### RISK_CLASSIFICATION
- 45 examples, 45 sources, 45 non-empty, 0 empty, 44 unique targets, 45 `deterministic`.
- Severity distribution v1 `{LOW: 12, MEDIUM: 6, HIGH: 0}` → v2 `{LOW: 12, MEDIUM: 12, HIGH: 21}`
  — v1 had **zero** HIGH-severity examples; v2 introduces real HIGH-severity coverage (driven
  honestly by the anti-pattern and file-I/O categories, not manufactured). The
  COMPUTE/EVALUATE-in-IF-block fix (`mmim-gen-v5`) moved 2 sources from MEDIUM to HIGH severity
  (14→12, 19→21). **Unaffected in aggregate by this cycle's level-88 fix** — `t_condition_names_88`
  gained 2 new real findings (`DEEPLY_NESTED_CONDITIONS`, evidence "deepest nest is in paragraph
  1000-VALIDATE-TX-TYPE"; a `SYNTAX_ERROR` finding for its one remaining unrelated diagnostic) but
  its `highest_severity` was already `MEDIUM` before this cycle (a pre-existing risk finding
  already at that level), so the distribution's top-level counts are identical (verified directly,
  not assumed): `{LOW: 12, MEDIUM: 12, HIGH: 21}`, still 45 total.
- Risk category diversity: 5 → 9 categories (adds `SYNTAX_ERROR`, `UNRESOLVED_PERFORM_TARGET`,
  `UNSUPPORTED_SYNTAX`, `DATA_COMPLEXITY`).
- **READY.**

### MODERNIZATION_STRATEGY
- 45 examples, 45 sources, 45 non-empty, 37 unique targets, 45 `deterministic`.
- Distribution: `REHOST 19 (42.2%)`, `REFACTOR 13 (28.9%)`, `PHASED_MIGRATION 7 (15.6%)`,
  `SERVICE_EXTRACTION 3 (6.7%)`, `REWRITE 2 (4.4%)`, `REPLATFORM 1 (2.2%)` — still 6 distinct
  labels (up from 3 in v1: `REFACTOR 12, REHOST 5, REPLATFORM 1`), and REHOST's share continued
  to **drop** across the parser-recovery cycles — 62.2% → 48.9% (decimal/AND-OR fix) → 42.2%
  (COMPUTE/EVALUATE-in-IF-block fix) — as each successive parser fix let the scorer see more real
  control flow. **Unaffected in aggregate by this cycle's level-88 fix** — `t_condition_names_88`
  stayed `REHOST` (verified directly, not assumed); the strategy label distribution is byte-for-byte
  identical to `mmim-gen-v6`. The label distribution was **not** rebalanced; it is reported as
  computed, at every step.
- **READY** — REHOST is still the plurality label, still explainable by the sources that carry
  real `SYN100`/`SYN101` unsupported-construct diagnostics (19/45, up from 16 — §11, unchanged this
  cycle — `t_condition_names_88` never carried a `SYN100`/`SYN101` diagnostic, before or after).
  `t_batch_acct_update` and `t_daily_trans_report` moved from `REHOST` to `PHASED_MIGRATION` two
  cycles ago as their newly-visible business rules gave the scorer real signal
  (`PHASED_MIGRATION` 5 → 7). `t_condition_names_88` — despite gaining 8 real business rules this
  cycle — stayed `REHOST`, its confidence still the low-confidence fallback: a genuine, independent
  defect was found here, not fixed (per this task's scope) — the fallback's rationale text
  unconditionally reads "no procedure logic, no business rules, and no risks to act on" even though
  its own `evidence` array correctly lists "8 business rule(s)"; see
  `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md` §10. A reminder, as with `t_shared_state_hazard`
  before it, that rule count alone does not automatically flip the strategy label — the label is
  reported as computed, not adjusted to match intuition, and this doc does not repeat the
  fallback's own inaccurate rationale text as if it were a verified fact.

### TRANSFORMATION_PLANNING
- 45 examples, 45 sources, 45 non-empty (0 empty architectures — the eligibility gate found
  nothing to skip), 45 unique targets, 45 `deterministic`.
- Component-type totals: `DTO 45, SERVICE 109, DOMAIN 9, INTEGRATION 13, REPOSITORY 0` (`SERVICE`
  109, up from 107, as `t_condition_names_88`'s two now-structured paragraphs contribute 2 more
  real services). Every source gets ≥1 real DTO/service with a source-traced responsibility string
  — **this task's instruction-format target was previously always empty** due to an adapter bug
  (see "Bug fixed" below), now corrected.
- Known limitation, disclosed rather than hidden: the architecture builder **never** emits a
  `REPOSITORY`-type component for any of the 45 sources (0/45), even for the file-I/O and
  multi-CALL categories where a repository abstraction would be architecturally appropriate.
  The `repositories` field in every instruction-format target is therefore `[]` — honestly, not
  fabricated, but a real coverage gap in the underlying architecture builder.
- **READY** for the DTO/SERVICE portion; **AUXILIARY ONLY** for anything relying on the
  `repositories` field, which currently carries no signal.

### COBOL_TO_JAVA
- 45 examples, 45 sources, 45 non-empty, 45 unique targets.
- **Current (`mmim-gen-v14`) ground truth**: 2 `executable_verified`, 41 `deterministic`, 2
  `reference` — unchanged since `mmim-gen-v13`. `mmim-gen-v14`'s `_skip_read_statement` fix
  (`docs/MMIM_READ_AT_END_PARSING_FIX.md`) removed the corrupted `READ ... AT END` identifiers
  (`wsEofFlagnotatend`, `wsEofendRead`, `wsInvEofendRead`, `wsPayEofendRead`) from the same 4
  `reference` sources' Java, but did not change their compile status: all 4 still fail `javac` on
  undeclared FILE SECTION fields alone (the mangled identifiers were never the only cause).
- `mmim-gen-v13`'s fix made `_translate_operand` recognise COBOL's own `'...'` string-literal
  delimiter (`'Y'` was emitted as the undeclared identifier `y`, now as `"Y"`); see
  `docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md`. The remaining 4 `reference` sources
  (`t_batch_acct_update`, `t_daily_trans_report`, `t_inventory_extract`, `t_payroll_file_post`) now
  fail `javac` only on undeclared FILE SECTION fields (documented, not fixed, in that doc's §6).
- Historical note (values below are as of the `mmim-gen-v7` level-88 cycle, kept for the record):
  ground truth was then 2 `executable_verified`, 36 `deterministic`, 7 `reference`. Unchanged
  by that cycle's fix (38/7 compiling split verified directly, identical to `mmim-gen-v6`):
  `t_condition_names_88` already compiled before this cycle (its two paragraphs were empty stubs,
  not compile failures) and still compiles after (now two `// TODO` stubs for a different, also
  pre-existing reason — a flat-paragraph-concatenation backend limitation unrelated to level-88,
  see `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md` §6). The new `IS-TRUE`/`IS-FALSE` condition
  operators reach the Java backend's IR opaquely and hit its existing, pre-built `BE007`
  unsupported-operator diagnostic path if a future source ever reaches that code path directly
  (confirmed safe, not merely assumed — no crash, no fabricated Java).
- **READY.**

### VALIDATION_REASONING
- **36 examples** (down from a theoretical 45), 36 sources, 36 non-empty (0 emitted with
  `test_count = 0` — enforced by `test_validation_reasoning_never_has_zero_tests`), 36 unique
  targets, 36 `deterministic` (see §3).
- **Six successive upgrades (plus one upstream correction, `mmim-gen-v10`, below), all additive, none a rebalancing**:
  (1) `app/behavioral/extraction/loops.py` (`mmim-gen-v3`) added deterministic tests for simple
  `PERFORM UNTIL` loop/accumulator patterns — 22/45 (48.9%) → 24/45 (53.3%), +2 sources
  (`t_interest_accrue`, `t_loan_balance`), documented in `docs/MMIM_VALIDATION_EXTRACTOR_AUDIT.md`.
  (2) Decimal-literal + compound AND/OR `IF`-condition parsing (`mmim-gen-v4`,
  `docs/MMIM_PARSER_VALIDATION_FIX.md`) recovered 5 further sources: `t_account_eligibility`,
  `t_credit_approval`, `t_tax_withhold`, `t_pricing_tier`, `t_payroll_deduct` — 24/45 → 29/45
  (64.4%). (3) `COMPUTE`/`EVALUATE`-inside-`IF`-block parser recovery (`mmim-gen-v5`,
  `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md`) recovered 1 further source, `t_shared_state_hazard` —
  29/45 → 30/45 (66.7%), total derivable tests 118 → 135. (4) Decimal-literal condition
  extraction (`mmim-gen-v6`, `docs/MMIM_DECIMAL_CONDITION_FIX.md`) — `parse_condition` now
  accepts a COBOL fixed-point decimal literal (`0.00`, `12.50`, ...) in a comparison condition,
  where before the whole condition failed to parse — recovered 4 further sources:
  `t_billing_engine`, `t_daily_trans_report`, `t_payroll_file_post`, `t_transitive_fx` —
  30/45 → 34/45 (75.6%), total derivable tests 135 → 152. (5) `IS-TRUE`/`IS-FALSE`
  condition-operator extraction (`mmim-gen-v8`, `docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md`) —
  `parse_condition` now recognises the level-88 condition-name sentinel operators the
  `mmim-gen-v7` parser fix introduced, with boundary values sourced from the condition-name's own
  declared `VALUE`/`VALUES` domain (read off the real DATA DIVISION AST, never fabricated) —
  recovered 1 further source: `t_condition_names_88` — **34/45 → 35/45 (77.8%)**, total
  derivable tests 152 → 161. (6) Compound `AND`/`OR` condition extraction (`mmim-gen-v9`,
  `docs/MMIM_COMPOUND_CONDITION_FIX.md`) — `parse_compound_condition` composes the existing
  `parse_condition` over each parenthesised term (no new grammar; `AND` or `OR`, never mixed),
  and cases are found by verified search over per-variable candidate values, keyed on the real
  underlying data item (a level-88 condition-name is a condition on its parent — in
  `t_condition_names_88` five of them are all `TX-TYPE-CODE`). Recovered 1 further source,
  `t_batch_acct_update` (4 tests; balance `< 500.00` with/without overdraft protection, verified
  against its COBOL) — **35/45 → 36/45 (80.0%)** — and added tests to **16 already-covered
  sources** (17 changed in total; `t_condition_names_88` 9 → 21, `t_pricing_tier` 15 → 29,
  `t_credit_approval` 8 → 20, `t_account_eligibility` 2 → 16, …; full table in the fix doc §5).
  The pre-existing `boundary_partition`/`loop_accumulator` tests from
  steps (1)–(4) are byte-for-byte unchanged by step (5), verified by
  `test_parser_fix_did_not_regress_any_v3_source`,
  `test_compute_evaluate_fix_did_not_regress_any_v4_source`,
  `test_decimal_condition_fix_did_not_regress_any_v5_source`, and
  `test_condition_operator_fix_did_not_regress_any_v7_validation_source`.
- 9 sources remain skipped with `reason: no_derivable_behavioral_tests`, each with its
  `parser_status` recorded. Root-caused precisely, not just measured by diagnostic count:
  `t_inventory_extract` (unsupported `FILE SECTION`/`OPEN`/`READ`);
  `t_order_hierarchy`, `t_table_indexed` (unsupported `OCCURS`); `t_goto_spaghetti` (unsupported
  `GO TO`); `t_inventory_reorder` (variable-vs-variable comparison, out of the behavioral
  extractor's current scope); `fx_perform_until`, `fx_simple_proc`, `t_dead_code_audit`,
  `t_temp_convert` (genuinely no derivable conditional/loop logic in reachable code, unchanged
  since the original audit). `t_condition_names_88` and `t_batch_acct_update` are **no longer in this list** — the
  parser/AST gap, the condition-operator gap and the compound-condition gap that used to block
  them are fixed; all 8 of `t_condition_names_88`'s business rules now yield tests (21 in total).
  **Evidence-quality caveat resolved in `mmim-gen-v10`:** BR-006/BR-007 used to lack the `AND
  TX-WITHDRAWAL` conjunct of the source's `IF PHYSICAL-BRANCH AND TX-WITHDRAWAL` because the
  business-rule engine never consumed `IfStatementNode.extra_conditions`; it does now
  (`docs/MMIM_EXTRA_CONDITIONS_FIX.md`), and their `taken=true` tests assign `TX-TYPE-CODE='W'`
  and reproduce the COBOL. The same fix brings the 5 real `OR` conditions
  (`t_credit_approval`, `t_daily_trans_report`, `t_insurance_claim`, `t_payment_gateway`,
  `t_pricing_tier`) into VALIDATION_REASONING with true/false evidence checked against the COBOL.
  Test counts moved: `t_account_eligibility` 16 → 12, `t_credit_approval` 20 → 17,
  `t_daily_trans_report` 3 → 5, `t_payment_gateway` 4 → 5, `t_pricing_tier` 29 → 32 (the `NOT ((a) AND (b))`
  ELSE conditions of AND-compound IFs are not consumable by the behavioral parser and now yield no
  test rather than a test derived from an incomplete condition).
- **NEEDS MORE DATA** — more precisely, still extractor-capability-limited, not a corpus-size
  problem: every consumer of `IfStatementNode.extra_conditions` is now fixed
  (`mmim-gen-v10`/`v11`); the remaining leverage is extending the behavioral compound parser to
  `NOT ((a) AND (b))` (5 rules) and the separate Java-backend literal-translation gap (below). An
  alternative, unrelated next step is the identical unsupported-statement-in-scope defect fixed
  for `IF`/`ELSE` blocks, still open for `PERFORM UNTIL` body loops (`docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §8;
  `docs/MMIM_DECIMAL_CONDITION_FIX.md` §10).

### Bug fixed during this generation: TRANSFORMATION_PLANNING instruction-format target

`app/dataset/instruction_adapter.py::_build_assistant_response` previously read
`expected.get("dtos", [])` / `"services"` / `"repositories"` — keys that **do not exist** in the
architecture builder's actual output (`app.java_modernization.architecture.builder.build_architecture().to_dict()`
returns `components` tagged with a `type` field, plus a `by_type` count map; there is no
top-level `dtos`/`services`/`repositories` key). Every `transformation_planning` instruction
example — in both v1 and (pre-fix) v2 — was therefore trained on `{"dtos": [], "services": [],
"repositories": []}` regardless of what architecture was actually generated, even though the
underlying `DatasetExample.expected_output` (the structured dataset, not the instruction format)
always had real components. Fixed by deriving `dtos`/`services`/`repositories` from `components`
filtered by `type`. Regression-tested by
`test_transformation_planning_target_reflects_real_architecture` in
`tests/dataset/test_instruction_adapter_v2.py`. `mmim-v1`'s already-generated instruction files
on disk are untouched (not regenerated); this fix only affects fresh generations.

---

## Data quality gates

| Gate | Result |
|---|---|
| No benchmark leakage | **PASS** |
| No split leakage | **PASS** |
| No duplicate sources | **PASS** |
| No fabricated evidence | **PASS** |
| Parser limitations explicitly represented | **PASS** — `parser_diagnostics`, `unsupported_constructs`, and every skip's `parser_status` |
| Task targets semantically meaningful | **PASS**, with the VALIDATION_REASONING coverage caveat above |
| Transformation planning not dominated by empty architecture | **PASS** — 0/45 empty |
| Validation reasoning not dominated by empty tests | **PASS** — 0 emitted with empty tests (9 honestly skipped instead) |
| Strategy labels not pathologically dominated without explanation | **PASS** — REHOST 42% (down from 62% three cycles ago) and explained (parser-limitation correlation, directly confirmed each cycle), 6 distinct labels present |
| Risk labels contain meaningful variation | **PASS** — LOW/MEDIUM/HIGH all present, 9 categories |
| Dependency task contains meaningful CALL/dependency variation | **PASS** — 13 unique CALL targets, 5 dependency types |

All listed gates pass. The dataset is not blocked by leakage, fabrication, or duplication. The
one substantive open item is VALIDATION_REASONING's 80.0% source coverage, which is a scope
limitation (honestly recorded, and actively improved six times now — 49% → 53% → 64% → 67% →
75.6% → 77.8% → 80.0%), not a quality defect. Two disclosed caveats sit alongside it: the
4 examples over 8k tokens (§15) and the two remaining Java-backend gaps (below).

---

## Tests run

```
python -m pytest tests/parser/test_read_at_end_parsing_fix.py -q  # 27 passed (22 fail on the pre-fix tree)
python -m pytest tests/parser -q        # 983 passed, 9 pre-existing failures (identical set to every prior cycle)
python -m pytest tests/analysis -q      # 340 passed
python -m pytest tests/modernization -q # 244 passed
python -m pytest tests/dataset -q       # 205 passed
python -m pytest tests/backend -q       # 693 passed
python -m pytest tests/ir -q            # 381 passed, 3 pre-existing failures (test_ir_control_flow.py, stale `condition=` kwarg)
python -m pytest tests/ -q   # full-tree: 4671 passed, 12 pre-existing unrelated failures
                              # (tests/ir/test_ir_control_flow.py x3, tests/parser/
                              # test_lexer.py x2, test_lexer_regression.py x1,
                              # test_procedure_parser.py "missing period" x4,
                              # test_token_types.py x2 -- identical set to every prior cycle's
                              # documented baseline; none touch READ, CFG/flow, PERFORM THRU, or
                              # GO TO handling)
.venv\Scripts\black.exe --check .                                               # clean
.venv\Scripts\ruff.exe check .                                                  # all checks passed
.venv\Scripts\mypy.exe app                                                      # no issues, 354 files
```

Included: `test_mmim_dataset.py` / `test_instruction_adapter.py` (mmim-v1, unmodified, still
144/144 passing — regression guard that v2 changes did not alter v1 semantics),
`test_mmim_v2_dataset.py` / `test_instruction_adapter_v2.py` (mmim-v2, updated this cycle for
`mmim-gen-v16`, with new §3o tests (only `t_fallthrough_flow`'s embedded CFG gains a THRU-range node,
its RISK_CLASSIFICATION output carries the new genuine `SHARED_MUTABLE_STATE` finding and no
`UNRESOLVED_PERFORM_TARGET`, its COBOL_TO_JAVA `compiles` stays `True`, its VALIDATION_REASONING
`expected_output` is untouched, no other source's expected_output mentions the recovered
`PASS-THRU-STATUS` variable, business-rule/compile counts and example/status totals unchanged; 2
pre-existing pinned assertions on `t_fallthrough_flow`'s generated Java text, from the `mmim-gen-v12`
and `mmim-gen-v13` cycles, were corrected to the new, legitimately-changed Java — see
`docs/MMIM_PERFORM_THRU_FIX.md` §6 for why); earlier, for `mmim-gen-v15`, with new §3n tests (only the
12 empty-paragraph-fix sources' embedded CFG gains an
`empty_` node id, no source's risk evidence retains a false `empty_`-target reference, `t_billing_engine`'s
genuine external `CALL` targets stay `ext_`, business-rule/COBOL_TO_JAVA/VALIDATION_REASONING counts
and example/status totals unchanged); earlier, for `mmim-gen-v14`, with new §3m tests (no mangled
dependency targets or Java identifiers remain, only the 4 READ-bearing sources changed,
business-rule/VALIDATION_REASONING counts and coverage unchanged); earlier, for `mmim-gen-v13`, with new §3l tests (single-quoted literals are Java strings, 3 sources newly
compile, other sources unchanged, counts/coverage unchanged); two earlier cycles' "did not
change" global ground-truth-status/compile-count pins were updated to the new, legitimately
changed totals (345/2/4, 41 compiling), each with a comment pointing at the test that verifies
it; earlier, for `mmim-gen-v12`, with new §3k tests (all 45 generated Java outputs brace-balanced, the five previously
unbalanced sources emit their `=` header, no compile flag or status changed); earlier, for `mmim-gen-v11`, with new §3j tests (`extra_terms` only in the 8 compound-IF sources, plain-IF IR
unchanged elsewhere, dependency ground truth, counts/statuses unchanged); earlier, for `mmim-gen-v10`, with new §3i tests asserting the real `OR`/`AND` conditions in the business-rule
ground truth, BR-006/BR-007, unchanged rule counts and the cn88 fee evidence; earlier §3h tests asserting `t_batch_acct_update`'s VALIDATION_REASONING
eligibility, all six `t_condition_names_88` compound rules, and zero regression on any prior
cycle's coverage; two §3g pins of exact counts were relaxed to membership checks), `test_loop_extraction.py`
(loop/accumulator extractor, unaffected by this cycle),
`test_decimal_and_compound_condition_fix.py` (15 tests, `docs/MMIM_PARSER_VALIDATION_FIX.md` §5),
`test_compute_evaluate_in_if_block_fix.py` (14 tests, `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §5),
`test_decimal_condition_extraction_fix.py` (25 tests, `docs/MMIM_DECIMAL_CONDITION_FIX.md` §5),
`test_level88_condition_reference_fix.py` (19 tests, `docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md`
§5 — one test updated this cycle to stop asserting on `conditions.py`'s now-changed behavior),
`test_extra_conditions_extraction_fix.py` (new — 40 tests, `docs/MMIM_EXTRA_CONDITIONS_FIX.md` §4;
36 of them fail against the pre-fix extractor), `test_intelligence_negative.py` (one test whose
premise — "the parser cannot represent AND on one IF" — was obsolete, updated to the exact
conjunction), `test_compound_condition_extraction_fix.py` (37 tests, `docs/MMIM_COMPOUND_CONDITION_FIX.md`
§9, including the real-corpus `t_condition_names_88` end-to-end regression that re-evaluates all 12
compound cases), `test_level88_condition_operator_fix.py` (24 tests,
`docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md` §5, including the real-corpus
`t_condition_names_88` end-to-end regression with valid evidence on both the true and false
branches), plus the existing `test_schema.py`, `test_security.py`,
`test_validation_split_leakage.py`, `test_benchmark_separation.py`, `test_eol_reproducibility.py`,
`test_extraction.py`, `test_phase10_integration.py`, `test_intelligence_pipeline.py` (one pinned
regression value corrected twice — 6→10→13 business rules on the `complex_acctbatch.cbl` fixture;
unaffected by this cycle, which touches only `t_condition_names_88`),
`test_unsupported_syntax_reporting.py` (diagnostic count corrected 51→44→45, unaffected by this
cycle for the same reason), `test_read_at_end_parsing_fix.py` (27 tests,
`docs/MMIM_READ_AT_END_PARSING_FIX.md` §4, unaffected by this cycle),
`test_empty_paragraph_perform_target_fix.py` (16 tests,
`docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md` §4; 10 of them fail against the isolated pre-fix
tree; 1 updated this cycle for the new THRU behavior — see below),
`test_perform_thru_parsing_fix.py` (new — 8 tests, `docs/MMIM_PERFORM_THRU_FIX.md` §4),
`test_perform_thru_fix.py` (new — 19 tests, `docs/MMIM_PERFORM_THRU_FIX.md` §4; 23 of these 43
THRU-related tests combined fail against the isolated pre-fix tree), `test_java_literal_emission_fix.py`
(1 pre-existing pinned real-corpus literal assertion for `fallthrough_flow.cbl` corrected from
`"SKIPPED-ALPHA"` to `"COMPLETED"` in the prior cycle — found only by the full suite, since this file
lives outside `tests/modernization`/`tests/parser`/`tests/dataset`; see
`docs/MMIM_PERFORM_THRU_FIX.md` §7-8), `test_go_to_parsing_fix.py` (new — 9 tests,
`docs/MMIM_GO_TO_FIX.md` §4), `test_go_to_fix.py` (new — 16 tests, `docs/MMIM_GO_TO_FIX.md` §4; 21 of
these 25 GO-TO-specific tests combined fail against the isolated pre-fix tree),
`test_ir_ast_node_coverage.py` (the "GO TO unreachable from real source" test inverted to "GO TO now
produced from real source"; ACCEPT's own, separate, still-true unreachable status untouched),
`test_analyzer.py` / `test_modernization_phase5.py` / `test_phase5_regression.py` (4 pre-existing
"unsupported statement" examples changed from `GO TO` to `OPEN`, which remains genuinely unsupported —
preserving each test's actual intent; see `docs/MMIM_GO_TO_FIX.md` §8). `test_unresolved_go_to_target.py` (new in Stage 18 — 24 tests, docs/MMIM_GO_TO_FIX.md §9),
`test_java_go_to_translation.py` (new — 28 tests, which compile and *execute* the generated Java against an
independent COBOL-semantics oracle; 21 fail on the isolated pre-fix tree, docs/MMIM_GO_TO_FIX.md §10; the
`GO TO` dataset pins are the new §3q). Stage 20 adds `test_java_value_initializer.py` (new — 78 tests, including
executed-Java checks; 76 fail on the isolated pre-fix tree), the dataset §3r pins (7) and 2 architecture tests. Four
golden `.java` files (5 lines), `test_combined_program_pipeline` (2 lines) and the `add.json` regression fixture (2
lines) were updated because each asserted the old uninitialized declaration for a program that declares a `VALUE`
(docs/MMIM_VALUE_INITIALIZER_FIX.md §3). Stage 21 adds `tests/parser/test_signed_value_literal.py` (new — 31 tests,
including executed-Java checks; 17 fail on the isolated pre-fix tree) and the dataset §3s pins (5; 6 dataset pins fail
pre-fix in total). Stage 20's exact initializer-count pin moved 270 → 275 (the 5 recovered items)
(docs/MMIM_SIGNED_VALUE_FIX.md §6). Stage 22 adds `tests/parser/test_leading_decimal_value_literal.py` (new — 55 tests,
including executed-Java checks; 22 fail on the isolated pre-fix tree, 33 are guards that pass on both) and changes no
dataset file (docs/MMIM_LEADING_DECIMAL_VALUE_FIX.md §7). Stage 23 adds `tests/parser/test_level88_value_literals.py`
(new — 81 tests), `tests/backend/test_level88_java_representation.py` (new — 21 tests, including executed Java) and the
dataset §3t pins (4); 50 tests fail on the isolated pre-fix tree. Four existing pins moved as direct consequences (the
uninitialized-field count 137 → 126 twice, one Stage 20 assertion now checking the 88 field is *absent*, and Stage 22's
"88 `.5` stays dropped" guard narrowed to `PIC .99`) (docs/MMIM_LEVEL88_VALUE_FIX.md §5). Stage 24 adds `tests/backend/test_cobol_comparison_semantics.py` (new — 98 tests, incl.
executed Java against an independent COBOL-semantics oracle; 91 fail on the isolated pre-fix tree, 24 on genuinely wrong behavior of
the unmodified code) and the dataset §3u pins (5); ten existing tests were edited as direct consequences (nine failed, one was re-pointed and kept passing: two
literal-emission pipeline tests, one dataset pin, the Stage 23 comparison assertion and its narrowed parametrization, and two level-88
safety-net tests that now use an 88 which is still untranslatable) (docs/MMIM_STRING_COMPARISON_FIX.md §7). Stage 25 adds `tests/parser/test_negated_comparison_operators.py`
(new — 33 tests) and `tests/backend/test_negated_comparison_java.py` (new — 20 tests, incl. executed Java against an
independent oracle; 32 of the 53 fail on the isolated pre-fix tree) plus the dataset §3v pins (4). Fourteen existing tests were
updated as direct, traceable consequences of legitimately more-complete parsing (exact rule/dependency/coverage counts moved for
the 4 newly-parseable sources, a chosen "malformed grammar" example that no longer is one, the helper now used by 2 sources not 1,
and the empty-paragraph-PERFORM-target source set shrinking from 12 to 10 once 2 previously wholly-dropped nested-IF paragraphs
were recovered) (docs/MMIM_NEGATED_COMPARISON_FIX.md §6). One narrow, fully-documented, 4-value exception was added to a
pre-existing business-rule test for the independent defect in gap (13) above -- never a blanket weakening. No existing test was
weakened
or deleted. Stage 26 adds `tests/parser/test_figurative_constant_operands.py` (new -- 37 tests, all failing to even
collect on the isolated pre-fix tree) and touches no dataset file and no existing test at all -- zero real-corpus impact
(docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md §4-§5). Stage 27 adds `tests/parser/test_file_section_fields.py`
(new -- 22 tests, all failing to even collect on the isolated pre-fix tree); it regenerates the dataset (`mmim-gen-v24`)
and updates 24 assertions in `tests/dataset/test_mmim_v2_dataset.py` plus 6 in `tests/parser`/`tests/backend`, every
one a direct, mechanically-traced consequence of the real Java/diagnostic/risk/ground-truth-status changes the fix
causes for its 4 affected sources (docs/MMIM_FILE_SECTION_FIELDS_FIX.md §7-§8) -- never a blanket weakening.
Stage 28 adds `tests/parser/test_perform_until_unsupported_statement_fix.py` (new -- 10 tests, 9 failing
on the isolated pre-fix tree, the 10th a corpus-survey test correctly unaffected either way) and updates
1 existing test (`test_figurative_constant_operands.py`'s own fixture-diagnostic pin, `SYN005` → `SYN100`
at one line, for this stage's unrelated reason) -- zero real-corpus impact, no dataset file touched
(docs/MMIM_PERFORM_UNTIL_UNSUPPORTED_STATEMENT_FIX.md §4-§5).

---

MMIM V2 STATUS:
READY FOR FURTHER DATA EXPANSION

SOURCES:
45

EXAMPLES:
351

TRAIN:
226

VALIDATION:
71

TEST:
54

BENCHMARK LEAKAGE:
PASS

SPLIT LEAKAGE:
PASS

DUPLICATE SOURCES:
PASS

FABRICATED EVIDENCE:
PASS

TASK STATUS:
PROGRAM_UNDERSTANDING: READY
BUSINESS_RULE_EXTRACTION: READY
DEPENDENCY_REASONING: READY
RISK_CLASSIFICATION: READY
MODERNIZATION_STRATEGY: READY
TRANSFORMATION_PLANNING: READY (DTO/SERVICE); AUXILIARY ONLY (repositories field — always empty, architecture builder never emits REPOSITORY components; see docs/MMIM_VALIDATION_EXTRACTOR_AUDIT.md §6)
COBOL_TO_JAVA: READY
VALIDATION_REASONING: NEEDS MORE DATA (80.0% source coverage — 36/45 — up from 49% six cycles ago via the loop/accumulator extractor, the decimal/AND-OR condition fix, the COMPUTE/EVALUATE-inside-IF-block fix, the decimal-literal condition extraction fix, the IS-TRUE/IS-FALSE condition-operator extraction fix, and this cycle's compound AND/OR condition extraction; still parser/extractor-capability-limited, not corpus-size-limited — see docs/MMIM_PARSER_VALIDATION_FIX.md, docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md, docs/MMIM_DECIMAL_CONDITION_FIX.md, docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md, docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md, and docs/MMIM_COMPOUND_CONDITION_FIX.md)

CRITICAL REMAINING GAPS:
- VALIDATION_REASONING covers 36/45 sources (80.0%). The 9 remaining skips are each root-caused (fix doc §8): `FILE SECTION`/`OPEN`/`READ`, `OCCURS`, a variable-vs-variable comparison, `no_derivable_behavioral_tests` (including `t_goto_spaghetti`, now GO-TO-parseable but still yielding no extractable behavioral condition), and other sources with no derivable conditional/loop logic.
- The Java backend `=`/skipped-header gap, the single-quoted-literal-as-identifier gap, the
  `READ ... AT END`/`NOT AT END` parser-level identifier-mangling gap, the CFG/flow generator's
  existing-but-empty-paragraph `UNRESOLVED_PERFORM_TARGET` overstatement, the
  `PERFORM ... THRU ...` single-target parsing gap, and the `GO TO` parser-level unsupported-statement
  gap reported in the prior six cycles are all **fixed** (`mmim-gen-v12`, `mmim-gen-v13`,
  `mmim-gen-v14`, `mmim-gen-v15`, `mmim-gen-v16`, `mmim-gen-v17`;
  docs/MMIM_JAVA_IF_EMISSION_FIX.md, docs/MMIM_JAVA_LITERAL_EMISSION_FIX.md,
  docs/MMIM_READ_AT_END_PARSING_FIX.md, docs/MMIM_EMPTY_PARAGRAPH_PERFORM_TARGET_FIX.md,
  docs/MMIM_PERFORM_THRU_FIX.md, docs/MMIM_GO_TO_FIX.md).
- **New, independent, unfixed (carried forward):** (1) `==` on a Java `String` is reference
  equality, not value equality (needs field types the IR does not carry for `.equals`); (2) FILE
  SECTION fields are never declared as Java fields (`fdTxVal`, `fdAcctBal`, …) — together (1)-(2)
  are why the same 4 sources still fail `javac`, purely on FILE SECTION fields (the mangled READ
  identifiers are gone); (3) the Java backend's pre-existing "flat paragraph concatenation"
  architecture does not consume `IRCall.thru_target` at all and does not scope a PERFORM'd paragraph's
  statements into its own Java method — for `t_fallthrough_flow`, fixing the THRU/statement-recovery
  gap changes *which* statements this pre-existing limitation happens to include in `run()` (still
  compiles; still not behaviorally correct Java either before or after)
  (docs/MMIM_PERFORM_THRU_FIX.md §7); (4) `GO TO A B C DEPENDING ON X` (multi-target/computed jump)
  remains unimplemented — not present anywhere in the real corpus, proven safe (not silently
  mis-narrowed) rather than assumed (docs/MMIM_GO_TO_FIX.md §3, §7); (5) **resolved in Stage 18, with
  no dataset change** (`mmim-gen-v17` remains current — the real corpus has no missing GO TO target,
  and regenerated output is byte-identical): a `GO TO` to a genuinely nonexistent paragraph
  (`EXTERNAL` node, `GOES_TO` edge) is now surfaced as a dedicated `UNRESOLVED_GO_TO_TARGET` risk, driven
  by the edge type so external `CALL`s are unaffected (docs/MMIM_GO_TO_FIX.md §9); (6) **resolved in Stage 19** (`mmim-gen-v18`): the Java backend's `// TODO: translate IRJump`
  placeholder is replaced by a real paragraph-dispatcher translation, verified by execution
  (docs/MMIM_GO_TO_FIX.md §10); (7) **resolved in Stage 20** (`mmim-gen-v19`): COBOL `VALUE` clauses now become Java field
  initializers (docs/MMIM_VALUE_INITIALIZER_FIX.md); (8) **resolved in Stage 21** (`mmim-gen-v20`): a *signed* `VALUE` literal
  (`VALUE +000450000.00`, `VALUE -5`) is now parsed as one literal, so the 5 `COMP-3` items of `t_packed_decimal` are
  declared and initialized (docs/MMIM_SIGNED_VALUE_FIX.md); (9) **newly found, unfixed** (the level-88 half is **resolved in Stage 23**, `mmim-gen-v21`: condition-names are no
  longer emitted as storage fields, docs/MMIM_LEVEL88_VALUE_FIX.md):
  `IF` on a `String` field emitting `==` (reference comparison) was **resolved in Stage 24** (`mmim-gen-v22`,
  docs/MMIM_STRING_COMPARISON_FIX.md); `MOVE 09 TO X` and `MOVE SPACES TO X` emit `x = 09;`
  / `x = spaces;` (the statement emitter neither normalizes a leading-zero literal nor handles a figurative
  constant); `DataModelElement.initial_value` in the architecture model is still never populated (all reproduced,
  none exercised by the corpus except the 88-levels and the (now-fixed) signed literal — docs/MMIM_VALUE_INITIALIZER_FIX.md §5);
  (10) **newly found in Stage 21:** leading-decimal-point literals — **resolved in Stage 22**, *with no dataset change*
  (`mmim-gen-v20` stays current: the corpus has no such literal, and regenerated output is byte-identical): the
  elementary-item `VALUE` parser now joins `[sign] . digits` when each piece sits directly against the next, so `.50`,
  `-.50` and `+.50` are one literal and no longer drop the item / keep it with the garbage value `'-'`; an un-joined
  sign before a period (`+ .50`) is rejected like every other detached form (docs/MMIM_LEADING_DECIMAL_VALUE_FIX.md).
  Signed / leading-decimal **level-88** values were then **resolved in Stage 23** (`mmim-gen-v21`,
  docs/MMIM_LEVEL88_VALUE_FIX.md). Still unfixed, reproduced, none in the corpus: a leading `.` in procedure operands (`MOVE .5`, `ADD .5`, `IF … > .5`) and in `PIC .99` (explicit
  diagnostics), and signed literals in procedure statements (`MOVE -5 TO X` is parsed as source `'- 5'` → Java
  `x = f5;`) (docs/MMIM_SIGNED_VALUE_FIX.md §7, docs/MMIM_LEADING_DECIMAL_VALUE_FIX.md §8);
  (11) **found in Stage 23:** `IF <condition-name>` untranslatable (`BE007`) — **resolved in Stage 24** (`mmim-gen-v22`) for every
  form that can be translated provably correctly (the rest keep `BE007`); still unsupported, reproduced, none in reachable corpus
  code: `SET <condition-name> TO TRUE` (`SYN100`), level-88 `THRU` ranges and comma-separated value lists
  (docs/MMIM_LEVEL88_VALUE_FIX.md §6); (12) **found in Stage 24:** `IF X NOT = 'A'` / `IF X <> 'A'` not parsed — **resolved in Stage 25** (`mmim-gen-v23`,
  docs/MMIM_NEGATED_COMPARISON_FIX.md); still unfixed, reproduced, none in the corpus: the *leading* `NOT` before an entire
  condition (`IF NOT WS-CODE = 'AUTO'`, as opposed to `IF WS-CODE NOT = 'AUTO'`) for anything but a known level-88 name;
  a subscripted operand (`IF WA-STATUS(WS-IDX) = 'C'`) is rejected outright, with or without `NOT`/`<>`; a figurative-constant
  operand (`IF X NOT = SPACES`) was rejected for 2 of 9 spellings — **resolved in Stage 26, no dataset change** (the comparison
  grammar's operand check only accepted `STRING`/`NUMBER`/`IDENTIFIER` tokens, and only `SPACES`/`ZEROS` lex as `KEYWORD` in
  this lexer's reserved-word table; every other spelling already lexed as `IDENTIFIER` and already parsed —
  docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md); `PERFORM UNTIL <condition-name>` is rejected by the parser (the backend
  supports it, tested with hand-built IR); ordering comparisons on text (`IF X > 'A'`) still emit uncompilable Java `>`; FILE
  SECTION fields were undeclared, so their comparisons kept identity `==` — **resolved in Stage 27** (`mmim-gen-v24`,
  docs/MMIM_FILE_SECTION_FIELDS_FIX.md: `t_batch_acct_update`'s and `t_daily_trans_report`'s comparisons now correctly reach
  `_cobolEquals` too) (docs/MMIM_NEGATED_COMPARISON_FIX.md §8); (13) **newly
  found in Stage 25, unfixed, independent:** `app/modernization/business_rules/extractor.py::_operand_bucket` (Phase 4, long
  predating and unrelated to any comparison-operator work) never splits a multi-token `DISPLAY 'literal' identifier` operand, so
  the whole compound string becomes one business-rule `dependencies` entry that is not an identifier at all — always latent,
  only now exercised because its guarding condition newly parses (docs/MMIM_NEGATED_COMPARISON_FIX.md §7); (14) **newly found in
  Stage 26, unfixed, independent:** `PERFORM VARYING <id> FROM <n> BY <n> UNTIL <condition> ... END-PERFORM` has zero support in
  `procedure_parser.py` — a bare `PERFORM VARYING` misparses `VARYING` as a paragraph-name target, dropping the entire loop body;
  confirmed present in the real corpus (`table_indexed.cbl`, its only `OCCURS`-table-driven paragraph) and the shared workspace
  fixture; the Java backend also has no figurative-constant-to-Java-value translation for *any* spelling (`ZERO`→`zero`,
  `SPACES`→`spaces`, an undeclared-identifier reference), pre-existing and unrelated to Stage 26's parser fix
  (docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md §6, §8); (15) **found across Stages 12-26, unfixed until now:** FILE SECTION
  fields were declared nowhere (parser skipped the whole section, `SYN101`), so every reference to one was an undeclared Java
  identifier — the sole remaining reason `t_batch_acct_update`/`t_daily_trans_report`/`t_inventory_extract`/`t_payroll_file_post`
  failed `javac`. **Resolved in Stage 27** (`mmim-gen-v24`): `FD` records now parse with the same data-item grammar a
  WORKING-STORAGE `01` record already uses, so symbol collection and Java field construction need no FILE-SECTION-specific code
  at all; `javac` moves from 41/45 to **45/45** (docs/MMIM_FILE_SECTION_FIELDS_FIX.md).
- Newly surfaced limitation: the ELSE branch of an AND-compound IF is rendered `NOT ((a) AND (b))`, a nested group the behavioral compound parser does not model, so 5 rules (t_account_eligibility BR-007/BR-008, t_credit_approval BR-004/BR-005, t_mortgage_service BR-004) yield no behavioral test — safely, not fabricated (docs/MMIM_EXTRA_CONDITIONS_FIX.md §3).
- New, independent, unfixed, low impact: `business_rules/extractor.py::_condition_variables` treats the operator word of a `NOT`-wrapped term (`IS-FALSE`) as a variable name in `rule["variables"]`; not consumed by behavioral extraction (docs/MMIM_COMPOUND_CONDITION_FIX.md §6.1).
- 4 instruction examples exceed 8192 estimated tokens (max 15 010, `t_pricing_tier` VALIDATION_REASONING) — a training-context concern, not a data defect (§15).
- A previously-discovered, unrelated, unfixed defect: `app/modernization/strategy/analyzer.py::_fallback`'s rationale text is inconsistent with its own evidence when the fallback path fires for a source with real business rules/risks (says "no business rules... no risks" while its own `evidence` array correctly lists them) -- confirmed not directly responsible for the IS-TRUE/IS-FALSE extraction failure this cycle fixed, so still not fixed, per this cycle's own stop conditions (docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md §6, §10; docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md §10).
- The identical unsupported-statement-in-scope defect fixed for IF/ELSE blocks in `mmim-gen-v5` also existed in `PERFORM UNTIL` body loops (`_parse_perform_statement`) — **resolved in Stage 28, no dataset change** (zero real-corpus impact; the same one-`elif`-branch fix `docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md` §8 predicted, docs/MMIM_PERFORM_UNTIL_UNSUPPORTED_STATEMENT_FIX.md).
- The `_apply_action` ARITH-op branch in `app/behavioral/extraction/extractor.py` still only computes a concrete accumulator result for integer literals; a decimal accumulator step (e.g. `ADD 0.5 TO WS-TOTAL`) leaves the result implicit rather than computing it — calculation semantics, not condition extraction, out of scope every cycle so far (docs/MMIM_DECIMAL_CONDITION_FIX.md §10).
- The `IF <var> NOT = <literal>` negated-equality gap (`t_account_eligibility`, `t_batch_acct_update`, `t_insurance_claim`,
  `t_payment_gateway`), tracked unfixed since docs/MMIM_LEVEL88_CONDITION_REFERENCE_FIX.md §4, §6, is **resolved in Stage 25**
  (`mmim-gen-v23`, docs/MMIM_NEGATED_COMPARISON_FIX.md).
- The architecture builder never emits a REPOSITORY-type component for any of the 45 sources, so TRANSFORMATION_PLANNING's repositories field carries no signal anywhere in the dataset.
- 7/45 sources (16%) still hit already-documented unsupported-syntax parser limitations (OPEN/READ/WRITE/CLOSE, GO TO, OCCURS/REDEFINES not represented in AST) — safely recorded, but downstream IR/business-rule/behavioral-test coverage for those sources is correspondingly incomplete. (FILE SECTION itself is no longer one of these — resolved in Stage 27.)

NEXT STEP:
Extend the behavioral compound parser to nested/mixed connectors so the 5 `NOT ((a) AND (b))` rules become testable, give `PERFORM`/`PERFORM THRU` a behaviorally-correct Java translation (they still lower to an empty stub call with the paragraph body inlined; `GO TO` no longer does — docs/MMIM_PERFORM_THRU_FIX.md §7, docs/MMIM_GO_TO_FIX.md §10), support `COMPUTE` so the recovered `t_packed_decimal` items are computed on and not merely declared (docs/MMIM_SIGNED_VALUE_FIX.md §7), implement `PERFORM VARYING` (found in Stage 26, gap 14 above — its own cycle, and a prerequisite for ever fixing the subscripted-operand comparison gap end-to-end; also blocks `table_indexed.cbl`'s only `OCCURS`-table loop from ever reaching real coverage), teach the Java backend what a figurative constant's *value* is rather than just accepting it as an operand (Stage 26's own newly-found gap, docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md §6), model `OCCURS`/Java arrays so the subscripted-operand comparison gap can finally be attempted end-to-end (docs/MMIM_NEGATED_COMPARISON_FIX.md §8 item 2, docs/MMIM_FIGURATIVE_CONSTANT_OPERAND_FIX.md §7 item 2), or fix the leading-`NOT` comparison gap left open by Stage 25 (docs/MMIM_NEGATED_COMPARISON_FIX.md §8 item 1). Any of these should be scoped and executed as its own task, per the same discipline the prior twenty-seven cycles each followed.
