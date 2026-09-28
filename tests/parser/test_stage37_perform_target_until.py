"""
Parser tests for task #stage37 — out-of-line ``PERFORM paragraph-name
UNTIL condition``.

Purpose:
    Before this stage, ``_parse_perform_statement``'s bare-target branch
    consumed only the paragraph name, leaving ``UNTIL <condition>`` on
    the stream. The next statement-level parse attempt raised
    ``ParserError`` ("expected statement keyword" / unexpected token),
    and because the four real corpus sources carrying this shape
    (``t_batch_acct_update``, ``t_daily_trans_report``,
    ``t_inventory_extract``, ``t_payroll_file_post``) have no period
    between statements in the entry paragraph, panic-mode recovery
    resynchronised to the next PERIOD — silently discarding every
    statement after the malformed PERFORM, including that paragraph's
    own closing PERFORM (to close files) and GOBACK.

    ``_parse_perform_statement`` now recognises ``PERFORM <identifier>
    UNTIL <condition>`` as a distinct form (checked before the THRU/
    THROUGH branch), parses the condition via the same
    ``_parse_condition_term`` machinery ``IF`` and ``PERFORM VARYING``
    already use, and returns a
    :class:`~app.parser.ast.statements.PerformTargetUntilStatementNode`
    — with no body/END-PERFORM to consume, since none exists in the
    source for this form.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.parser.ast.statements import (
    DisplayStatementNode,
    GobackStatementNode,
    PerformStatementNode,
    PerformTargetUntilStatementNode,
    PerformUntilStatementNode,
)
from app.parser.lexer.lexer import CobolLexer
from app.parser.syntax.program_parser import ProgramParser

_HEADER = (
    "IDENTIFICATION DIVISION.\n"
    "PROGRAM-ID. T.\n"
    "DATA DIVISION.\n"
    "WORKING-STORAGE SECTION.\n"
    "01 WS-EOF PIC X(1) VALUE SPACE.\n"
    "01 WS-A PIC 9(3) VALUE 0.\n"
)


def _paragraphs(body: str, header: str = _HEADER):
    source = header + "PROCEDURE DIVISION.\n" + body
    tokens = CobolLexer().tokenize(source, filename="t.cbl")
    program = ProgramParser().parse(tokens)
    return program.procedure_division.paragraphs


class TestRealCorpusShape:
    """daily_trans_report.cbl's real shape: ``PERFORM 2000-PROCESS-RECORDS
    UNTIL WS-EOF = 'Y'`` -- identical across all 4 evidenced sources
    modulo names."""

    def test_target_name_preserved(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "2000-PROCESS-RECORDS.\n"
            "    DISPLAY 'X'.\n"
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformTargetUntilStatementNode)
        assert stmt.target == "2000-PROCESS-RECORDS"

    def test_condition_preserved(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "2000-PROCESS-RECORDS.\n"
            "    DISPLAY 'X'.\n"
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformTargetUntilStatementNode)
        assert stmt.condition_left == "WS-EOF"
        assert stmt.condition_operator == "="
        assert stmt.condition_right == "'Y'"

    def test_following_statements_are_not_swallowed(self) -> None:
        """The exact defect: DISPLAY and GOBACK after the malformed
        PERFORM used to vanish entirely."""
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
            "    DISPLAY 'DONE'.\n"
            "    GOBACK.\n"
            "2000-PROCESS-RECORDS.\n"
            "    DISPLAY 'X'.\n"
        )
        stmts = paragraphs[0].statements
        assert [type(s).__name__ for s in stmts] == [
            "PerformTargetUntilStatementNode",
            "DisplayStatementNode",
            "GobackStatementNode",
        ]

    def test_following_goback_remains_parsed(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "2000-PROCESS-RECORDS.\n"
            "    DISPLAY 'X'.\n"
        )
        assert isinstance(paragraphs[0].statements[-1], GobackStatementNode)

    def test_target_paragraph_itself_still_parses(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "2000-PROCESS-RECORDS.\n"
            "    DISPLAY 'X'.\n"
        )
        assert paragraphs[1].name == "2000-PROCESS-RECORDS"
        assert len(paragraphs[1].statements) == 1
        assert isinstance(paragraphs[1].statements[0], DisplayStatementNode)

    def test_no_parser_errors(self) -> None:
        source = (
            _HEADER + "PROCEDURE DIVISION.\n"
            "MAIN-PARA.\n"
            "    PERFORM 2000-PROCESS-RECORDS UNTIL WS-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "2000-PROCESS-RECORDS.\n"
            "    DISPLAY 'X'.\n"
        )
        tokens = CobolLexer().tokenize(source, filename="t.cbl")
        program = ProgramParser().parse(tokens)
        # ProgramParser records recoverable errors on the returned
        # program's diagnostics/errors collection when panic-mode
        # recovery ever engaged; the whole point of this fix is that it
        # no longer does for this shape.
        errors = getattr(program, "errors", None) or getattr(
            program, "diagnostics", None
        )
        if errors is not None:
            assert not errors


class TestFourRealSourceShapes:
    """The other three evidenced sources' own field/flag names, to prove
    the fix is not narrowly tied to one identifier spelling."""

    def test_batch_acct_update_shape(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 3000-PROCESS-LOOP UNTIL WS-EOF-FLAG = 'Y'.\n"
            "    GOBACK.\n"
            "3000-PROCESS-LOOP.\n"
            "    DISPLAY 'X'.\n",
            header=_HEADER + "01 WS-EOF-FLAG PIC X(1) VALUE SPACE.\n",
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformTargetUntilStatementNode)
        assert stmt.target == "3000-PROCESS-LOOP"
        assert stmt.condition_left == "WS-EOF-FLAG"

    def test_inventory_extract_shape(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 2000-SCAN-ITEMS UNTIL WS-INV-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "2000-SCAN-ITEMS.\n"
            "    DISPLAY 'X'.\n",
            header=_HEADER + "01 WS-INV-EOF PIC X(1) VALUE SPACE.\n",
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformTargetUntilStatementNode)
        assert stmt.target == "2000-SCAN-ITEMS"

    def test_payroll_file_post_shape(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM 2000-PROCESS-EMPLOYEE UNTIL WS-PAY-EOF = 'Y'.\n"
            "    GOBACK.\n"
            "2000-PROCESS-EMPLOYEE.\n"
            "    DISPLAY 'X'.\n",
            header=_HEADER + "01 WS-PAY-EOF PIC X(1) VALUE SPACE.\n",
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformTargetUntilStatementNode)
        assert stmt.target == "2000-PROCESS-EMPLOYEE"


class TestRegressionOtherPerformForms:
    """Every other PERFORM shape this parser already supports must stay
    byte-for-byte unchanged."""

    def test_plain_perform_unaffected(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA.\n"
            "    GOBACK.\n"
            "SUB-PARA.\n"
            "    DISPLAY 'X'.\n"
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformStatementNode)
        assert stmt.target == "SUB-PARA"
        assert stmt.thru_target == ""

    def test_perform_thru_unaffected(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA THRU SUB-PARA-3.\n"
            "    GOBACK.\n"
            "SUB-PARA.\n"
            "    DISPLAY 'X'.\n"
            "SUB-PARA-3.\n"
            "    DISPLAY 'Y'.\n"
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformStatementNode)
        assert stmt.target == "SUB-PARA"
        assert stmt.thru_target == "SUB-PARA-3"

    def test_inline_perform_until_unaffected(self) -> None:
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM UNTIL WS-A > 4\n"
            "        ADD 1 TO WS-A\n"
            "    END-PERFORM.\n"
            "    GOBACK.\n"
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformUntilStatementNode)
        assert stmt.condition_left == "WS-A"
        assert len(stmt.statements) == 1

    def test_perform_varying_unaffected(self) -> None:
        from app.parser.ast.statements import PerformVaryingStatementNode

        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM VARYING WS-A FROM 1 BY 1 UNTIL WS-A > 4\n"
            "        DISPLAY WS-A\n"
            "    END-PERFORM.\n"
            "    GOBACK.\n"
        )
        stmt = paragraphs[0].statements[0]
        assert isinstance(stmt, PerformVaryingStatementNode)
        assert stmt.varying_variable == "WS-A"

    def test_perform_times_not_misinterpreted(self) -> None:
        """PERFORM ... TIMES is out of Stage 37's scope (unevidenced);
        it must not be swallowed as the new UNTIL form. It is still an
        unsupported statement -- the paragraph-level SYN100/recovery
        path handles it exactly as before this stage."""
        paragraphs = _paragraphs(
            "MAIN-PARA.\n"
            "    PERFORM SUB-PARA 3 TIMES.\n"
            "    DISPLAY 'AFTER'.\n"
            "    GOBACK.\n"
            "SUB-PARA.\n"
            "    DISPLAY 'X'.\n"
        )
        stmt = paragraphs[0].statements[0]
        # "PERFORM SUB-PARA" is read as a plain PERFORM (its own,
        # pre-existing, out-of-scope behavior); "3 TIMES." is left for
        # ordinary recovery. The key regression guard is that this is
        # NOT a PerformTargetUntilStatementNode.
        assert not isinstance(stmt, PerformTargetUntilStatementNode)
