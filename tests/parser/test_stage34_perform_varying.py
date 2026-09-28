"""
Parser tests for task #stage34 — ``PERFORM VARYING ... FROM ... BY ...
UNTIL ...`` structured loop parsing.

Purpose:
    Before this stage, the token right after ``PERFORM`` being ``VARYING``
    (not ``UNTIL``) fell into ``_parse_perform_statement``'s inline-target
    branch, which -- finding an ``IDENTIFIER``-shaped token (``VARYING``
    is not a reserved lexer word) -- misread the whole construct as a
    ``PERFORM`` to a paragraph literally named "VARYING"
    (``PerformStatementNode(target="VARYING")``), discarding the varying
    variable, ``FROM``/``BY``/``UNTIL`` clauses, and the entire loop body.

    ``ProcedureDivisionParser._parse_perform_varying_statement`` replaces
    that misparse with the real grammar, producing a structured
    ``PerformVaryingStatementNode`` whose body is parsed with the exact
    same statement-list mechanism ``PERFORM UNTIL``/``IF`` already use.

Coverage (mapped to the task's 20 numbered requirements, items 1-7 and
11-12 at this layer):
    1-7. PERFORM VARYING recognition, varying variable, FROM, BY, UNTIL,
         body retention, body statement count.
    11-12. Nested IF and MOVE inside the body survive.
    Token-boundary tests (exact consumption, no over/under-reach).
    Malformed/incomplete syntax regression tests.
    EXIT PERFORM inside the body (a real-corpus shape) tested via the
    already-existing, unmodified statement-skip machinery. COMPUTE inside
    the body was too, until task #stage35 implemented COMPUTE itself --
    see ``test_compute_inside_body_now_parses``, which now asserts the
    real corpus shape (a subscripted running-total accumulation on the
    loop's own varying variable) parses correctly, exercising that
    Stage 34's loop/index machinery already exposes everything COMPUTE
    needs, unchanged.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

from app.parser.ast.statements import (
    ComputeStatementNode,
    DisplayStatementNode,
    IfStatementNode,
    MoveStatementNode,
    PerformVaryingStatementNode,
    StopRunStatementNode,
)
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 CURRENT-IDX PIC 9(2) VALUE 1.\n"
    "01 WS-TABLE.\n"
    "   05 WS-ITEM PIC 9(3) OCCURS 4.\n"
    "01 WS-TOTAL PIC 9(5).\n"
    "PROCEDURE DIVISION.\n"
)


def _parse(body: str) -> Any:
    """Parse a PROCEDURE DIVISION *body* end to end, returning the program."""
    source = f"{_HEADER}MAIN-PARA.\n{body}"
    state = ParserState(TokenStream(CobolLexer().tokenize(source, filename="t.cbl")))
    return ProgramParser()._parse_program(state)


def _statements(program: Any) -> list[Any]:
    return list(program.procedure_division.paragraphs[0].statements)


def _diagnostics(body: str) -> list[Any]:
    """Parse *body* via the full pipeline (recovery-aware) and return the
    resulting syntax diagnostics -- used for malformed-syntax tests where
    a raw ParserError would abort rather than recover."""
    from app.analysis.service import AnalysisService
    import tempfile
    from pathlib import Path

    source = f"{_HEADER}MAIN-PARA.\n{body}"
    d = Path(tempfile.mkdtemp())
    p = d / "t.cbl"
    p.write_text(source, encoding="utf-8")
    return AnalysisService().analyze_file(p).syntax_diagnostics


class TestBasicRecognition:
    """Items 1-5: PERFORM VARYING is recognised; varying variable, FROM,
    BY, UNTIL are all captured correctly."""

    def test_recognises_perform_varying(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert loop is not None

    def test_varying_variable(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert loop.varying_variable == "CURRENT-IDX"

    def test_from_expression(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert loop.from_value == "1"

    def test_by_expression(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert loop.by_value == "1"

    def test_by_negative_expression(self) -> None:
        """BY -1: the sign must be joined to the digit, matching the
        established VALUE-clause signed-literal precedent."""
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 4 BY -1\n"
            "        UNTIL CURRENT-IDX < 1\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert loop.by_value == "-1"

    def test_until_condition(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert loop.condition_left == "CURRENT-IDX"
        assert loop.condition_operator == ">"
        assert loop.condition_right == "4"


class TestBodyRetention:
    """Items 6-7: the body is retained (the current-before-this-stage
    bug discards it), with the correct statement count."""

    def test_body_is_retained_not_discarded(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert len(loop.statements) == 1
        assert isinstance(loop.statements[0], DisplayStatementNode)

    def test_body_statement_count_multiple(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        MOVE CURRENT-IDX TO WS-ITEM(CURRENT-IDX)\n"
            "        DISPLAY WS-ITEM(CURRENT-IDX)\n"
            "        DISPLAY 'X'\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert len(loop.statements) == 3

    def test_subscripted_body_operand_is_structured(self) -> None:
        """A subscripted reference inside the loop body reaches Stage 32's
        structured Subscript, not a flattened string."""
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        MOVE CURRENT-IDX TO WS-ITEM(CURRENT-IDX)\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        (mv,) = loop.statements
        assert isinstance(mv, MoveStatementNode)
        assert mv.target == "WS-ITEM"
        assert len(mv.target_subscript) == 1
        assert mv.target_subscript[0].kind == "identifier"
        assert mv.target_subscript[0].value == "CURRENT-IDX"


class TestTokenBoundaries:
    """Exact token consumption: the loop must not swallow the statement
    that follows it, nor leak into the loop body."""

    def test_statement_after_loop_is_not_consumed(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n"
            "    DISPLAY 'DONE'.\n"
            "    STOP RUN.\n"
        )
        stmts = _statements(program)
        assert len(stmts) == 3
        assert isinstance(stmts[0], PerformVaryingStatementNode)
        assert isinstance(stmts[1], DisplayStatementNode)
        assert stmts[1].operand == "'DONE'"
        assert isinstance(stmts[2], StopRunStatementNode)

    def test_no_trailing_period_still_terminates_cleanly(self) -> None:
        """END-PERFORM with no statement-level period before the next
        sentence (a bare END-PERFORM immediately followed by another
        statement on its own line) still ends the loop at the right
        token."""
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM\n"
            "    DISPLAY 'AFTER'.\n"
            "    STOP RUN.\n"
        )
        stmts = _statements(program)
        assert len(stmts) == 3
        assert stmts[1].operand == "'AFTER'"


class TestNestedControlFlow:
    """Item 11: nested IF/END-IF inside PERFORM VARYING survives, via the
    same _parse_statement/_parse_perform_body machinery IF/PERFORM UNTIL
    already use -- no parallel mini-language."""

    def test_if_inside_perform_varying(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        IF WS-ITEM(CURRENT-IDX) > 100\n"
            "            MOVE 0 TO WS-ITEM(CURRENT-IDX)\n"
            "        END-IF\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert len(loop.statements) == 1
        (if_stmt,) = loop.statements
        assert isinstance(if_stmt, IfStatementNode)
        assert if_stmt.condition_left == "WS-ITEM"
        assert len(if_stmt.condition_left_subscript) == 1
        (then_stmt,) = if_stmt.then_statements
        assert isinstance(then_stmt, MoveStatementNode)
        assert then_stmt.target == "WS-ITEM"


class TestRealCorpusShapes:
    """The exact real-corpus body shapes: EXIT PERFORM inside a nested IF
    (complex_acctbatch's 4100-FIND-ACCOUNT/4200-FIND-CUSTOMER), and
    COMPUTE inside the loop body (t_table_indexed) -- both already
    handled by the unmodified _skip_unsupported_statement path, exactly
    like they already are inside a plain IF/PERFORM UNTIL."""

    def test_exit_perform_inside_nested_if_does_not_break_the_loop(self) -> None:
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        IF WS-ITEM(CURRENT-IDX) > 100\n"
            "            MOVE 0 TO WS-ITEM(CURRENT-IDX)\n"
            "            EXIT PERFORM\n"
            "        END-IF\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        (if_stmt,) = loop.statements
        # EXIT is skipped (unsupported), the MOVE around it survives.
        assert len(if_stmt.then_statements) == 1
        assert isinstance(if_stmt.then_statements[0], MoveStatementNode)

    def test_compute_inside_body_now_parses(self) -> None:
        """Renamed (task #stage35): COMPUTE was out of Stage 34's scope
        and got the graceful-skip treatment tested here originally.
        Stage 35 implements COMPUTE itself -- this is exactly the real
        corpus shape (`t_table_indexed`'s running-total aggregation,
        `TOTAL = TOTAL + ITEM(idx)` with an identifier subscript on the
        loop's own varying variable) that motivated checking COMPUTE
        inside a PERFORM VARYING body in the first place, so it now
        asserts the stronger, correct outcome: both statements survive,
        not just the one COMPUTE used to leave behind. Stage 34's loop
        header/index machinery itself is completely unchanged -- this
        only exercises that it already exposed everything COMPUTE needs."""
        program = _parse(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        COMPUTE WS-TOTAL = WS-TOTAL + WS-ITEM(CURRENT-IDX)\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s
            for s in _statements(program)
            if isinstance(s, PerformVaryingStatementNode)
        ]
        assert len(loop.statements) == 2
        compute, display = loop.statements
        assert isinstance(compute, ComputeStatementNode)
        assert compute.target == "WS-TOTAL"
        assert isinstance(display, DisplayStatementNode)


class TestMalformedSyntaxRegression:
    """Missing/incomplete VARYING clauses are reported, not silently
    misparsed. The full pipeline (``AnalysisService``, exactly like every
    other diagnostic test in this project) recovers from the underlying
    ``ParserError`` via the paragraph-level statement loop's existing
    ``record_and_synchronise`` mechanism -- the same recovery path every
    other unsupported/malformed construct already goes through -- so the
    observable contract is a reported ``SYN005`` diagnostic, not a raised
    exception reaching the caller."""

    def test_missing_from_is_reported_via_full_pipeline(self) -> None:
        diags = _diagnostics(
            "    PERFORM VARYING CURRENT-IDX BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        assert any(d.code == "SYN005" for d in diags)

    def test_missing_by_is_reported_via_full_pipeline(self) -> None:
        diags = _diagnostics(
            "    PERFORM VARYING CURRENT-IDX FROM 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        assert any(d.code == "SYN005" for d in diags)

    def test_missing_until_is_reported_via_full_pipeline(self) -> None:
        diags = _diagnostics(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        assert any(d.code == "SYN005" for d in diags)

    def test_missing_end_perform_is_reported_via_full_pipeline(self) -> None:
        diags = _diagnostics(
            "    PERFORM VARYING CURRENT-IDX FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    STOP RUN.\n"
        )
        assert any(d.code == "SYN005" for d in diags)

    def test_missing_varying_variable_is_reported_via_full_pipeline(self) -> None:
        diags = _diagnostics(
            "    PERFORM VARYING FROM 1 BY 1\n"
            "        UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        assert any(d.code == "SYN005" for d in diags)


class TestScalarRegression:
    """A plain (non-VARYING) PERFORM UNTIL, and a plain inline PERFORM,
    are completely unaffected by this stage."""

    def test_plain_perform_until_unaffected(self) -> None:
        from app.parser.ast.statements import PerformUntilStatementNode

        program = _parse(
            "    PERFORM UNTIL CURRENT-IDX > 4\n"
            "        DISPLAY CURRENT-IDX\n"
            "        ADD 1 TO CURRENT-IDX\n"
            "    END-PERFORM.\n    STOP RUN.\n"
        )
        (loop,) = [
            s for s in _statements(program) if isinstance(s, PerformUntilStatementNode)
        ]
        assert loop.condition_left == "CURRENT-IDX"
        assert loop.condition_operator == ">"
        assert loop.condition_right == "4"
        assert len(loop.statements) == 2

    def test_plain_inline_perform_unaffected(self) -> None:
        from app.parser.ast.statements import PerformStatementNode

        program = _parse("    PERFORM 2000-SUB-PARAGRAPH.\n    STOP RUN.\n")
        (perf,) = [
            s for s in _statements(program) if isinstance(s, PerformStatementNode)
        ]
        assert perf.target == "2000-SUB-PARAGRAPH"
        assert perf.thru_target == ""
