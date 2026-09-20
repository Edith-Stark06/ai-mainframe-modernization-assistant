# STEP 11 — Level-88 Condition-Name Extraction: Audit (STOP, No Fix Applied)

## Outcome

**STOPPED before implementation, per this task's explicit instruction.** The parser/AST does
**not** preserve sufficient information for level-88 condition-name references to produce
behavioral validation evidence, and the reason is not a gap in
`app/behavioral/extraction/conditions.py` (the module this task was scoped to extend). It is
**two independent COBOL *procedure-division and data-division grammar* gaps**, upstream of
`conditions.py` entirely. Fixing either requires modifying parser grammar, which this task
explicitly forbids ("Do not modify: ... parser grammar") and which matches its own stop
conditions verbatim ("level-88 information is missing from the AST"; "level-88 semantics require
parser changes"). No code was changed. No tests were added. MMIM was not regenerated.

## 1. Audit — read before modifying code

- `data/sources/phase6-v2/condition_names_88.cbl` — the one affected source, read in full (§2).
- `app/parser/syntax/data_parser.py::_parse_condition_name` — how level-88 declarations are
  parsed into AST.
- `app/parser/ast/data_items.py::ConditionNameNode` — the AST representation (`level`, `name`,
  `value: str | None` — a single literal, no support for multiple values or ranges).
- `app/parser/syntax/procedure_parser.py::_parse_simple_condition` /
  `_parse_if_statement` — how `IF` conditions are parsed.
- `app/modernization/business_rules/extractor.py`, `app/behavioral/extraction/conditions.py`,
  `app/behavioral/extraction/extractor.py` — how business rules and behavioral tests are derived
  from the AST (grepped for `ConditionNameNode`/`condition_name`/level-88 handling: **none found
  in either module** — confirmed by `grep -ri "ConditionNameNode\|condition_name\|level.*88"
  app/`, which returns only parser/semantic-layer files, never `app/modernization/` or
  `app/behavioral/`).
- `app/parser/semantic/symbol_collector.py::visit_condition_name` — registers a
  `VariableSymbol` for each condition-name in the semantic symbol table (for reference-resolution
  validation only); this table is never consulted by business-rule or behavioral-test extraction.
- Existing tests: `tests/parser/test_data_parser.py` — covers `_parse_condition_name` for the
  singular `VALUE literal` form and the "no VALUE clause" edge case **only**; grepped for
  `VALUES` (plural) — **zero tests exist for the multi-value form**. `tests/parser/
  test_procedure_parser.py` — grepped for "condition name" / "level 88" / "bare identifier" as an
  IF operand — **zero tests exist**; every existing IF-condition test uses the
  `<var> <op> <literal>` comparison shape.

## 2. The affected source

```cobol
01  TRANSACTION-STATUS-RECORD.
    05  TX-TYPE-CODE        PIC X(1) VALUE 'D'.
        88  TX-DEPOSIT      VALUE 'D'.
        88  TX-WITHDRAWAL   VALUE 'W'.
        88  TX-TRANSFER     VALUE 'T'.
        88  TX-FEE          VALUE 'F'.
        88  TX-VALID-KIND   VALUES 'D' 'W' 'T' 'F'.
    05  TX-STATUS-FLAG      PIC X(1) VALUE 'P'.
        88  TX-PENDING      VALUE 'P'.
        88  TX-APPROVED     VALUE 'A'.
        88  TX-REJECTED     VALUE 'R'.
        88  TX-SETTLED      VALUE 'S'.
    05  CHANNEL-ORIGIN      PIC X(3) VALUE 'ATM'.
        88  ONLINE-CHANNEL  VALUES 'WEB' 'MOB' 'API'.
        88  PHYSICAL-BRANCH VALUES 'BRN' 'ATM'.
    05  TX-AMOUNT           PIC 9(7)V99 VALUE 0002500.00.
...
1000-VALIDATE-TX-TYPE.
    IF NOT TX-VALID-KIND
        MOVE 'REJECT-BAD-KIND' TO OUTCOME-ACTION
        ...
    ELSE
        IF TX-DEPOSIT
            MOVE 'CREDIT-ACCOUNT' TO OUTCOME-ACTION
        ELSE
            ...
        END-IF
    END-IF.

2000-ROUTE-BY-STATUS.
    IF PHYSICAL-BRANCH AND TX-WITHDRAWAL
        IF TX-AMOUNT > 1000.00
            MOVE 5.00 TO FEES-LEVIED
        ELSE
            MOVE 0.00 TO FEES-LEVIED
        END-IF
    END-IF
    IF ONLINE-CHANNEL
        MOVE 0.00 TO FEES-LEVIED
    END-IF.
```

`grep -rl "^\s*88\s" data/sources/phase6-v2/` confirms `condition_names_88.cbl` is the **only**
source in the 45-source corpus that declares any level-88 condition name — this audit's findings
are exhaustive for the current corpus, not a sample.

## 3. Reproduction

Direct parse of the real source (`build_analysis_bundle`):

```
syntax_diagnostics:
  SYN003  line 4   "expected a clause keyword, got '*'"           (unrelated: comment-line artifact)
  SYN005  line 13  "expected '.' to terminate data item, got 'VALUES'"   <- TX-VALID-KIND
  SYN005  line 20  "expected '.' to terminate data item, got 'VALUES'"   <- ONLINE-CHANNEL
  SYN005  line 21  "expected '.' to terminate data item, got 'VALUES'"   <- PHYSICAL-BRANCH
  SYN005  line 34  "expected comparison operator in IF condition"        <- IF NOT TX-VALID-KIND
  SYN005  line 54  "expected comparison operator in IF condition"        <- IF PHYSICAL-BRANCH AND TX-WITHDRAWAL

business_rules: 0   (entire source — zero, not merely "few")

procedure_division paragraphs:
  0000-PROCESS-TRANSACTION  3 statements  (unaffected — no level-88 usage)
  1000-VALIDATE-TX-TYPE     0 statements  (entire paragraph lost to recovery)
  2000-ROUTE-BY-STATUS      0 statements  (entire paragraph lost to recovery)
```

Isolated minimal reproduction, to separate the two independent causes:

**(a) Data-division `VALUES` (plural) gap** — reproduced directly against
`_parse_condition_name`'s grammar: it branches only on
`tok.type is TokenType.KEYWORD and tok.lexeme.upper() == "VALUE"` (singular). `"VALUES"` is not
in the lexer's keyword table at all (`grep -n '"VALUE"' app/parser/lexer/keywords.py` finds only
the singular form) — it lexes as a plain `IDENTIFIER`, so the branch is skipped unconditionally,
`value` stays `None`, and the method immediately calls `_expect_period`, which sees `"VALUES"`
sitting where a period must be and raises. **The whole data-item entry is lost to error recovery
— `TX-VALID-KIND`, `ONLINE-CHANNEL`, and `PHYSICAL-BRANCH` do not appear in the AST at all** (only
8 of the source's 11 level-88 names do — every one declared with singular `VALUE`). Verified
directly by walking `ast["data_division"]["working_storage"]["items"]`: only `TX-DEPOSIT`,
`TX-WITHDRAWAL`, `TX-TRANSFER`, `TX-FEE`, `TX-PENDING`, `TX-APPROVED`, `TX-REJECTED`,
`TX-SETTLED` are present, each with a correct `value`.

**(b) Procedure-division bare-condition-name-in-IF gap** — reproduced with a *minimal, isolated*
fixture using only a condition-name that **does** have complete AST information (ruling out (a)
as the cause):

```cobol
01  TX-TYPE-CODE        PIC X(1) VALUE 'D'.
    88  TX-DEPOSIT      VALUE 'D'.
...
MAIN-PARA.
    IF TX-DEPOSIT
        MOVE 'YES' TO WS-OUT
    END-IF
    DISPLAY WS-OUT
    STOP RUN.
```

Result: `SYN005 "expected comparison operator in IF condition"` at the `IF TX-DEPOSIT` line, and
`MAIN-PARA` parses with **0 statements** — the `MOVE`, the `DISPLAY`, and the `STOP RUN` are all
swallowed by recovery, exactly the same "scan to next period" pattern documented in
`docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md`, but triggered here by a condition-*parse* failure (before
any `IfStatementNode` is even constructed) rather than an unsupported statement verb inside an
already-valid `IF`.

## 4. Root cause — precisely identified, traced end to end

`app/parser/syntax/procedure_parser.py::_parse_simple_condition` (the shared helper for a plain
`IF` condition and each `AND`/`OR`-joined term of a compound one) is:

```python
tok = stream.current()
if (tok.type is not TokenType.IDENTIFIER
        and tok.type is not TokenType.NUMBER
        and tok.type is not TokenType.STRING):
    raise ParserError("expected operand for IF condition", ...)
left = tok.lexeme
stream.advance()

tok = stream.current()
if tok.type.name not in ("OPERATOR_EQ", "OPERATOR_GT", ...) and tok.lexeme not in ("=", ">", ...):
    raise ParserError("expected comparison operator in IF condition", ...)
```

It unconditionally requires `<operand> <comparison-operator> <operand>`. There is **no code path
anywhere in this method, `_parse_if_statement`, or any caller for a bare identifier/condition-name
reference** (`IF TX-DEPOSIT`), a negated one (`IF NOT TX-VALID-KIND`), or one joined by `AND`/`OR`
(`IF PHYSICAL-BRANCH AND TX-WITHDRAWAL`) — every one of these forms hits the second `raise`
above, unconditionally, regardless of whether the referenced condition-name's own declaration
parsed successfully. **No `IfStatementNode` is ever constructed for such an `IF`.**

**Data flow, COBOL source → AST → business rule → `parse_condition()` → behavioral test:**

1. `88 name VALUE literal.` → `ConditionNameNode(name, value)` — correctly built. `88 name VALUES
   lit1 lit2 ...` → parse error in `_parse_condition_name`; **entry never reaches the AST** (root
   cause (a), `data_parser.py`, DATA DIVISION grammar).
2. `IF <condition-name-reference>` (any form: bare, `NOT`-prefixed, `AND`/`OR`-joined) →
   `_parse_simple_condition` raises unconditionally; **no `IfStatementNode` is ever produced, and
   the paragraph's error-recovery consumes every subsequent statement in that paragraph up to the
   next period** (root cause (b), `procedure_parser.py`, PROCEDURE DIVISION grammar — confirmed
   independent of (a) via the minimal `TX-DEPOSIT` repro in §3).
3. `app/modernization/business_rules/extractor.py` walks the AST for `IfStatementNode`s to build
   rules; since none exist for either affected paragraph, **it produces zero business rules for
   this entire source** (confirmed: `len(bundle.business_rules) == 0`, not merely a subset).
4. `app/behavioral/extraction/conditions.py::parse_condition` is a pure function of a business
   rule's `condition` string — it is **never even invoked** for level-88 conditions, because step
   3 never hands it one. **There is nothing in `conditions.py` to extend**: the module correctly
   has no opinion on level-88 semantics because it never receives level-88 data in the first
   place.

This is the honest conclusion the task's own audit-first instruction was designed to surface:
**"Do not assume [the target module] itself is completely [the cause]. Determine whether the
defect is [upstream]."** Here it categorically is — two grammar-level gaps, not an
extraction-level one.

## 5. Why this is not a "smallest fix in conditions.py"

Even setting aside gap (a) (the 3 missing `VALUES`-declared names), gap (b) alone means **every**
level-88 condition-name reference in this corpus — including the 8 that have fully correct AST
declarations — is unreachable by any downstream extraction module, because the `IF` referencing
it never parses into an AST node at all. There is no `condition` string, real or malformed, for
`parse_condition()` to see. Extending `conditions.py` to recognize a level-88-shaped condition
string (e.g. `"TX-DEPOSIT"` or `"NOT TX-VALID-KIND"` or `"PHYSICAL-BRANCH AND TX-WITHDRAWAL"`)
would be building a feature with **zero reachable real-corpus input** — nothing upstream would
ever produce such a string for it to consume, so the change could not be validated against real
data, only against a value fabricated for testing. That directly conflicts with this task's own
requirements ("Do NOT invent values", "no fabricated values", "Do not claim the task is complete
unless the real-corpus `t_condition_names_88` path is actually validated") and its stop condition
("fabricated/insufficient evidence").

## 6. New independent gap found during the audit (not level-88, not fixed, reported separately)

While scanning the full 45-source corpus for the same `"expected comparison operator in IF
condition"` diagnostic (to confirm the level-88 finding's exact blast radius), 4 **unrelated**
sources were found to hit the identical diagnostic message for a **different** cause — COBOL's
`NOT =` negated-equality form, which `_parse_simple_condition` also does not support (it consumes
the left operand, then requires an operator token immediately, but sees `NOT` instead):

```
t_account_eligibility  line 33  IF CITIZENSHIP-STATUS NOT = 'CITIZEN' AND CITIZENSHIP-STATUS NOT = 'RESIDENT'
t_batch_acct_update     line 40  IF WS-FILE-STATUS NOT = '00'
t_insurance_claim       line 48  IF DEDUCTIBLE-PAID NOT = 'Y'
t_payment_gateway       line 36  IF TOK-OUT-STATUS NOT = '00'
```

This is a **separate, unrelated condition-parser defect** (same diagnostic *message*, different
grammar gap, different fix site within the same method) — per this task's stop conditions,
explicitly **not** fixed here and reported instead. It is a plausible next parser task, and,
being non-level-88, may turn out to be a narrower and more tractable grammar extension than
either gap (a) or (b) above.

## 7. What was NOT done, and why

- **No code changed** — `app/behavioral/extraction/conditions.py`,
  `app/parser/syntax/data_parser.py`, and `app/parser/syntax/procedure_parser.py` are all
  untouched by this task. Fixing either root cause requires editing parser grammar
  (`data_parser.py` and/or `procedure_parser.py`), which this task explicitly forbids.
- **No tests added** — the task's required test list (single level-88 condition, AND/OR
  combinations, unknown condition name, etc.) all presuppose a working extraction path to test
  against; none exists to test.
- **No real-corpus before/after** — there is no "after" to compare; the source's condition
  extraction, business-rule count (0), and validation eligibility are unchanged from before this
  task, and remain unchanged after it.
- **No MMIM regeneration, no generator-version bump** — `dataset_version`/`generator_version`
  stay at `mmim-v2` / `MMIM_GENERATOR_VERSION_V6` (unchanged from STEP 10); regenerating would
  produce byte-identical output to the current `data/dataset/mmim-v2/**` since nothing changed
  upstream of it (not run, to avoid unnecessary I/O, but trivially true from the "no code changed"
  fact above).

## 8. Recommended next step

This is now a two-part **parser task** (not a condition-extraction task), to be scoped and
executed separately, per this task's own discipline:

1. `app/parser/syntax/data_parser.py::_parse_condition_name` — add support for
   `VALUES literal literal ...` (and, for completeness, the `VALUE lit1 THRU lit2` range form,
   which the corpus does not currently use but is equally standard COBOL) — extending
   `ConditionNameNode` to carry a list of values rather than a single one. This alone would make
   `TX-VALID-KIND`, `ONLINE-CHANNEL`, and `PHYSICAL-BRANCH` visible in the AST, but would **not**
   by itself make any of `t_condition_names_88`'s business rules extractable, because of gap (b).
2. `app/parser/syntax/procedure_parser.py::_parse_simple_condition` /
   `_parse_if_statement` — add grammar support for a bare condition-name (and negated/AND/OR
   forms) as an `IF` condition operand, most likely by resolving the identifier against the
   symbol table's `ConditionNameNode` registrations (already collected by
   `symbol_collector.py::visit_condition_name`) to determine it denotes a level-88 name rather
   than a comparison target, and constructing an appropriately-shaped condition AST node. This is
   the larger of the two changes and the one actually blocking all 11 condition-name references
   in the source, not just the 3 `VALUES`-declared ones.

Only after both land would `t_condition_names_88` produce any business rules at all — at which
point extending `app/behavioral/extraction/conditions.py::parse_condition` to recognize the
resulting condition shape would become a legitimate, independently scoped follow-up task with
real corpus data to validate against.

A narrower, more tractable next step — not level-88, but discovered during this audit (§6) — is
the `NOT =` negated-equality grammar gap affecting `t_account_eligibility`, `t_batch_acct_update`,
`t_insurance_claim`, and `t_payment_gateway`.
