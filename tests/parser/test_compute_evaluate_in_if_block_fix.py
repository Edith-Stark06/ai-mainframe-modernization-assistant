"""
Regression tests: COMPUTE/EVALUATE-inside-IF-block parser recovery fix
(docs/MMIM_PARSER_VALIDATION_FIX.md §7 follow-up).

Purpose:
    ``ProcedureDivisionParser._parse_if_statement``'s then/else statement
    loops checked only ``tok.lexeme.upper() in _STATEMENT_LEXEMES`` — unlike
    the paragraph-level statement loop, they never checked
    ``_UNSUPPORTED_STATEMENT_LEXEMES`` (the set that gives ``COMPUTE``/
    ``EVALUATE``/etc. their clean ``SYN100`` "unsupported statement"
    diagnostic and graceful skip everywhere else). A ``COMPUTE`` or
    ``EVALUATE`` used *inside* an ``IF``'s then/else block raised a hard
    ``ParserError`` instead, which the caller's statement-level recovery
    resolves by synchronising to the next ``PERIOD`` — and a structured
    ``IF``/``END-IF`` has no interior periods, so recovery ran straight
    through to the paragraph's own closing period, silently discarding
    everything in between.

    Fixed by routing unsupported verbs inside the then/else loops through
    the same ``_skip_unsupported_statement`` mechanism the paragraph-level
    loop already used (``procedure_parser.py``).

    A second, sharper defect surfaced while fixing the first: scope-opening
    verbs (``EVALUATE``) are skipped by scanning for *the next period* —
    correct when ``EVALUATE`` is written with its own trailing period, but
    wrong when ``EVALUATE`` is the *last* statement inside an ``IF`` block
    (idiomatic COBOL — no period until the enclosing ``END-IF``): the old
    scan ran straight past ``END-IF`` and consumed the real statement after
    it. This is not new-to-the-IF-block-fix — it already existed at
    paragraph level for a period-less ``EVALUATE`` (see
    ``test_paragraph_level_evaluate_without_own_period_recovers_next_statement``
    below) — the IF-block fix just makes it visible far more often, since
    an ``EVALUATE`` nested in an ``IF`` almost never carries its own
    period. Fixed by matching ``EVALUATE``'s own ``END-EVALUATE`` precisely
    (honoring same-verb nesting) instead of scanning for an unrelated
    period, in the new ``ProcedureDivisionParser._skip_to_matching_close_word``.

Non-responsibilities:
    - ``SEARCH`` (the other scope-opening verb) keeps its original,
      unbounded scan-to-next-period behavior — no test in this corpus or
      task exercises it inside an ``IF``/``ELSE`` block.
    - Implementing COMPUTE/EVALUATE semantics — both remain entirely
      unimplemented verbs; only *recovery* around them changed.
    - The identical defect pattern in ``PERFORM UNTIL`` bodies (a third,
      unfixed occurrence of the same statement-loop shape) — reported
      separately, not fixed here, per this task's explicit scope.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.analysis.service import AnalysisService

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


def _statement_types(result, paragraph_name: str) -> list[str]:
    pd = result.ast.procedure_division
    for p in pd.paragraphs:
        if p.name == paragraph_name:
            return [s.__class__.__name__ for s in p.statements]
    raise AssertionError(f"no such paragraph: {paragraph_name}")


# ---------------------------------------------------------------------------
# 1. IF ... COMPUTE ... END-IF followed by another statement
# ---------------------------------------------------------------------------


def test_if_compute_end_if_then_another_statement(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T1.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       01 WS-B PIC 9(5) VALUE 2.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               COMPUTE WS-B = WS-A + 1
           END-IF
           DISPLAY WS-B
           DISPLAY WS-A.
"""
    result = _analyze(src, tmp_path)
    codes = [d.code for d in result.syntax_diagnostics]
    assert codes == ["SYN100"]
    assert "unsupported statement 'COMPUTE'" in result.syntax_diagnostics[0].message
    assert _statement_types(result, "MAIN-PARA") == [
        "IfStatementNode",
        "DisplayStatementNode",
        "DisplayStatementNode",
    ]


def test_if_compute_else_compute_end_if_then_another_statement(tmp_path):
    """The ELSE branch's statement loop needed the identical fix."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T1B.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       01 WS-B PIC 9(5) VALUE 2.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               DISPLAY 'POSITIVE'
           ELSE
               COMPUTE WS-B = WS-A - 1
           END-IF
           DISPLAY WS-B.
"""
    result = _analyze(src, tmp_path)
    codes = [d.code for d in result.syntax_diagnostics]
    assert codes == ["SYN100"]
    assert _statement_types(result, "MAIN-PARA") == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]
    if_stmt = result.ast.procedure_division.paragraphs[0].statements[0]
    assert len(if_stmt.then_statements) == 1
    assert len(if_stmt.else_statements) == 0  # COMPUTE itself is still unmodeled


# ---------------------------------------------------------------------------
# 2. IF ... COMPUTE ... followed by another statement at paragraph level
#    (regression: the pre-existing top-level behavior must be unchanged)
# ---------------------------------------------------------------------------


def test_compute_at_paragraph_level_unchanged(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T2.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           COMPUTE WS-A = WS-A + 1
           DISPLAY WS-A.
"""
    result = _analyze(src, tmp_path)
    codes = [d.code for d in result.syntax_diagnostics]
    assert codes == ["SYN100"]
    assert _statement_types(result, "MAIN-PARA") == ["DisplayStatementNode"]


# ---------------------------------------------------------------------------
# 3. IF ... EVALUATE ... END-IF followed by another statement
# ---------------------------------------------------------------------------


def test_if_evaluate_end_if_then_another_statement(tmp_path):
    """EVALUATE as the IF block's last statement -- idiomatic COBOL, no
    period of its own; the closing word is END-EVALUATE, then END-IF
    supplies the real terminator."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T3.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               EVALUATE WS-A
                   WHEN 1
                       DISPLAY 'ONE'
                   WHEN OTHER
                       DISPLAY 'OTHER'
               END-EVALUATE
           END-IF
           DISPLAY WS-A.
"""
    result = _analyze(src, tmp_path)
    codes = [d.code for d in result.syntax_diagnostics]
    assert codes == ["SYN100"]
    assert "unsupported statement 'EVALUATE'" in result.syntax_diagnostics[0].message
    assert _statement_types(result, "MAIN-PARA") == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]


def test_paragraph_level_evaluate_with_own_period_unchanged(tmp_path):
    """Pre-existing, already-tested paragraph-level shape
    (tests/parser/test_statement_boundaries.py::
    test_scope_delimited_construct_still_skipped_whole) must be byte-for-
    byte unchanged by this fix."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T3B.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           EVALUATE WS-A
               WHEN 1
                   DISPLAY 'ONE'
           END-EVALUATE.
           STOP RUN.
"""
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == ["SYN100"]
    assert _statement_types(result, "MAIN-PARA") == ["StopRunStatementNode"]


def test_paragraph_level_evaluate_without_own_period_recovers_next_statement(
    tmp_path,
):
    """Critical companion fix: this was ALREADY broken before any IF was
    involved -- a period-less EVALUATE at plain paragraph level lost
    everything after it too, via the same "scan to next period" defect.
    Now fixed by the same precise END-EVALUATE matching."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T3C.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           EVALUATE WS-A
               WHEN 1
                   DISPLAY 'ONE'
           END-EVALUATE
           STOP RUN.
"""
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == ["SYN100"]
    assert _statement_types(result, "MAIN-PARA") == ["StopRunStatementNode"]


# ---------------------------------------------------------------------------
# 4. COMPUTE with integer operands / 5. COMPUTE with decimal literals
# ---------------------------------------------------------------------------


def test_if_compute_integer_operands_then_statement(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T4.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       01 WS-B PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               COMPUTE WS-B = WS-A + 2 * 3
           END-IF
           DISPLAY WS-B.
"""
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == ["SYN100"]
    assert _statement_types(result, "MAIN-PARA") == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]


def test_if_compute_decimal_literal_operands_then_statement(tmp_path):
    """Combines both parser fixes: a decimal literal inside a COMPUTE
    that is itself inside an IF block."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T5.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5)V99 VALUE 1.
       01 WS-B PIC 9(5)V99 VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               COMPUTE WS-B = WS-A * 1.50
           END-IF
           DISPLAY WS-B.
"""
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == ["SYN100"]
    assert _statement_types(result, "MAIN-PARA") == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]


# ---------------------------------------------------------------------------
# 6. Nested IF + COMPUTE/EVALUATE where nested constructs are supported
# ---------------------------------------------------------------------------


def test_nested_if_with_compute_in_inner_branch(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       01 WS-B PIC 9(5) VALUE 2.
       01 WS-C PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               IF WS-B > 0
                   COMPUTE WS-C = WS-A + WS-B
               END-IF
               DISPLAY WS-C
           END-IF
           DISPLAY WS-A.
"""
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == ["SYN100"]
    outer_if = result.ast.procedure_division.paragraphs[0].statements[0]
    assert [s.__class__.__name__ for s in outer_if.then_statements] == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]
    inner_if = outer_if.then_statements[0]
    assert inner_if.then_statements == ()  # COMPUTE itself stays unmodeled
    assert _statement_types(result, "MAIN-PARA") == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]


def test_nested_evaluate_inside_evaluate_inside_if(tmp_path):
    """Same-verb nesting depth tracking in
    ProcedureDivisionParser._skip_to_matching_close_word."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6B.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       01 WS-B PIC 9(5) VALUE 2.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               EVALUATE WS-A
                   WHEN 1
                       EVALUATE WS-B
                           WHEN 2
                               DISPLAY 'INNER'
                       END-EVALUATE
               END-EVALUATE
           END-IF
           DISPLAY WS-A.
"""
    result = _analyze(src, tmp_path)
    assert [d.code for d in result.syntax_diagnostics] == ["SYN100"]
    assert _statement_types(result, "MAIN-PARA") == [
        "IfStatementNode",
        "DisplayStatementNode",
    ]


# ---------------------------------------------------------------------------
# 7. Period/paragraph boundary after the affected block
# ---------------------------------------------------------------------------


def test_paragraph_boundary_after_if_compute_is_intact(tmp_path):
    """The next PARAGRAPH (not just the next statement) must be completely
    unaffected."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T7.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       01 WS-B PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               COMPUTE WS-B = WS-A + 1
           END-IF
           DISPLAY WS-B.
       NEXT-PARA.
           DISPLAY 'REACHED'.
           STOP RUN.
"""
    result = _analyze(src, tmp_path)
    counts = _paragraph_statement_counts(result)
    assert counts == {"MAIN-PARA": 2, "NEXT-PARA": 2}
    assert [d.code for d in result.syntax_diagnostics] == ["SYN100"]


# ---------------------------------------------------------------------------
# 8. Malformed COMPUTE/EVALUATE still produces a diagnostic, never silently
#    consumes the rest of the paragraph
# ---------------------------------------------------------------------------


def test_evaluate_missing_end_evaluate_stops_safely_not_silently(tmp_path):
    """A malformed (unterminated) EVALUATE inside an IF must not crash and
    must not silently swallow an unrelated later paragraph -- it is
    diagnosed and the scan stops at EOF/division-boundary, exactly like
    every other unsupported-statement skip already does."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T8.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A > 0
               EVALUATE WS-A
                   WHEN 1
                       DISPLAY 'ONE'
"""
    result = _analyze(src, tmp_path)
    # must not raise; must still produce the unsupported-statement diagnostic
    assert any(d.code == "SYN100" for d in result.syntax_diagnostics)
    assert result.ast is not None


def test_malformed_if_condition_still_diagnosed_not_silently_parsed(tmp_path):
    """An outright malformed IF condition (not COMPUTE/EVALUATE-related)
    must still raise a diagnostic -- this fix only changes recovery for
    *unsupported verbs*, never makes genuinely malformed syntax parse."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T8B.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(5) VALUE 1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF WS-A
               DISPLAY 'BAD'
           END-IF
           STOP RUN.
"""
    result = _analyze(src, tmp_path)
    assert any(d.code == "SYN005" for d in result.syntax_diagnostics)


# ---------------------------------------------------------------------------
# Critical regression: the previously-lost statement is present
# ---------------------------------------------------------------------------


def test_critical_regression_statement_after_if_compute_survives(tmp_path):
    """The exact previously-reported failure mode
    (docs/MMIM_PARSER_VALIDATION_FIX.md §7): before this fix, this whole
    paragraph parsed to ZERO statements with a single vague diagnostic
    that did not even name COMPUTE as the cause."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRITICAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 MONTHLY-INCOME PIC 9(7)V99 VALUE 5500.
       01 DTI-PERCENTAGE PIC 9(5)V99 VALUE 0.
       01 WS-NOTE PIC X(10) VALUE SPACES.
       PROCEDURE DIVISION.
       MAIN-PARA.
           IF MONTHLY-INCOME > 0.00
               COMPUTE DTI-PERCENTAGE = MONTHLY-INCOME * 2.50
           ELSE
               MOVE 999.00 TO DTI-PERCENTAGE
           END-IF
           MOVE 'DONE' TO WS-NOTE
           DISPLAY DTI-PERCENTAGE
           DISPLAY WS-NOTE.
"""
    result = _analyze(src, tmp_path)
    para = result.ast.procedure_division.paragraphs[0]
    # IF, MOVE, DISPLAY, DISPLAY -- nothing lost
    assert len(para.statements) == 4
    assert [s.__class__.__name__ for s in para.statements] == [
        "IfStatementNode",
        "MoveStatementNode",
        "DisplayStatementNode",
        "DisplayStatementNode",
    ]
    codes = [d.code for d in result.syntax_diagnostics]
    assert codes == ["SYN100"]
    assert "COMPUTE" in result.syntax_diagnostics[0].message
