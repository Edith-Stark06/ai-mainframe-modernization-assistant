"""
Regression tests: level-88 condition-name parser grammar gaps
(docs/MMIM_LEVEL88_CONDITION_AUDIT.md).

Purpose:
    Two independent, upstream parser-grammar gaps prevented level-88
    condition-name references from ever reaching business-rule or
    behavioral-test extraction:

    1. ``app/parser/syntax/data_parser.py::_parse_condition_name`` only
       recognised the singular ``88 name VALUE literal.`` form. The plural
       ``88 name VALUES literal literal ...`` form (used by the real
       source ``t_condition_names_88.cbl`` for ``TX-VALID-KIND``,
       ``ONLINE-CHANNEL``, and ``PHYSICAL-BRANCH``) raised a parse error
       and the condition-name never reached the AST at all.

    2. ``app/parser/syntax/procedure_parser.py::_parse_simple_condition``
       unconditionally required ``<operand> <comparison-operator>
       <operand>`` -- there was no grammar path for a bare condition-name
       reference (``IF TX-DEPOSIT``), a negated one (``IF NOT
       TX-VALID-KIND``), or one joined by ``AND``/``OR`` (``IF
       PHYSICAL-BRANCH AND TX-WITHDRAWAL``), even for condition-names with
       a fully correct AST declaration. No ``IfStatementNode`` was ever
       constructed, and the paragraph's own error recovery discarded
       every statement after the failed ``IF`` up to the next period.

Fixed by:
    - ``ConditionNameNode`` gained a ``values: tuple[str, ...]`` field
      (``value: str | None`` kept, unchanged, for the singular form) and
      ``_parse_condition_name`` now recognises ``VALUES`` by lexeme (via
      the existing ``matches_grammar_word`` helper -- ``VALUES`` is not a
      lexer keyword) and collects one-or-more literals.
    - ``ParserState`` gained ``known_condition_names``, populated by
      ``ProgramParser`` from the already-parsed DATA DIVISION AST before
      the PROCEDURE DIVISION is parsed. ``ProcedureDivisionParser`` gained
      ``_parse_condition_term``, which recognises a bare or
      ``NOT``-prefixed reference to a *known* condition-name (never an
      arbitrary undeclared identifier) and represents it as a
      ``(name, "IS-TRUE"|"IS-FALSE", name)`` triple -- reusing the
      existing three-string ``ConditionTerm``/``IfStatementNode`` shape
      with no new AST fields -- before falling back to the unchanged
      ordinary-comparison grammar.

Non-responsibilities:
    - ``app/behavioral/extraction/conditions.py`` was not modified by
      *this* fix and did not recognise the ``IS-TRUE``/``IS-FALSE``
      operators at the time this file was written -- extending it was a
      separate, then-out-of-scope follow-up task, since completed (see
      ``docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md`` and
      ``tests/behavioral/test_level88_condition_operator_fix.py``). This
      file's tests pin facts about the parser/AST/business-rule layer
      only, and do not assert on ``conditions.py``'s current behavior.
    - The unrelated ``IF <var> NOT = <literal>`` negated-equality gap
      (affects ``t_account_eligibility``, ``t_batch_acct_update``,
      ``t_insurance_claim``, ``t_payment_gateway``) is not touched.
    - The ``PERFORM UNTIL`` unsupported-statement recovery gap is not
      touched.
    - ``VALUE ... THRU ...`` range condition-names remain unsupported
      (explicit diagnostic, not silently misparsed) -- no corpus source
      uses this form.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.analysis.service import AnalysisService
from app.dataset.analysis_bundle import build_analysis_bundle

REAL_SOURCE = Path("data/sources/phase6-v2/condition_names_88.cbl")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _analyze(source: str, tmp_path, name: str = "probe.cbl"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(str(path))


def _paragraph_statement_counts(result) -> dict[str, int]:
    pd = result.ast.procedure_division
    return {p.name: len(p.statements) for p in pd.paragraphs}


def _find_paragraph(result, name: str):
    for p in result.ast.procedure_division.paragraphs:
        if p.name == name:
            return p
    raise AssertionError(f"no such paragraph: {name}")


_DATA_HEADER = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T1.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  TX-TYPE-CODE        PIC X(1) VALUE 'D'.
           88  TX-DEPOSIT      VALUE 'D'.
           88  TX-WITHDRAWAL   VALUE 'W'.
           88  TX-VALID-KIND   VALUES 'D' 'W'.
       01  WS-OUT               PIC X(10) VALUE SPACES.
       01  WS-AMOUNT            PIC 9(5) VALUE 100.
"""


def _prog(procedure_body: str) -> str:
    return _DATA_HEADER + "       PROCEDURE DIVISION.\n" + procedure_body


# ---------------------------------------------------------------------------
# 1. Reproduction, minimal -- proves the parser loses structure before the
#    fix and recovers it after (recorded here as the "after" state; the
#    audit doc documents the "before" reproduction that motivated this fix)
# ---------------------------------------------------------------------------


def test_bare_condition_name_if_produces_ifstatement(tmp_path):
    src = _prog("""       MAIN-PARA.
           IF TX-DEPOSIT
               MOVE 'YES' TO WS-OUT
           END-IF
           DISPLAY WS-OUT
           STOP RUN.
""")
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == []
    para = _find_paragraph(result, "MAIN-PARA")
    assert [s.__class__.__name__ for s in para.statements] == [
        "IfStatementNode",
        "DisplayStatementNode",
        "StopRunStatementNode",
    ]
    if_stmt = para.statements[0]
    assert if_stmt.condition_left == "TX-DEPOSIT"
    assert if_stmt.condition_operator == "IS-TRUE"
    assert if_stmt.condition_right == "TX-DEPOSIT"
    assert len(if_stmt.then_statements) == 1


# ---------------------------------------------------------------------------
# 2. NOT applied to a condition-name reference
# ---------------------------------------------------------------------------


def test_not_condition_name_if_produces_ifstatement(tmp_path):
    src = _prog("""       MAIN-PARA.
           IF NOT TX-VALID-KIND
               MOVE 'BAD' TO WS-OUT
           ELSE
               MOVE 'OK' TO WS-OUT
           END-IF
           DISPLAY WS-OUT
           STOP RUN.
""")
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == []
    para = _find_paragraph(result, "MAIN-PARA")
    if_stmt = para.statements[0]
    assert if_stmt.condition_left == "TX-VALID-KIND"
    assert if_stmt.condition_operator == "IS-FALSE"
    assert if_stmt.condition_right == "TX-VALID-KIND"
    assert len(if_stmt.then_statements) == 1
    assert len(if_stmt.else_statements) == 1
    assert [s.__class__.__name__ for s in para.statements] == [
        "IfStatementNode",
        "DisplayStatementNode",
        "StopRunStatementNode",
    ]


def test_not_of_an_undeclared_identifier_is_not_treated_as_condition_name(tmp_path):
    """`NOT` only ever admits a *known* condition-name -- an arbitrary
    undeclared identifier after NOT is not silently accepted; it still
    hits the original diagnostic. (The `NOT <var> = <literal>` negated-
    equality shape is a separate, unrelated, deliberately unfixed gap --
    this is not that; UNDECLARED-THING here has no comparison operator
    at all, so it would fail regardless of which gap it resembled.)"""
    src = _prog("""       MAIN-PARA.
           IF NOT UNDECLARED-THING
               MOVE 'X' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
""")
    result = _analyze(src, tmp_path)
    assert any(
        "comparison operator" in d.message or "operand" in d.message
        for d in result.syntax_diagnostics
    )


# ---------------------------------------------------------------------------
# 3. AND / OR combinations involving condition-name references
# ---------------------------------------------------------------------------


def test_condition_name_and_condition_name(tmp_path):
    src = _prog("""       MAIN-PARA.
           IF TX-DEPOSIT AND TX-VALID-KIND
               MOVE 'BOTH' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
""")
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == []
    para = _find_paragraph(result, "MAIN-PARA")
    if_stmt = para.statements[0]
    assert if_stmt.condition_left == "TX-DEPOSIT"
    assert if_stmt.condition_operator == "IS-TRUE"
    assert len(if_stmt.extra_conditions) == 1
    extra = if_stmt.extra_conditions[0]
    assert extra.connector == "AND"
    assert extra.left == "TX-VALID-KIND"
    assert extra.operator == "IS-TRUE"
    assert extra.right == "TX-VALID-KIND"
    assert [s.__class__.__name__ for s in para.statements] == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]


def test_condition_name_or_condition_name(tmp_path):
    src = _prog("""       MAIN-PARA.
           IF TX-DEPOSIT OR TX-WITHDRAWAL
               MOVE 'EITHER' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
""")
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == []
    para = _find_paragraph(result, "MAIN-PARA")
    if_stmt = para.statements[0]
    assert len(if_stmt.extra_conditions) == 1
    extra = if_stmt.extra_conditions[0]
    assert extra.connector == "OR"
    assert extra.left == "TX-WITHDRAWAL"
    assert extra.operator == "IS-TRUE"


def test_condition_name_combined_with_ordinary_comparison(tmp_path):
    """`IF <condition-name> AND <ordinary comparison>` -- the exact shape
    (modulo names) of the real corpus's
    `IF PHYSICAL-BRANCH AND TX-WITHDRAWAL` followed by a nested
    `IF TX-AMOUNT > 1000.00`, flattened to one compound condition here to
    exercise _parse_condition_term and _parse_simple_condition dispatching
    within the same IF."""
    src = _prog("""       MAIN-PARA.
           IF TX-DEPOSIT AND WS-AMOUNT > 50
               MOVE 'HIGH' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
""")
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == []
    para = _find_paragraph(result, "MAIN-PARA")
    if_stmt = para.statements[0]
    assert if_stmt.condition_left == "TX-DEPOSIT"
    assert if_stmt.condition_operator == "IS-TRUE"
    extra = if_stmt.extra_conditions[0]
    assert extra.left == "WS-AMOUNT"
    assert extra.operator == ">"
    assert extra.right == "50"


# ---------------------------------------------------------------------------
# 4. Unknown identifiers are never treated as condition-names
# ---------------------------------------------------------------------------


def test_undeclared_identifier_in_if_still_diagnosed(tmp_path):
    """An identifier the DATA DIVISION never declared as level-88 is not
    guessed at -- it still hits the original diagnostic, exactly as
    before this fix. Proves the fix is gated on real declared evidence,
    not "any bare identifier that lacks an operator"."""
    src = _prog("""       MAIN-PARA.
           IF NOT-A-REAL-CONDITION-NAME
               MOVE 'X' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
""")
    result = _analyze(src, tmp_path)
    assert any("comparison operator" in d.message for d in result.syntax_diagnostics)


def test_existing_integer_comparison_regression_unaffected(tmp_path):
    src = _prog("""       MAIN-PARA.
           IF WS-AMOUNT > 50
               MOVE 'HIGH' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
""")
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == []
    para = _find_paragraph(result, "MAIN-PARA")
    if_stmt = para.statements[0]
    assert (
        if_stmt.condition_left,
        if_stmt.condition_operator,
        if_stmt.condition_right,
    ) == (
        "WS-AMOUNT",
        ">",
        "50",
    )


def test_existing_compound_and_or_comparison_regression_unaffected(tmp_path):
    """Ordinary (non-condition-name) compound AND/OR conditions --
    already fixed in an earlier cycle -- are unaffected by routing through
    the new _parse_condition_term dispatcher."""
    src = _prog("""       MAIN-PARA.
           IF WS-AMOUNT > 50 AND WS-AMOUNT < 200
               MOVE 'MID' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
""")
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == []
    para = _find_paragraph(result, "MAIN-PARA")
    if_stmt = para.statements[0]
    assert if_stmt.condition_operator == ">"
    assert if_stmt.extra_conditions[0].operator == "<"


def test_malformed_if_condition_still_diagnosed(tmp_path):
    """An outright malformed IF (bare EOF where a condition should be)
    must still fail -- this fix does not make genuinely broken syntax
    parse."""
    src = (
        _DATA_HEADER + "       PROCEDURE DIVISION.\n       MAIN-PARA.\n           IF\n"
    )
    result = _analyze(src, tmp_path)
    assert any(
        "expected operand for IF condition" in d.message
        for d in result.syntax_diagnostics
    )


# ---------------------------------------------------------------------------
# 5. Critical error-recovery requirement: statements after a condition-name
#    IF survive parsing, in the same paragraph and in a later one.
# ---------------------------------------------------------------------------


def test_statements_after_condition_name_if_survive_in_same_paragraph(tmp_path):
    src = _prog("""       MAIN-PARA.
           IF TX-DEPOSIT
               MOVE 'YES' TO WS-OUT
           END-IF
           DISPLAY WS-OUT
           MOVE 999 TO WS-AMOUNT
           DISPLAY WS-AMOUNT.
""")
    result = _analyze(src, tmp_path)
    para = _find_paragraph(result, "MAIN-PARA")
    assert [s.__class__.__name__ for s in para.statements] == [
        "IfStatementNode",
        "DisplayStatementNode",
        "MoveStatementNode",
        "DisplayStatementNode",
    ]


def test_statements_in_later_paragraph_survive_condition_name_if(tmp_path):
    """Before this fix, a failed condition-name IF's error recovery
    consumed everything up to the paragraph's own closing period -- never
    a later paragraph. This pins that the failure mode this fix targets
    was contained (and now eliminated) at the single-paragraph level, not
    a whole-program-losing one -- and confirms the later paragraph is
    unaffected either way."""
    src = _prog("""       MAIN-PARA.
           IF TX-DEPOSIT
               MOVE 'YES' TO WS-OUT
           END-IF
           DISPLAY WS-OUT.
       NEXT-PARA.
           DISPLAY 'REACHED'
           STOP RUN.
""")
    result = _analyze(src, tmp_path)
    counts = _paragraph_statement_counts(result)
    assert counts == {"MAIN-PARA": 2, "NEXT-PARA": 2}
    assert [d.code for d in result.syntax_diagnostics] == []


# ---------------------------------------------------------------------------
# 6. Downstream business-rule extraction receives real level-88-derived
#    conditions (not fabricated -- read straight from the AST this fix
#    produces).
# ---------------------------------------------------------------------------


def test_business_rule_extraction_sees_condition_name_rule(tmp_path):
    src = _prog("""       MAIN-PARA.
           IF TX-DEPOSIT
               MOVE 'CREDIT' TO WS-OUT
           END-IF.
""")
    bundle = build_analysis_bundle("T-CONDNAME", src, str(tmp_path))
    rules = bundle.business_rules or []
    assert len(rules) == 1
    rule = rules[0]
    assert rule["condition"] == "TX-DEPOSIT IS-TRUE TX-DEPOSIT"
    assert "TX-DEPOSIT" in rule["variables"]["conditions"]
    assert rule["actions"][0]["target"] == "WS-OUT"


# ---------------------------------------------------------------------------
# 7. Real-corpus regression: t_condition_names_88.cbl
# ---------------------------------------------------------------------------


def _real_source() -> str:
    return REAL_SOURCE.read_text(encoding="utf-8")


def test_real_corpus_all_eleven_condition_names_reach_the_ast():
    """Root cause 1's fix: every level-88 name in the real source --
    singular VALUE and plural VALUES alike -- is now present in the AST,
    where before this fix TX-VALID-KIND, ONLINE-CHANNEL, and
    PHYSICAL-BRANCH (the three VALUES-declared ones) were silently
    absent."""
    bundle = build_analysis_bundle(
        "t_condition_names_88", _real_source(), tempfile.mkdtemp()
    )
    ast = bundle.ast or {}
    ws = (ast.get("data_division") or {}).get("working_storage") or {}
    names = {
        item["name"]: item for item in ws.get("items", []) if item.get("level") == 88
    }
    assert set(names) == {
        "TX-DEPOSIT",
        "TX-WITHDRAWAL",
        "TX-TRANSFER",
        "TX-FEE",
        "TX-VALID-KIND",
        "TX-PENDING",
        "TX-APPROVED",
        "TX-REJECTED",
        "TX-SETTLED",
        "ONLINE-CHANNEL",
        "PHYSICAL-BRANCH",
    }
    # singular-VALUE items: unchanged shape
    assert names["TX-DEPOSIT"]["value"] == "'D'"
    assert names["TX-DEPOSIT"]["values"] == ["'D'"]
    # plural-VALUES items: the new capability
    assert names["TX-VALID-KIND"]["value"] is None
    assert names["TX-VALID-KIND"]["values"] == ["'D'", "'W'", "'T'", "'F'"]
    assert names["ONLINE-CHANNEL"]["values"] == ["'WEB'", "'MOB'", "'API'"]
    assert names["PHYSICAL-BRANCH"]["values"] == ["'BRN'", "'ATM'"]


def test_real_corpus_both_previously_lost_paragraphs_now_have_statements():
    """Root cause 2's fix: `1000-VALIDATE-TX-TYPE` and
    `2000-ROUTE-BY-STATUS` -- both entirely empty (0 statements) before
    this fix because their leading IF referenced a bare condition-name --
    now contain real, parsed statements."""
    bundle = build_analysis_bundle(
        "t_condition_names_88", _real_source(), tempfile.mkdtemp()
    )
    ast = bundle.ast or {}
    paragraphs = (ast.get("procedure_division") or {}).get("paragraphs") or []
    counts = {p["name"]: len(p.get("statements", [])) for p in paragraphs}
    assert counts["1000-VALIDATE-TX-TYPE"] > 0
    assert counts["2000-ROUTE-BY-STATUS"] > 0
    # exact, not just non-zero: each is a single top-level IF (the nested
    # IF/ELSE cascade lives inside its then/else branches, same
    # representation nested IFs have always used)
    assert counts["1000-VALIDATE-TX-TYPE"] == 1
    assert counts["2000-ROUTE-BY-STATUS"] == 2


def test_real_corpus_route_by_status_condition_is_physical_branch_and_withdrawal():
    """The exact condition text from the task's own example --
    `IF PHYSICAL-BRANCH AND TX-WITHDRAWAL` -- reaches the AST intact."""
    bundle = build_analysis_bundle(
        "t_condition_names_88", _real_source(), tempfile.mkdtemp()
    )
    ast = bundle.ast or {}
    paragraphs = (ast.get("procedure_division") or {}).get("paragraphs") or []
    route = next(p for p in paragraphs if p["name"] == "2000-ROUTE-BY-STATUS")
    first_if = route["statements"][0]
    assert first_if["condition_left"] == "PHYSICAL-BRANCH"
    assert first_if["condition_operator"] == "IS-TRUE"
    extra = first_if["extra_conditions"]
    assert len(extra) == 1
    assert extra[0]["connector"] == "AND"
    assert extra[0]["left"] == "TX-WITHDRAWAL"
    assert extra[0]["operator"] == "IS-TRUE"


def test_real_corpus_syntax_diagnostics_no_longer_include_condition_errors():
    """Before this fix: 5 SYN005 diagnostics tied to level-88 (3 DATA
    DIVISION VALUES-parse failures, 2 PROCEDURE DIVISION "expected
    comparison operator" failures). After: none. The one remaining
    diagnostic (a `* CATEGORY B: ...` comment-line artifact at line 4) is
    unrelated to level-88 and predates this fix."""
    bundle = build_analysis_bundle(
        "t_condition_names_88", _real_source(), tempfile.mkdtemp()
    )
    diagnostics = bundle.syntax_diagnostics or []
    condition_related = [
        d
        for d in diagnostics
        if "comparison operator" in d.get("message", "")
        or "VALUES" in d.get("message", "")
    ]
    assert condition_related == []
    assert len(diagnostics) == 1
    assert diagnostics[0]["line"] == 4


def test_real_corpus_business_rules_now_derived_from_level88_conditions():
    """Root cause 1 + 2 together: business-rule extraction, entirely
    unmodified by this task, now sees 8 real rules (up from 0) purely
    because the AST it walks is now complete -- nothing was invented to
    make this happen."""
    bundle = build_analysis_bundle(
        "t_condition_names_88", _real_source(), tempfile.mkdtemp()
    )
    rules = bundle.business_rules or []
    assert len(rules) == 8
    conditions = {r["condition"] for r in rules}
    assert "TX-VALID-KIND IS-FALSE TX-VALID-KIND" in conditions
    assert any(
        "PHYSICAL-BRANCH IS-TRUE PHYSICAL-BRANCH" in c and "TX-AMOUNT > 1000.00" in c
        for c in conditions
    )
    # every condition traces to a real source location, never fabricated
    for rule in rules:
        assert rule["source_locations"]
        for loc in rule["source_locations"]:
            assert loc["filename"] == "t_condition_names_88.cbl"
            assert loc["line"] > 0


def test_real_corpus_business_rules_are_exhaustively_is_true_is_false_shaped():
    """Documents the exact boundary this parser-only task left behind, and
    which a later, separate task (`docs/MMIM_LEVEL88_CONDITION_OPERATOR_FIX.md`)
    closed: every one of `t_condition_names_88`'s 8 business-rule
    conditions is `IS-TRUE`/`IS-FALSE` shaped (directly, or as a term
    inside an `AND` compound) -- confirming the parser-grammar gap this
    task fixed was the real and exhaustive blocker for this source, with
    nothing else standing between the AST and a `parse_condition`-shaped
    string. This module intentionally does not import or assert against
    `app/behavioral/extraction/conditions.py`'s *current* behavior (see
    `tests/behavioral/test_level88_condition_operator_fix.py` for that,
    including this same source's real-corpus regression) -- this test
    only pins facts about the AST/business-rule layer this task actually
    changed."""
    bundle = build_analysis_bundle(
        "t_condition_names_88", _real_source(), tempfile.mkdtemp()
    )
    rules = bundle.business_rules or []
    assert len(rules) == 8
    assert all(
        "IS-TRUE" in str(r["condition"]) or "IS-FALSE" in str(r["condition"])
        for r in rules
    )
    single_term = [r for r in rules if " AND " not in str(r["condition"])]
    assert len(single_term) == 2
