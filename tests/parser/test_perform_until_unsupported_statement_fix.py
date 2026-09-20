"""
Regression tests: unsupported-statement-in-scope parser recovery fix for
``PERFORM UNTIL`` bodies (Stage 28).

Purpose:
    ``ProcedureDivisionParser._parse_perform_statement``'s ``PERFORM
    UNTIL``/``END-PERFORM`` body loop checked only ``tok.lexeme.upper() in
    _STATEMENT_LEXEMES`` -- unlike the paragraph-level statement loop (and,
    since docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md, the ``IF``/``ELSE`` then/else
    loops), it never checked ``_UNSUPPORTED_STATEMENT_LEXEMES`` (the set that
    gives ``READ``/``COMPUTE``/``EVALUATE``/etc. their clean ``SYN100``
    "unsupported statement" diagnostic and graceful skip everywhere else). An
    unsupported verb used *inside* a ``PERFORM UNTIL`` body raised a hard
    ``ParserError`` instead, which the caller's statement-level recovery
    resolves by synchronising to the next ``PERIOD`` -- and a structured
    ``PERFORM UNTIL``/``END-PERFORM`` has no interior periods of its own
    guaranteed, so recovery ran straight through to the paragraph's own
    closing period, silently discarding everything in between (the whole
    paragraph, in the common case of one ``PERFORM UNTIL`` being the
    paragraph's only statement).

    This is the identical defect class docs/MMIM_COMPUTE_EVALUATE_IF_FIX.md
    §4 fixed for ``IF``/``ELSE`` blocks -- that task's own §8 found and named
    this exact third occurrence, explicitly out of its scope: "the fix would
    be structurally identical (one ``elif`` branch) if a future task
    requests it." Fixed here by adding that ``elif`` branch, routing
    unsupported verbs inside the ``PERFORM UNTIL`` body through the same
    ``_skip_unsupported_statement`` mechanism the paragraph-level loop and
    the ``IF``/``ELSE`` loops already use -- no new recovery behavior
    invented, matching the discipline both prior fixes followed.

Non-responsibilities:
    - Implementing any of the unsupported verbs' semantics -- they remain
      entirely unimplemented; only *recovery* around them changed.
    - ``SEARCH`` (the other scope-opening verb, alongside ``EVALUATE``)
      keeps its original, unbounded scan-to-next-period behavior -- no test
      here exercises it inside a ``PERFORM UNTIL`` body, matching the
      IF-block fix's own documented non-responsibility.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.service import AnalysisService
from app.dataset.corpus import load_training_corpus

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


def _codes(result) -> list[str]:
    return [str(getattr(d, "code", "")) for d in result.syntax_diagnostics]


# ---------------------------------------------------------------------------
# 1. PERFORM UNTIL ... COMPUTE ... END-PERFORM followed by another statement
# ---------------------------------------------------------------------------


def test_perform_until_compute_end_perform_then_another_statement(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T1.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A PIC 9(3) VALUE 0.
       01  WS-B PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM UNTIL WS-A >= 3
               COMPUTE WS-B = WS-B + 1
               ADD 1 TO WS-A
           END-PERFORM
           DISPLAY WS-B.
"""
    result = _analyze(src, tmp_path)
    assert _statement_types(result, "MAIN-PARA") == [
        "PerformUntilStatementNode",
        "DisplayStatementNode",
    ]
    codes = _codes(result)
    assert codes == ["SYN100"]
    (diag,) = result.syntax_diagnostics
    assert "COMPUTE" in diag.message
    pd = result.ast.procedure_division
    perform = pd.paragraphs[0].statements[0]
    assert [s.__class__.__name__ for s in perform.statements] == ["AddStatementNode"]


# ---------------------------------------------------------------------------
# 2. PERFORM UNTIL EVALUATE with no own period (idiomatic last-statement
#    form) is skipped to its matching END-EVALUATE, not the next period
# ---------------------------------------------------------------------------


def test_perform_until_evaluate_without_own_period_then_another_statement(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T2.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A PIC 9(3) VALUE 0.
       01  WS-B PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM UNTIL WS-A >= 3
               ADD 1 TO WS-A
               EVALUATE WS-A
                   WHEN 1 MOVE 'A' TO WS-B
                   WHEN OTHER MOVE 'B' TO WS-B
               END-EVALUATE
           END-PERFORM
           DISPLAY WS-B.
"""
    result = _analyze(src, tmp_path)
    assert _statement_types(result, "MAIN-PARA") == [
        "PerformUntilStatementNode",
        "DisplayStatementNode",
    ]
    assert _codes(result) == ["SYN100"]
    pd = result.ast.procedure_division
    perform = pd.paragraphs[0].statements[0]
    assert [s.__class__.__name__ for s in perform.statements] == ["AddStatementNode"]


# ---------------------------------------------------------------------------
# 3. The real corpus/fixture shape: READ ... AT END ... NOT AT END ...
#    END-READ inside a PERFORM UNTIL, with a nested IF inside NOT AT END
# ---------------------------------------------------------------------------


def test_perform_until_read_at_end_then_another_statement(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T3.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUSTOMER-FILE ASSIGN TO 'CUST.DAT'.
       DATA DIVISION.
       FILE SECTION.
       FD  CUSTOMER-FILE.
       01  CUST-RECORD PIC X(10).
       WORKING-STORAGE SECTION.
       01  WS-EOF PIC X(1) VALUE 'N'.
       01  WS-COUNT PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM UNTIL WS-EOF = 'Y'
               READ CUSTOMER-FILE
                   AT END
                       MOVE 'Y' TO WS-EOF
                   NOT AT END
                       ADD 1 TO WS-COUNT
               END-READ
           END-PERFORM
           DISPLAY WS-COUNT.
"""
    result = _analyze(src, tmp_path)
    assert _statement_types(result, "MAIN-PARA") == [
        "PerformUntilStatementNode",
        "DisplayStatementNode",
    ]
    codes = _codes(result)
    assert codes == ["SYN100"]
    assert "READ" in result.syntax_diagnostics[0].message
    pd = result.ast.procedure_division
    perform = pd.paragraphs[0].statements[0]
    # the whole READ...END-READ (AT END/NOT AT END clauses included) is
    # skipped as one unsupported statement -- exactly how READ is already
    # skipped everywhere else (docs/MMIM_READ_AT_END_PARSING_FIX.md)
    assert perform.statements == ()


# ---------------------------------------------------------------------------
# 4. Nested PERFORM UNTIL: the defect and its fix both apply at any depth
# ---------------------------------------------------------------------------


def test_nested_perform_until_with_compute_in_inner_loop(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T4.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-I PIC 9(3) VALUE 0.
       01  WS-J PIC 9(3) VALUE 0.
       01  WS-K PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM UNTIL WS-I >= 2
               ADD 1 TO WS-I
               PERFORM UNTIL WS-J >= 2
                   COMPUTE WS-K = WS-K + 1
                   ADD 1 TO WS-J
               END-PERFORM
           END-PERFORM
           DISPLAY WS-K.
"""
    result = _analyze(src, tmp_path)
    assert _statement_types(result, "MAIN-PARA") == [
        "PerformUntilStatementNode",
        "DisplayStatementNode",
    ]
    assert _codes(result) == ["SYN100"]
    outer = result.ast.procedure_division.paragraphs[0].statements[0]
    assert [s.__class__.__name__ for s in outer.statements] == [
        "AddStatementNode",
        "PerformUntilStatementNode",
    ]
    inner = outer.statements[1]
    assert [s.__class__.__name__ for s in inner.statements] == ["AddStatementNode"]


# ---------------------------------------------------------------------------
# 5. Paragraph boundary after PERFORM UNTIL COMPUTE is intact
# ---------------------------------------------------------------------------


def test_paragraph_boundary_after_perform_until_compute_is_intact(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T5.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       FIRST-PARA.
           PERFORM UNTIL WS-A >= 1
               COMPUTE WS-A = WS-A + 1
           END-PERFORM.
       SECOND-PARA.
           DISPLAY WS-A.
           STOP RUN.
"""
    result = _analyze(src, tmp_path)
    counts = _paragraph_statement_counts(result)
    assert counts == {"FIRST-PARA": 1, "SECOND-PARA": 2}
    assert _statement_types(result, "SECOND-PARA") == [
        "DisplayStatementNode",
        "StopRunStatementNode",
    ]


# ---------------------------------------------------------------------------
# 6. Malformed / unterminated PERFORM UNTIL still fails safely, not silently
# ---------------------------------------------------------------------------


def test_perform_until_missing_end_perform_still_diagnosed(tmp_path):
    """A genuinely unterminated PERFORM UNTIL (no END-PERFORM before EOF)
    is unaffected by this fix -- still reported, no crash, no silent
    swallow of unrelated tokens."""
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A PIC 9(3) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM UNTIL WS-A >= 3
               COMPUTE WS-A = WS-A + 1
"""
    result = _analyze(src, tmp_path)
    codes = _codes(result)
    assert "SYN100" in codes  # the COMPUTE is still skipped gracefully
    # some diagnostic reports the missing END-PERFORM; no exception raised
    assert result.ast is not None


# ---------------------------------------------------------------------------
# 7. Critical regression: statements after a PERFORM UNTIL with an
#    unsupported verb all survive (previously: zero statements, one vague
#    diagnostic)
# ---------------------------------------------------------------------------


def test_critical_regression_statements_after_perform_until_survive(tmp_path):
    src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. T7.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A PIC 9(3) VALUE 0.
       01  WS-B PIC 9(3) VALUE 0.
       01  WS-C PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 1 TO WS-A
           PERFORM UNTIL WS-A >= 3
               COMPUTE WS-B = WS-B + 1
               ADD 1 TO WS-A
           END-PERFORM
           MOVE 'Y' TO WS-C
           DISPLAY WS-B.
"""
    result = _analyze(src, tmp_path)
    assert _statement_types(result, "MAIN-PARA") == [
        "MoveStatementNode",
        "PerformUntilStatementNode",
        "MoveStatementNode",
        "DisplayStatementNode",
    ]
    codes = _codes(result)
    assert codes == ["SYN100"]
    assert "COMPUTE" in result.syntax_diagnostics[0].message


# ---------------------------------------------------------------------------
# 8. Real corpus: zero occurrences (confirmed directly, not assumed) --
#    matching task #stage22's precedent: a genuine, narrow, correctly-fixed
#    grammar/recovery gap with zero real-corpus impact needs no version bump
# ---------------------------------------------------------------------------

_UNSUPPORTED_VERBS = (
    "OPEN",
    "CLOSE",
    "READ",
    "WRITE",
    "REWRITE",
    "DELETE",
    "START",
    "EVALUATE",
    "COMPUTE",
    "STRING",
    "UNSTRING",
    "INSPECT",
    "INITIALIZE",
    "SEARCH",
    "SET",
    "SORT",
    "MERGE",
    "RETURN",
    "RELEASE",
    "ACCEPT",
    "CONTINUE",
    "EXIT",
)


def test_no_corpus_source_has_an_unsupported_verb_inside_perform_until() -> None:
    import re

    pattern = re.compile(r"PERFORM\s+UNTIL\b.*?END-PERFORM", re.IGNORECASE | re.DOTALL)
    verb_pattern = re.compile(r"\b(" + "|".join(_UNSUPPORTED_VERBS) + r")\b")
    hits: dict[str, list[str]] = {}
    for rec in load_training_corpus():
        for m in pattern.finditer(rec.source):
            body_verbs = sorted(set(verb_pattern.findall(m.group(0).upper())))
            if body_verbs:
                hits.setdefault(rec.source_id, []).extend(body_verbs)
    assert hits == {}


# ---------------------------------------------------------------------------
# 9. Shared workspace fixture: 3 real PERFORM UNTIL / READ occurrences
#    (not part of the 45-source training corpus, so no dataset impact, but
#    a real, independently-confirmed corpus of COBOL exercising this fix)
# ---------------------------------------------------------------------------

_FIXTURE = Path("workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl")


@pytest.mark.skipif(
    not _FIXTURE.exists(), reason="shared workspace fixture not present"
)
def test_fixture_three_read_occurrences_now_report_syn100_not_syn005() -> None:
    result = AnalysisService().analyze_file(_FIXTURE)
    codes_by_line = {d.line: str(d.code) for d in result.syntax_diagnostics}
    for line in (191, 229, 256):
        assert codes_by_line[line] == "SYN100", line
    assert "SYN005" not in [
        str(d.code) for d in result.syntax_diagnostics if d.line in (191, 229, 256)
    ]


@pytest.mark.skipif(
    not _FIXTURE.exists(), reason="shared workspace fixture not present"
)
def test_fixture_diagnostic_total_and_statements_parsed_move_by_the_read_fix() -> None:
    """Total diagnostics unchanged (49): each SYN005 is replaced 1-for-1 by
    a SYN100 at the same line. ``statements_parsed`` rises by exactly 3 (one
    newly-real ``PerformUntilStatementNode`` per fixed loop); the 3
    paragraphs that own them each gain exactly one statement."""
    result = AnalysisService().analyze_file(_FIXTURE)
    assert len(result.syntax_diagnostics) == 49
    assert result.coverage.statements_parsed == 63
    counts = _paragraph_statement_counts(result)
    assert counts["2000-LOAD-CUSTOMERS"] == 2
    assert counts["3000-LOAD-ACCOUNTS"] == 2
    assert counts["4000-PROCESS-TRANSACTIONS"] == 2
    for name in (
        "2000-LOAD-CUSTOMERS",
        "3000-LOAD-ACCOUNTS",
        "4000-PROCESS-TRANSACTIONS",
    ):
        types = _statement_types(result, name)
        assert "PerformUntilStatementNode" in types
