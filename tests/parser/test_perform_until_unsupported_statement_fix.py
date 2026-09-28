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
    # task #stage35: COMPUTE now parses -- `WS-B + 1` is a plain +
    # expression, squarely the supported grammar -- so no diagnostic at
    # all, and the loop body now models both statements.
    assert _statement_types(result, "MAIN-PARA") == [
        "PerformUntilStatementNode",
        "DisplayStatementNode",
    ]
    codes = _codes(result)
    assert codes == []
    pd = result.ast.procedure_division
    perform = pd.paragraphs[0].statements[0]
    assert [s.__class__.__name__ for s in perform.statements] == [
        "ComputeStatementNode",
        "AddStatementNode",
    ]


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
    """task #stage40: READ now has a real parser/AST node (previously
    unsupported, whole READ...END-READ skipped as one SYN100). This test
    originally documented that discard-path behaviour; now that READ is
    genuinely parsed, this exact source produces zero diagnostics and the
    PERFORM UNTIL body holds a real ``ReadStatementNode`` with its AT
    END/NOT AT END clauses captured -- confirmed directly, not assumed."""
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
    assert codes == []
    pd = result.ast.procedure_division
    perform = pd.paragraphs[0].statements[0]
    assert [s.__class__.__name__ for s in perform.statements] == ["ReadStatementNode"]
    read = perform.statements[0]
    assert [s.__class__.__name__ for s in read.at_end_statements] == [
        "MoveStatementNode"
    ]
    assert [s.__class__.__name__ for s in read.not_at_end_statements] == [
        "AddStatementNode"
    ]


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
    # task #stage35: COMPUTE now parses at any PERFORM UNTIL nesting depth.
    assert _statement_types(result, "MAIN-PARA") == [
        "PerformUntilStatementNode",
        "DisplayStatementNode",
    ]
    assert _codes(result) == []
    outer = result.ast.procedure_division.paragraphs[0].statements[0]
    assert [s.__class__.__name__ for s in outer.statements] == [
        "AddStatementNode",
        "PerformUntilStatementNode",
    ]
    inner = outer.statements[1]
    assert [s.__class__.__name__ for s in inner.statements] == [
        "ComputeStatementNode",
        "AddStatementNode",
    ]


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
    swallow of unrelated tokens.

    task #stage35: COMPUTE itself now parses cleanly (no SYN100 for it
    any more -- confirmed directly), so what remains is the missing
    END-PERFORM itself: a SYN005, not SYN100, since there is no longer
    any unsupported verb in this source for SYN100 to be about."""
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
    assert "SYN005" in codes  # missing END-PERFORM; no exception raised
    assert "SYN100" not in codes  # COMPUTE itself no longer unsupported
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
    # task #stage35: COMPUTE now parses -- no diagnostic at all, and the
    # loop body now models it instead of only the ADD that survived.
    codes = _codes(result)
    assert codes == []
    perform = result.ast.procedure_division.paragraphs[0].statements[1]
    assert [s.__class__.__name__ for s in perform.statements] == [
        "ComputeStatementNode",
        "AddStatementNode",
    ]


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

_FIXTURE = Path("tests/fixtures/complex_acctbatch.cbl")


@pytest.mark.skipif(
    not _FIXTURE.exists(), reason="shared workspace fixture not present"
)
def test_fixture_three_read_occurrences_now_report_no_diagnostic() -> None:
    """task #stage40: READ now has a real parser/AST node, so these 3
    real ``READ ... AT END ... NOT AT END ... END-READ`` occurrences no
    longer produce any diagnostic at all (previously ``SYN100``, and
    before that, in the pre-#stage28 baseline, ``SYN005``) -- confirmed
    directly against the fixture, not assumed."""
    result = AnalysisService().analyze_file(_FIXTURE)
    codes_by_line = {d.line: str(d.code) for d in result.syntax_diagnostics}
    for line in (191, 229, 256):
        assert line not in codes_by_line, line


@pytest.mark.skipif(
    not _FIXTURE.exists(), reason="shared workspace fixture not present"
)
def test_fixture_diagnostic_total_and_statements_parsed_move_by_the_read_fix() -> None:
    """Total diagnostics unchanged (49 at the time of this stage): each
    SYN005 is replaced 1-for-1 by a SYN100 at the same line.
    ``statements_parsed`` rises by exactly 3 (one newly-real
    ``PerformUntilStatementNode`` per fixed loop); the 3 paragraphs that own
    them each gain exactly one statement.

    49 -> 48 and 63 -> 68 (task #stage32) are for a later, unrelated
    reason, not this stage's own fix: this fixture's
    ``4300-VALIDATE-TRANSACTION``/``4310-CHECK-LIMIT``/``4320-CHECK-FRAUD``/
    ``4330-CHECK-DATE``/``4400-POST-TRANSACTION``/``4410-CALCULATE-FEE``/
    ``4420-UPDATE-ACCOUNT-TABLE`` paragraphs contain ``IF`` conditions on
    subscripted table elements, which this grammar's comparison-operand
    check had never accepted -- each was its own latent
    ``SYN005 "expected comparison operator"``, dropping the whole
    enclosing ``IF``/``END-IF`` (and every statement inside it). Task
    #stage32 (docs/...) teaches the condition parser to recognise a
    single-dimension, literal- or identifier-subscripted reference as one
    structured operand instead, so these ``IF``s now parse: one fewer
    ``SYN005`` (49 -> 48) and 8 more previously-unreachable statements now
    counted (63 -> 68). Confirmed directly against the fixture, not
    assumed. This stage's own three ``PERFORM VARYING`` occurrences
    (``4100-FIND-ACCOUNT``, ``4200-FIND-CUSTOMER``, ``5000-CALCULATE-
    EXPOSURE``/``5100-RISK-AGGREGATION``) were untouched by task #stage32 --
    `PERFORM VARYING`'s own header grammar was a separate, deliberately
    out-of-scope gap at that time (task #stage32 only fixed table/subscript
    *representation*) -- so this test's own three per-paragraph assertions
    below were unaffected by that stage and stayed exactly as they were.

    48 -> 47 (task #stage34) is for a further, later, unrelated reason:
    task #stage34 finally implements ``PERFORM VARYING`` itself (this
    fixture's four occurrences, including the three named above). Before
    it, each mis-parsed into a bare ``PerformStatementNode(
    target="VARYING")``, stranding the loop variable
    (``WS-IDX``/``WS-IDX2``) on the token stream as an unexpected token
    -- 4 latent ``SYN001`` diagnostics. Task #stage34's real
    ``PerformVaryingStatementNode``/parser removes all 4 (net -4); it
    also newly reaches two ``EXIT PERFORM`` statements nested inside two
    of those loops' bodies and correctly reports each as its own
    ``SYN100 "unsupported statement 'EXIT PERFORM'"`` (net +2) rather
    than letting a mis-skipped bare ``EXIT`` leave a stray ``PERFORM``
    token to corrupt the surrounding parse. Net -2 relative to the true,
    pre-#stage32 baseline this fixture started from; combined with
    #stage32's own already-recorded -1, that nets to 48 -> 47 relative to
    this test's immediately-prior (#stage32-era) value -- confirmed
    directly against the fixture, not assumed.

    68 -> 67 (task #stage34) similarly: ``statements_parsed`` reflects
    the four loops' headers now being real ``PerformVaryingStatementNode``
    statements plus their genuinely-supported body statements (MOVE/ADD/
    IF -- COMPUTE/EXIT PERFORM still contribute none, exactly like any
    other unsupported statement), net of what the previous ``SYN001``
    misparse recovery had -- by accident, not by design -- still managed
    to count nearby. Confirmed directly against the fixture as 67, not
    derived from a hand-decomposed sum. This stage's own three
    per-paragraph assertions below (``2000-LOAD-CUSTOMERS``/
    ``3000-LOAD-ACCOUNTS``/``4000-PROCESS-TRANSACTIONS``, all plain
    ``PERFORM UNTIL``, no ``VARYING``) are unaffected by task #stage34 and
    stay exactly as they were -- confirmed directly.

    47 -> 44 and 67 -> 69 (task #stage35): COMPUTE is now implemented; 4
    of this fixture's 6 real COMPUTE statements now parse (net -4
    diagnostics), the other 2 use syntax Stage 35 does not implement
    (``FUNCTION``, ``ROUNDED``) and are unaffected -- see
    ``tests/parser/test_unsupported_syntax_reporting.py
    ::test_complex_fixture_surfaces_49_syntax_diagnostics`` for the full
    accounting. None of the 6 COMPUTE statements are in this test's three
    named paragraphs (``2000-LOAD-CUSTOMERS``/``3000-LOAD-ACCOUNTS``/
    ``4000-PROCESS-TRANSACTIONS``), so their per-paragraph counts below
    are unaffected -- confirmed directly.

    44 -> 41 (task #stage40): ``READ`` now has a real parser/AST node.
    This fixture's 3 real ``READ ... AT END ... NOT AT END ... END-READ``
    occurrences (``2000-LOAD-CUSTOMERS``/``3000-LOAD-ACCOUNTS``/
    ``4000-PROCESS-TRANSACTIONS``, lines 191/229/256) previously each
    contributed one ``SYN100`` "unsupported statement" diagnostic; all
    three now parse cleanly with zero diagnostics (net -3). ``AT END``'s
    ``MOVE`` now lowers as real IR (task #stage40's always-end-of-file
    model); ``NOT AT END``'s statements are captured on the AST for
    fidelity but never lowered (provably unreachable under that model).
    ``statements_parsed`` stays at 69, unchanged: each ``PERFORM UNTIL``
    body already counted as exactly one statement before this fix (the
    ``PerformUntilStatementNode`` itself), and still does -- the READ is
    now that one statement's real content instead of a fully-discarded
    unsupported statement contributing zero, so the body's own statement
    count does not change. Confirmed directly against the fixture, not
    assumed.

    41 -> 24 (task #stage41): ``USAGE``/``COMP*`` now has a real
    parser/AST field. This fixture's 17 real ``COMP-3`` occurrences
    (none in this test's three named paragraphs) previously each
    contributed one ``SYN200`` "not represented" diagnostic; all 17 now
    attach a real ``UsageType.COMP_3`` with zero diagnostics (net -17).
    ``statements_parsed`` and the three named paragraphs' own statement
    counts are unaffected -- USAGE is a data-item clause, not a
    PROCEDURE DIVISION statement. Confirmed directly against the
    fixture, not assumed."""
    result = AnalysisService().analyze_file(_FIXTURE)
    assert len(result.syntax_diagnostics) == 24
    assert result.coverage.statements_parsed == 69
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
