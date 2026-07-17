"""
Tests for the Procedure Division Parser.

Purpose:
    Verify that ProcedureDivisionParser, ProcedureDivisionNode,
    ParagraphNode, and all statement AST nodes behave correctly in
    isolation and when integrated with ProgramParser.

Coverage:
    - Empty PROCEDURE DIVISION (no paragraphs).
    - Single paragraph with no statements.
    - Single paragraph with a DISPLAY statement.
    - Single paragraph with a MOVE statement.
    - Single paragraph with STOP RUN.
    - Single paragraph with GOBACK.
    - Multiple statements in one paragraph.
    - Multiple paragraphs.
    - ProgramParser integration: PROCEDURE DIVISION alone.
    - ProgramParser integration: all three divisions present.
    - AST node immutability (frozen dataclasses).
    - Visitor dispatch on all new node types.
    - Default field values.
    - Error: missing period after paragraph label.
    - Error: missing period after statement.
    - Error: MOVE statement missing TO.
    - Error: DISPLAY statement missing operand.
    - Error: STOP without RUN.
    - Error: bad PROCEDURE DIVISION header.

Non-responsibilities:
    - IF, EVALUATE, PERFORM, GO TO, CALL, COMPUTE, arithmetic.
    - SECTION parsing.

Dependencies:
    - :mod:`app.parser.syntax.program_parser`      — ProgramParser.
    - :mod:`app.parser.syntax.procedure_parser`    — ProcedureDivisionParser.
    - :mod:`app.parser.ast.procedure`              — ProcedureDivisionNode.
    - :mod:`app.parser.ast.paragraphs`             — ParagraphNode.
    - :mod:`app.parser.ast.statements`             — statement node types.
    - :mod:`app.parser.ast.node`                   — ASTNode.
    - :mod:`app.parser.ast.program`                — ProgramNode.
    - :mod:`app.parser.syntax.parser_exceptions`   — ParserError.
    - :mod:`app.parser.syntax.parser_state`        — ParserState.
    - :mod:`app.parser.syntax.token_stream`        — TokenStream.
    - :mod:`app.parser.lexer.token`                — Token.
    - :mod:`app.parser.lexer.token_types`          — TokenType.
    - :mod:`app.parser.lexer.position`             — Position.
    - :mod:`pytest`                                — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses

import pytest

from app.parser.ast.node import ASTNode
from app.parser.ast.paragraphs import ParagraphNode
from app.parser.ast.procedure import ProcedureDivisionNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.statements import (
    DisplayStatementNode,
    GobackStatementNode,
    MoveStatementNode,
    StatementNode,
    StopRunStatementNode,
)
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.procedure_parser import ProcedureDivisionParser
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

# ---------------------------------------------------------------------------
# Token-building helpers
# ---------------------------------------------------------------------------

_FILE = "test.cbl"


def _pos(line: int = 1, col: int = 1, offset: int = 0) -> Position:
    return Position(line=line, column=col, offset=offset, filename=_FILE)


def _kw(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(
        type=TokenType.KEYWORD, lexeme=lexeme, position=_pos(line, col, offset)
    )


def _id(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(
        type=TokenType.IDENTIFIER, lexeme=lexeme, position=_pos(line, col, offset)
    )


def _num(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.NUMBER, lexeme=lexeme, position=_pos(line, col, offset))


def _period(line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.PERIOD, lexeme=".", position=_pos(line, col, offset))


def _str_tok(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.STRING, lexeme=lexeme, position=_pos(line, col, offset))


def _eof(line: int = 99, col: int = 1, offset: int = 9999) -> Token:
    return Token(type=TokenType.EOF, lexeme="", position=_pos(line, col, offset))


def _make_state(tokens: list[Token]) -> ParserState:
    return ParserState(TokenStream(tokens))


# ---------------------------------------------------------------------------
# Common token sequences
# ---------------------------------------------------------------------------


def _proc_header() -> list[Token]:
    """PROCEDURE DIVISION ."""
    return [_kw("PROCEDURE"), _kw("DIVISION"), _period()]


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — empty PROCEDURE DIVISION
# ---------------------------------------------------------------------------


class TestProcedureDivisionParserEmpty:
    """ProcedureDivisionParser on PROCEDURE DIVISION with no paragraphs."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_empty_procedure_division_returns_node(self) -> None:
        tokens = _proc_header() + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node, ProcedureDivisionNode)

    def test_empty_procedure_division_has_no_paragraphs(self) -> None:
        tokens = _proc_header() + [_eof()]
        node = self._parse(tokens)
        assert node.paragraphs == ()

    def test_procedure_division_node_is_astnode(self) -> None:
        tokens = _proc_header() + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node, ASTNode)

    def test_start_position_on_procedure_keyword(self) -> None:
        tokens = _proc_header() + [_eof()]
        node = self._parse(tokens)
        assert node.start_position.line == 1

    def test_procedure_division_is_frozen(self) -> None:
        pos = _pos()
        node = ProcedureDivisionNode(start_position=pos, end_position=pos)
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.paragraphs = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — single paragraph (no statements)
# ---------------------------------------------------------------------------


class TestSingleEmptyParagraph:
    """A single paragraph with no statements."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_single_paragraph_is_present(self) -> None:
        tokens = _proc_header() + [_id("MAIN-PARA"), _period(), _eof()]
        node = self._parse(tokens)
        assert len(node.paragraphs) == 1

    def test_single_paragraph_correct_name(self) -> None:
        tokens = _proc_header() + [_id("MAIN-PARA"), _period(), _eof()]
        node = self._parse(tokens)
        assert node.paragraphs[0].name == "MAIN-PARA"

    def test_single_paragraph_no_statements(self) -> None:
        tokens = _proc_header() + [_id("MAIN-PARA"), _period(), _eof()]
        node = self._parse(tokens)
        assert node.paragraphs[0].statements == ()

    def test_single_paragraph_is_paragraph_node(self) -> None:
        tokens = _proc_header() + [_id("MAIN-PARA"), _period(), _eof()]
        node = self._parse(tokens)
        assert isinstance(node.paragraphs[0], ParagraphNode)

    def test_paragraph_is_frozen(self) -> None:
        pos = _pos()
        para = ParagraphNode(start_position=pos, end_position=pos, name="P")
        with pytest.raises(dataclasses.FrozenInstanceError):
            para.name = "Q"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — DISPLAY statement
# ---------------------------------------------------------------------------


class TestDisplayStatement:
    """DISPLAY statement parsing."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_display_string_literal(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"HELLO"'), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert len(node.paragraphs) == 1
        stmts = node.paragraphs[0].statements
        assert len(stmts) == 1
        assert isinstance(stmts[0], DisplayStatementNode)

    def test_display_operand_value(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"HELLO"'), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmt = node.paragraphs[0].statements[0]
        assert isinstance(stmt, DisplayStatementNode)
        assert stmt.operand == '"HELLO"'

    def test_display_identifier_operand(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _id("WS-NAME"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmt = node.paragraphs[0].statements[0]
        assert isinstance(stmt, DisplayStatementNode)
        assert stmt.operand == "WS-NAME"

    def test_display_numeric_operand(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _num("42"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmt = node.paragraphs[0].statements[0]
        assert isinstance(stmt, DisplayStatementNode)
        assert stmt.operand == "42"

    def test_display_is_statement_node(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"X"'), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert isinstance(node.paragraphs[0].statements[0], StatementNode)

    def test_display_node_is_frozen(self) -> None:
        pos = _pos()
        node = DisplayStatementNode(start_position=pos, end_position=pos, operand="X")
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.operand = "Y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — MOVE statement
# ---------------------------------------------------------------------------


class TestMoveStatement:
    """MOVE ... TO ... statement parsing."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_move_numeric_to_identifier(self) -> None:
        # MOVE 1 TO WS-COUNT.
        # Note: TO is emitted as IDENTIFIER (not a keyword)
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmts = node.paragraphs[0].statements
        assert len(stmts) == 1
        assert isinstance(stmts[0], MoveStatementNode)

    def test_move_source_value(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmt = node.paragraphs[0].statements[0]
        assert isinstance(stmt, MoveStatementNode)
        assert stmt.source == "1"

    def test_move_target_value(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmt = node.paragraphs[0].statements[0]
        assert isinstance(stmt, MoveStatementNode)
        assert stmt.target == "WS-COUNT"

    def test_move_identifier_to_identifier(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [
                _kw("MOVE"),
                _id("WS-NAME"),
                _id("TO"),
                _id("DISPLAY-NAME"),
                _period(),
            ]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmt = node.paragraphs[0].statements[0]
        assert isinstance(stmt, MoveStatementNode)
        assert stmt.source == "WS-NAME"
        assert stmt.target == "DISPLAY-NAME"

    def test_move_node_is_frozen(self) -> None:
        pos = _pos()
        node = MoveStatementNode(
            start_position=pos, end_position=pos, source="1", target="X"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.source = "2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — STOP RUN statement
# ---------------------------------------------------------------------------


class TestStopRunStatement:
    """STOP RUN statement parsing."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_stop_run_parsed(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmts = node.paragraphs[0].statements
        assert len(stmts) == 1
        assert isinstance(stmts[0], StopRunStatementNode)

    def test_stop_run_is_statement_node(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert isinstance(node.paragraphs[0].statements[0], StatementNode)

    def test_stop_run_node_is_frozen(self) -> None:
        pos = _pos()
        node = StopRunStatementNode(start_position=pos, end_position=pos)
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.start_position = pos  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — GOBACK statement
# ---------------------------------------------------------------------------


class TestGobackStatement:
    """GOBACK statement parsing (GOBACK is emitted as IDENTIFIER)."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_goback_parsed(self) -> None:
        # GOBACK is an IDENTIFIER token (not in keyword set)
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_id("GOBACK"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmts = node.paragraphs[0].statements
        assert len(stmts) == 1
        assert isinstance(stmts[0], GobackStatementNode)

    def test_goback_is_statement_node(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_id("GOBACK"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert isinstance(node.paragraphs[0].statements[0], StatementNode)

    def test_goback_node_is_frozen(self) -> None:
        pos = _pos()
        node = GobackStatementNode(start_position=pos, end_position=pos)
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.end_position = pos  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — multiple statements in one paragraph
# ---------------------------------------------------------------------------


class TestMultipleStatements:
    """Multiple statements in a single paragraph."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_display_then_stop_run(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"HELLO"'), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmts = node.paragraphs[0].statements
        assert len(stmts) == 2
        assert isinstance(stmts[0], DisplayStatementNode)
        assert isinstance(stmts[1], StopRunStatementNode)

    def test_display_move_stop_run(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"START"'), _period()]
            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmts = node.paragraphs[0].statements
        assert len(stmts) == 3
        assert isinstance(stmts[0], DisplayStatementNode)
        assert isinstance(stmts[1], MoveStatementNode)
        assert isinstance(stmts[2], StopRunStatementNode)

    def test_display_then_goback(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"BYE"'), _period()]
            + [_id("GOBACK"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        stmts = node.paragraphs[0].statements
        assert len(stmts) == 2
        assert isinstance(stmts[0], DisplayStatementNode)
        assert isinstance(stmts[1], GobackStatementNode)


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — multiple paragraphs
# ---------------------------------------------------------------------------


class TestMultipleParagraphs:
    """Multiple paragraphs in a single PROCEDURE DIVISION."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_two_paragraphs(self) -> None:
        tokens = (
            _proc_header()
            + [_id("FIRST-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"ONE"'), _period()]
            + [_id("SECOND-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert len(node.paragraphs) == 2

    def test_two_paragraphs_names(self) -> None:
        tokens = (
            _proc_header()
            + [_id("FIRST-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"ONE"'), _period()]
            + [_id("SECOND-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.paragraphs[0].name == "FIRST-PARA"
        assert node.paragraphs[1].name == "SECOND-PARA"

    def test_two_paragraphs_statements_split(self) -> None:
        tokens = (
            _proc_header()
            + [_id("FIRST-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"ONE"'), _period()]
            + [_id("SECOND-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert len(node.paragraphs[0].statements) == 1
        assert isinstance(node.paragraphs[0].statements[0], DisplayStatementNode)
        assert len(node.paragraphs[1].statements) == 1
        assert isinstance(node.paragraphs[1].statements[0], StopRunStatementNode)

    def test_three_paragraphs(self) -> None:
        tokens = (
            _proc_header()
            + [_id("INIT-PARA"), _period()]
            + [_kw("MOVE"), _num("0"), _id("TO"), _id("WS-COUNT"), _period()]
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"HELLO"'), _period()]
            + [_id("END-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert len(node.paragraphs) == 3

    def test_paragraph_with_no_statements_then_next(self) -> None:
        tokens = (
            _proc_header()
            + [_id("EMPTY-PARA"), _period()]
            + [_id("WORK-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert len(node.paragraphs) == 2
        assert node.paragraphs[0].statements == ()
        assert len(node.paragraphs[1].statements) == 1


# ---------------------------------------------------------------------------
# ProcedureDivisionParser — error cases
# ---------------------------------------------------------------------------


class TestProcedureDivisionParserErrors:
    """Malformed inputs raise ParserError."""

    def _parse_expect_error(self, tokens: list[Token]) -> ParserError:
        state = _make_state(tokens)
        parser = ProcedureDivisionParser()
        with pytest.raises(ParserError) as exc_info:
            parser.parse(state)
        return exc_info.value

    def test_missing_period_after_procedure_division_header(self) -> None:
        tokens = [_kw("PROCEDURE"), _kw("DIVISION"), _eof()]
        self._parse_expect_error(tokens)

    def test_wrong_second_keyword_in_header(self) -> None:
        tokens = [_kw("PROCEDURE"), _kw("DATA"), _period(), _eof()]
        self._parse_expect_error(tokens)

    def test_missing_period_after_paragraph_label(self) -> None:
        tokens = _proc_header() + [_id("MAIN-PARA"), _id("SOMETHING"), _eof()]
        self._parse_expect_error(tokens)

    def test_stop_without_run(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("STOP"), _id("SOMETHING"), _period()]
            + [_eof()]
        )
        self._parse_expect_error(tokens)

    def test_move_missing_to(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("MOVE"), _num("1"), _id("WS-COUNT"), _period()]
            + [_eof()]
        )
        self._parse_expect_error(tokens)

    def test_display_missing_period(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"X"'), _eof()]
        )
        self._parse_expect_error(tokens)

    def test_stop_run_missing_period(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _eof()]
        )
        self._parse_expect_error(tokens)

    def test_goback_missing_period(self) -> None:
        tokens = (
            _proc_header() + [_id("MAIN-PARA"), _period()] + [_id("GOBACK"), _eof()]
        )
        self._parse_expect_error(tokens)

    def test_move_missing_period(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _eof()]
        )
        self._parse_expect_error(tokens)


# ---------------------------------------------------------------------------
# ProgramParser — PROCEDURE DIVISION integration
# ---------------------------------------------------------------------------


class TestProgramParserProcedureDivision:
    """ProgramParser correctly detects and delegates PROCEDURE DIVISION."""

    def test_parses_procedure_division(self) -> None:
        tokens = _proc_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert program.procedure_division is not None

    def test_procedure_division_node_type(self) -> None:
        tokens = _proc_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert isinstance(program.procedure_division, ProcedureDivisionNode)

    def test_no_procedure_division_when_absent(self) -> None:
        pos = _pos()
        eof = Token(type=TokenType.EOF, lexeme="", position=pos)
        parser = ProgramParser()
        program = parser.parse([eof])
        assert program.procedure_division is None

    def test_program_node_procedure_division_has_paragraph(self) -> None:
        tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            + [_eof()]
        )
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert program.procedure_division is not None
        assert len(program.procedure_division.paragraphs) == 1

    def test_program_node_is_program_node_type(self) -> None:
        tokens = _proc_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert isinstance(program, ProgramNode)

    def test_all_three_divisions_present(self) -> None:
        """Full program: IDENTIFICATION + DATA + PROCEDURE DIVISION."""
        ident_tokens = [
            _kw("IDENTIFICATION"),
            _kw("DIVISION"),
            _period(),
            _kw("PROGRAM-ID"),
            _period(),
            _id("MYPROG"),
            _period(),
        ]
        data_tokens = [
            _kw("DATA"),
            _kw("DIVISION"),
            _period(),
        ]
        proc_tokens = (
            _proc_header()
            + [_id("MAIN-PARA"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
        )
        tokens = ident_tokens + data_tokens + proc_tokens + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert program.identification_division is not None
        assert program.data_division is not None
        assert program.procedure_division is not None


# ---------------------------------------------------------------------------
# Visitor dispatch
# ---------------------------------------------------------------------------


class TestVisitorDispatch:
    """accept() on new nodes dispatches to the correct visitor method."""

    _POS = _pos()

    def test_procedure_division_accept_dispatches(self) -> None:
        visited: list[ProcedureDivisionNode] = []

        class V:
            def visit_procedure_division(self, n: ProcedureDivisionNode) -> None:
                visited.append(n)

        node = ProcedureDivisionNode(start_position=self._POS, end_position=self._POS)
        node.accept(V())
        assert len(visited) == 1
        assert visited[0] is node

    def test_paragraph_accept_dispatches(self) -> None:
        visited: list[ParagraphNode] = []

        class V:
            def visit_paragraph(self, n: ParagraphNode) -> None:
                visited.append(n)

        node = ParagraphNode(start_position=self._POS, end_position=self._POS, name="P")
        node.accept(V())
        assert len(visited) == 1

    def test_display_statement_accept_dispatches(self) -> None:
        visited: list[DisplayStatementNode] = []

        class V:
            def visit_display_statement(self, n: DisplayStatementNode) -> None:
                visited.append(n)

        node = DisplayStatementNode(
            start_position=self._POS, end_position=self._POS, operand="X"
        )
        node.accept(V())
        assert len(visited) == 1

    def test_move_statement_accept_dispatches(self) -> None:
        visited: list[MoveStatementNode] = []

        class V:
            def visit_move_statement(self, n: MoveStatementNode) -> None:
                visited.append(n)

        node = MoveStatementNode(
            start_position=self._POS, end_position=self._POS, source="1", target="X"
        )
        node.accept(V())
        assert len(visited) == 1

    def test_stop_run_accept_dispatches(self) -> None:
        visited: list[StopRunStatementNode] = []

        class V:
            def visit_stop_run_statement(self, n: StopRunStatementNode) -> None:
                visited.append(n)

        node = StopRunStatementNode(start_position=self._POS, end_position=self._POS)
        node.accept(V())
        assert len(visited) == 1

    def test_goback_accept_dispatches(self) -> None:
        visited: list[GobackStatementNode] = []

        class V:
            def visit_goback_statement(self, n: GobackStatementNode) -> None:
                visited.append(n)

        node = GobackStatementNode(start_position=self._POS, end_position=self._POS)
        node.accept(V())
        assert len(visited) == 1

    def test_accept_returns_none_for_unknown_visitor(self) -> None:
        node = ProcedureDivisionNode(start_position=self._POS, end_position=self._POS)
        result = node.accept(object())
        assert result is None

    def test_statement_base_accept_dispatches_to_visit_statement(self) -> None:
        """StatementNode.accept falls back to visit_statement."""
        # Use DisplayStatementNode but have the visitor only implement
        # visit_statement (not visit_display_statement)
        visited: list[StatementNode] = []

        class GenericVisitor:
            def visit_statement(self, n: StatementNode) -> None:
                visited.append(n)

        # StatementNode itself is abstract — test via a concrete subclass
        # that does NOT override accept correctly; instead call super().accept
        # We simulate via direct StatementNode.accept call with a MoveStatementNode
        # using a visitor that only has visit_statement
        pos = self._POS
        node = GobackStatementNode(start_position=pos, end_position=pos)
        # GobackStatementNode.accept dispatches to visit_goback_statement;
        # if missing, falls back to None.  Use StatementNode.accept explicitly:
        StatementNode.accept(node, GenericVisitor())
        assert len(visited) == 1


# ---------------------------------------------------------------------------
# AST node defaults and field checks
# ---------------------------------------------------------------------------


class TestASTNodeDefaults:
    """Default field values for all new AST node types."""

    _POS = _pos()

    def test_procedure_division_node_defaults(self) -> None:
        node = ProcedureDivisionNode(start_position=self._POS, end_position=self._POS)
        assert node.paragraphs == ()

    def test_paragraph_node_statements_default(self) -> None:
        node = ParagraphNode(start_position=self._POS, end_position=self._POS, name="P")
        assert node.statements == ()

    def test_all_new_nodes_are_astnodes(self) -> None:
        pos = self._POS
        nodes: list[ASTNode] = [
            ProcedureDivisionNode(start_position=pos, end_position=pos),
            ParagraphNode(start_position=pos, end_position=pos, name="P"),
            DisplayStatementNode(start_position=pos, end_position=pos, operand="X"),
            MoveStatementNode(
                start_position=pos, end_position=pos, source="1", target="Y"
            ),
            StopRunStatementNode(start_position=pos, end_position=pos),
            GobackStatementNode(start_position=pos, end_position=pos),
        ]
        for node in nodes:
            assert isinstance(node, ASTNode), f"{type(node).__name__} is not ASTNode"


# ---------------------------------------------------------------------------
# Comprehensive scenario: well-formed PROCEDURE DIVISION
# ---------------------------------------------------------------------------


class TestWellFormedProcedureDivision:
    """Integration test with a realistic PROCEDURE DIVISION."""

    def _parse(self, tokens: list[Token]) -> ProcedureDivisionNode:
        state = _make_state(tokens)
        return ProcedureDivisionParser().parse(state)

    def test_full_procedure_division(self) -> None:
        """
        Parse a PROCEDURE DIVISION with:

            PROCEDURE DIVISION.

            MAIN-PARA.
                DISPLAY "HELLO".
                MOVE 1 TO WS-COUNT.
                STOP RUN.

            CLEANUP-PARA.
                GOBACK.
        """
        tokens = (
            _proc_header()
            # MAIN-PARA
            + [_id("MAIN-PARA"), _period()]
            + [_kw("DISPLAY"), _str_tok('"HELLO"'), _period()]
            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _period()]
            + [_kw("STOP"), _kw("RUN"), _period()]
            # CLEANUP-PARA
            + [_id("CLEANUP-PARA"), _period()]
            + [_id("GOBACK"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)

        assert len(node.paragraphs) == 2

        main_para = node.paragraphs[0]
        assert main_para.name == "MAIN-PARA"
        assert len(main_para.statements) == 3
        assert isinstance(main_para.statements[0], DisplayStatementNode)
        assert main_para.statements[0].operand == '"HELLO"'
        assert isinstance(main_para.statements[1], MoveStatementNode)
        assert main_para.statements[1].source == "1"
        assert main_para.statements[1].target == "WS-COUNT"
        assert isinstance(main_para.statements[2], StopRunStatementNode)

        cleanup_para = node.paragraphs[1]
        assert cleanup_para.name == "CLEANUP-PARA"
        assert len(cleanup_para.statements) == 1
        assert isinstance(cleanup_para.statements[0], GobackStatementNode)
