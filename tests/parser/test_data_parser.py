"""
Tests for the Data Division Parser.

Purpose:
    Verify that the DataDivisionParser, WorkingStorageSectionNode,
    DataDivisionNode, and related data-item AST nodes behave correctly
    in isolation and when integrated with ProgramParser.

Coverage:
    - Empty DATA DIVISION (no sections).
    - Empty WORKING-STORAGE SECTION (no items).
    - Single 01-level group declaration.
    - Single 01-level elementary (with PIC clause).
    - Nested 01/05 declarations.
    - 77-level standalone elementary declaration.
    - 88-level condition-name declaration.
    - PIC clause with parenthesised size: X(30), 9(5).
    - VALUE clause on elementary and condition-name items.
    - Missing period after level-number item.
    - Invalid level number (e.g. 99).
    - ProgramParser detects and delegates DATA DIVISION.
    - ProgramNode.data_division populated correctly.
    - DataDivisionNode is an ASTNode.
    - All AST nodes are frozen dataclasses (immutable).
    - Visitor dispatch on new nodes.

Non-responsibilities:
    - FILE SECTION, LINKAGE SECTION, LOCAL-STORAGE parsing.
    - OCCURS, REDEFINES, COMP semantics.

Dependencies:
    - :mod:`app.parser.syntax.program_parser`     — ProgramParser.
    - :mod:`app.parser.syntax.data_parser`        — DataDivisionParser.
    - :mod:`app.parser.ast.data`                  — DataDivisionNode.
    - :mod:`app.parser.ast.working_storage`       — WorkingStorageSectionNode.
    - :mod:`app.parser.ast.data_items`            — item node types.
    - :mod:`app.parser.ast.node`                  — ASTNode.
    - :mod:`app.parser.ast.program`               — ProgramNode.
    - :mod:`app.parser.syntax.parser_exceptions`  — ParserError.
    - :mod:`app.parser.syntax.parser_state`       — ParserState.
    - :mod:`app.parser.syntax.token_stream`       — TokenStream.
    - :mod:`app.parser.lexer.token`               — Token.
    - :mod:`app.parser.lexer.token_types`         — TokenType.
    - :mod:`app.parser.lexer.position`            — Position.
    - :mod:`pytest`                               — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import dataclasses

import pytest

from app.parser.ast.data import DataDivisionNode
from app.parser.ast.data_items import (
    ConditionNameNode,
    DataItemNode,
    ElementaryItemNode,
    GroupItemNode,
)
from app.parser.ast.node import ASTNode
from app.parser.ast.program import ProgramNode
from app.parser.ast.working_storage import WorkingStorageSectionNode
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.data_parser import DataDivisionParser
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState
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


def _lparen(line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.LPAREN, lexeme="(", position=_pos(line, col, offset))


def _rparen(line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.RPAREN, lexeme=")", position=_pos(line, col, offset))


def _str_tok(lexeme: str, line: int = 1, col: int = 1, offset: int = 0) -> Token:
    return Token(type=TokenType.STRING, lexeme=lexeme, position=_pos(line, col, offset))


def _eof(line: int = 99, col: int = 1, offset: int = 999) -> Token:
    return Token(type=TokenType.EOF, lexeme="", position=_pos(line, col, offset))


def _make_state(tokens: list[Token]) -> ParserState:
    return ParserState(TokenStream(tokens))


# ---------------------------------------------------------------------------
# Common token sequences
# ---------------------------------------------------------------------------


def _data_header() -> list[Token]:
    """DATA DIVISION ."""
    return [_kw("DATA"), _kw("DIVISION"), _period()]


def _ws_header() -> list[Token]:
    """WORKING-STORAGE SECTION ."""
    return [_kw("WORKING-STORAGE"), _kw("SECTION"), _period()]


def _pic_clause(name: str) -> list[Token]:
    """PIC <name> (without trailing period)."""
    return [_kw("PIC"), _id(name)]


def _pic_clause_with_parens(prefix: str, size: str) -> list[Token]:
    """PIC X(30) → PIC X ( 30 ) (without trailing period)."""
    return [_kw("PIC"), _id(prefix), _lparen(), _num(size), _rparen()]


# ---------------------------------------------------------------------------
# DataDivisionParser — empty DATA DIVISION
# ---------------------------------------------------------------------------


class TestDataDivisionParserEmpty:
    """DataDivisionParser on DATA DIVISION with no sections."""

    def _parse(self, tokens: list[Token]) -> DataDivisionNode:
        state = _make_state(tokens)
        parser = DataDivisionParser()
        return parser.parse(state)

    def test_empty_data_division_returns_node(self) -> None:
        tokens = _data_header() + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node, DataDivisionNode)

    def test_empty_data_division_has_no_working_storage(self) -> None:
        tokens = _data_header() + [_eof()]
        node = self._parse(tokens)
        assert node.working_storage is None

    def test_data_division_node_is_astnode(self) -> None:
        tokens = _data_header() + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node, ASTNode)

    def test_start_position_on_data_keyword(self) -> None:
        tokens = _data_header() + [_eof()]
        node = self._parse(tokens)
        assert node.start_position.line == 1

    def test_data_division_is_frozen(self) -> None:
        pos = _pos()
        node = DataDivisionNode(start_position=pos, end_position=pos)
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.working_storage = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DataDivisionParser — WORKING-STORAGE SECTION (empty)
# ---------------------------------------------------------------------------


class TestWorkingStorageSectionEmpty:
    """Empty WORKING-STORAGE SECTION produces an empty items tuple."""

    def _parse(self, tokens: list[Token]) -> DataDivisionNode:
        state = _make_state(tokens)
        return DataDivisionParser().parse(state)

    def test_working_storage_section_present(self) -> None:
        tokens = _data_header() + _ws_header() + [_eof()]
        node = self._parse(tokens)
        assert node.working_storage is not None

    def test_working_storage_section_is_correct_type(self) -> None:
        tokens = _data_header() + _ws_header() + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node.working_storage, WorkingStorageSectionNode)

    def test_empty_working_storage_has_no_items(self) -> None:
        tokens = _data_header() + _ws_header() + [_eof()]
        node = self._parse(tokens)
        assert node.working_storage is not None
        assert node.working_storage.items == ()

    def test_working_storage_node_is_astnode(self) -> None:
        tokens = _data_header() + _ws_header() + [_eof()]
        node = self._parse(tokens)
        assert isinstance(node.working_storage, ASTNode)

    def test_working_storage_section_is_frozen(self) -> None:
        pos = _pos()
        ws = WorkingStorageSectionNode(start_position=pos, end_position=pos)
        with pytest.raises(dataclasses.FrozenInstanceError):
            ws.items = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DataDivisionParser — single 01 group declaration
# ---------------------------------------------------------------------------


class TestGroupItemDeclaration:
    """01-level group item (no PIC) is parsed as GroupItemNode."""

    def _parse(self, tokens: list[Token]) -> DataDivisionNode:
        state = _make_state(tokens)
        return DataDivisionParser().parse(state)

    def test_single_01_group_item(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        assert len(node.working_storage.items) == 1

    def test_01_item_is_group_node(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, GroupItemNode)

    def test_01_item_level_and_name(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert item.level == 1
        assert item.name == "CUSTOMER-REC"

    def test_group_item_is_data_item_node(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, DataItemNode)

    def test_group_item_is_frozen(self) -> None:
        pos = _pos()
        gn = GroupItemNode(start_position=pos, end_position=pos, level=1, name="REC")
        with pytest.raises(dataclasses.FrozenInstanceError):
            gn.name = "X"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DataDivisionParser — elementary (with PIC) declaration
# ---------------------------------------------------------------------------


class TestElementaryItemDeclaration:
    """Elementary items with PIC clauses are parsed as ElementaryItemNode."""

    def _parse(self, tokens: list[Token]) -> DataDivisionNode:
        state = _make_state(tokens)
        return DataDivisionParser().parse(state)

    def test_05_elementary_with_pic(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("05"), _id("CUSTOMER-ID")]
            + _pic_clause("9")
            + [_period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        assert len(node.working_storage.items) == 1
        item = node.working_storage.items[0]
        assert isinstance(item, ElementaryItemNode)
        assert item.level == 5
        assert item.name == "CUSTOMER-ID"
        assert "9" in item.picture

    def test_pic_clause_with_parentheses(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("05"), _id("CUSTOMER-NAME")]
            + _pic_clause_with_parens("X", "30")
            + [_period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, ElementaryItemNode)
        assert "X" in item.picture
        assert "30" in item.picture

    def test_77_elementary_item(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("77"), _id("WS-COUNT")]
            + _pic_clause("9")
            + [_period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, ElementaryItemNode)
        assert item.level == 77
        assert item.name == "WS-COUNT"

    def test_elementary_item_no_value(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("05"), _id("WS-FLAG")]
            + _pic_clause("X")
            + [_period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, ElementaryItemNode)
        assert item.value is None

    def test_elementary_item_with_value(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("05"), _id("WS-FLAG")]
            + _pic_clause("X")
            + [_kw("VALUE"), _str_tok("'N'"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, ElementaryItemNode)
        assert item.value == "'N'"

    def test_elementary_item_is_frozen(self) -> None:
        pos = _pos()
        en = ElementaryItemNode(
            start_position=pos, end_position=pos, level=5, name="X", picture="9"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            en.picture = "X"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DataDivisionParser — nested 01/05 declarations
# ---------------------------------------------------------------------------


class TestNestedItemDeclarations:
    """Nested 01/05 items are all emitted as flat top-level items."""

    def _parse(self, tokens: list[Token]) -> DataDivisionNode:
        state = _make_state(tokens)
        return DataDivisionParser().parse(state)

    def test_01_group_with_two_05_items(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            + [_num("05"), _id("CUSTOMER-ID")]
            + _pic_clause_with_parens("9", "5")
            + [_period()]
            + [_num("05"), _id("CUSTOMER-NAME")]
            + _pic_clause_with_parens("X", "30")
            + [_period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        assert len(node.working_storage.items) == 3

    def test_nested_items_correct_types(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            + [_num("05"), _id("CUSTOMER-ID")]
            + _pic_clause_with_parens("9", "5")
            + [_period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        items = node.working_storage.items
        assert isinstance(items[0], GroupItemNode)
        assert isinstance(items[1], ElementaryItemNode)

    def test_nested_items_levels(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("REC"), _period()]
            + [_num("05"), _id("FIELD")]
            + _pic_clause("9")
            + [_period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        items = node.working_storage.items
        assert items[0].level == 1
        assert items[1].level == 5


# ---------------------------------------------------------------------------
# DataDivisionParser — 88-level condition name
# ---------------------------------------------------------------------------


class TestConditionNameDeclaration:
    """88-level items are parsed as ConditionNameNode."""

    def _parse(self, tokens: list[Token]) -> DataDivisionNode:
        state = _make_state(tokens)
        return DataDivisionParser().parse(state)

    def test_88_condition_name_with_value(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("88"), _id("END-OF-FILE"), _kw("VALUE"), _str_tok("'Y'"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        assert len(node.working_storage.items) == 1
        item = node.working_storage.items[0]
        assert isinstance(item, ConditionNameNode)
        assert item.level == 88
        assert item.name == "END-OF-FILE"
        assert item.value == "'Y'"

    def test_88_condition_name_no_value(self) -> None:
        """88-level without VALUE clause stores None for value."""
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("88"), _id("END-OF-FILE"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, ConditionNameNode)
        assert item.value is None

    def test_condition_name_is_data_item_node(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("88"), _id("FLAG-ON"), _kw("VALUE"), _str_tok("'Y'"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        item = node.working_storage.items[0]
        assert isinstance(item, DataItemNode)

    def test_condition_name_is_frozen(self) -> None:
        pos = _pos()
        cn = ConditionNameNode(
            start_position=pos, end_position=pos, level=88, name="FLAG", value="'Y'"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cn.value = "N"  # type: ignore[misc]

    def test_88_after_05_item(self) -> None:
        """88-level condition after a 05-level item is parsed correctly."""
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("05"), _id("WS-STATUS")]
            + _pic_clause("X")
            + [_period()]
            + [_num("88"), _id("STATUS-OK"), _kw("VALUE"), _str_tok("'Y'"), _period()]
            + [_eof()]
        )
        node = self._parse(tokens)
        assert node.working_storage is not None
        items = node.working_storage.items
        assert len(items) == 2
        assert isinstance(items[0], ElementaryItemNode)
        assert isinstance(items[1], ConditionNameNode)


# ---------------------------------------------------------------------------
# DataDivisionParser — error cases
# ---------------------------------------------------------------------------


class TestDataDivisionParserErrors:
    """Fatal errors raise ParserError; recoverable errors record diagnostics.

    After TASK-017, item-level errors (invalid level, missing data-name,
    missing period at item end) are recovered via SyntaxDiagnostic.
    Division/section header errors remain fatal.
    """

    def _parse_expect_error(self, tokens: list[Token]) -> ParserError:
        state = _make_state(tokens)
        parser = DataDivisionParser()
        with pytest.raises(ParserError) as exc_info:
            parser.parse(state)
        return exc_info.value

    def test_missing_period_after_data_division_header(self) -> None:
        """DATA DIVISION <eof> → missing period after header."""
        tokens = [_kw("DATA"), _kw("DIVISION"), _eof()]
        self._parse_expect_error(tokens)

    def test_missing_period_after_working_storage_header(self) -> None:
        """WORKING-STORAGE SECTION <eof> → missing period."""
        tokens = _data_header() + [_kw("WORKING-STORAGE"), _kw("SECTION"), _eof()]
        self._parse_expect_error(tokens)

    def test_missing_period_after_data_item(self) -> None:
        """01 CUSTOMER-REC <eof> → missing period → diagnostic recorded.

        After TASK-017 the parser records a SyntaxDiagnostic and continues.
        """
        tokens = (
            _data_header() + _ws_header() + [_num("01"), _id("CUSTOMER-REC"), _eof()]
        )
        state = _make_state(tokens)
        parser = DataDivisionParser()
        parser.parse(state)
        assert state.has_errors

    def test_missing_period_after_elementary_item(self) -> None:
        """05 CUSTOMER-ID PIC 9 <eof> → missing period → diagnostic recorded.

        After TASK-017 the parser records a SyntaxDiagnostic and continues.
        """
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("05"), _id("CUSTOMER-ID")]
            + _pic_clause("9")
            + [_eof()]
        )
        state = _make_state(tokens)
        parser = DataDivisionParser()
        parser.parse(state)
        assert state.has_errors

    def test_invalid_level_number(self) -> None:
        """Level 99 is not a valid COBOL level number → diagnostic recorded.

        After TASK-017 the parser records a SyntaxDiagnostic and continues.
        """
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("99"), _id("INVALID"), _period()]
            + [_eof()]
        )
        state = _make_state(tokens)
        parser = DataDivisionParser()
        parser.parse(state)
        assert state.has_errors
        diag_messages = " ".join(d.message for d in state.diagnostics)
        assert "99" in diag_messages or "invalid" in diag_messages.lower()

    def test_missing_division_keyword(self) -> None:
        """DATA <period> → missing DIVISION keyword."""
        tokens = [_kw("DATA"), _period(), _eof()]
        self._parse_expect_error(tokens)

    def test_wrong_keyword_instead_of_division(self) -> None:
        """DATA ENVIRONMENT . → wrong second keyword."""
        tokens = [_kw("DATA"), _kw("ENVIRONMENT"), _period(), _eof()]
        self._parse_expect_error(tokens)

    def test_missing_data_name_after_level(self) -> None:
        """01 . → missing data-name → diagnostic recorded.

        After TASK-017 the parser records a SyntaxDiagnostic and continues.
        """
        tokens = _data_header() + _ws_header() + [_num("01"), _period()] + [_eof()]
        state = _make_state(tokens)
        parser = DataDivisionParser()
        parser.parse(state)
        assert state.has_errors


# ---------------------------------------------------------------------------
# ProgramParser — DATA DIVISION integration
# ---------------------------------------------------------------------------


class TestProgramParserDataDivision:
    """ProgramParser correctly detects and delegates DATA DIVISION."""

    def test_parses_data_division(self) -> None:
        tokens = _data_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert program.data_division is not None

    def test_data_division_node_type(self) -> None:
        tokens = _data_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert isinstance(program.data_division, DataDivisionNode)

    def test_no_data_division_when_absent(self) -> None:
        from app.parser.lexer.position import Position as Pos

        pos = Pos(line=1, column=1, offset=0, filename="x.cbl")
        eof = Token(type=TokenType.EOF, lexeme="", position=pos)
        parser = ProgramParser()
        program = parser.parse([eof])
        assert program.data_division is None

    def test_program_node_data_division_has_working_storage(self) -> None:
        tokens = _data_header() + _ws_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert program.data_division is not None
        assert program.data_division.working_storage is not None

    def test_program_node_working_storage_items(self) -> None:
        tokens = (
            _data_header()
            + _ws_header()
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            + [_eof()]
        )
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert program.data_division is not None
        assert program.data_division.working_storage is not None
        assert len(program.data_division.working_storage.items) == 1

    def test_identification_then_data_division(self) -> None:
        """Full program: IDENTIFICATION DIVISION followed by DATA DIVISION."""
        ident_tokens = [
            _kw("IDENTIFICATION"),
            _kw("DIVISION"),
            _period(),
            _kw("PROGRAM-ID"),
            _period(),
            _id("MYPROG"),
            _period(),
        ]
        tokens = ident_tokens + _data_header() + _ws_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert program.identification_division is not None
        assert program.data_division is not None

    def test_program_node_is_program_node_type(self) -> None:
        tokens = _data_header() + [_eof()]
        parser = ProgramParser()
        program = parser.parse(tokens)
        assert isinstance(program, ProgramNode)


# ---------------------------------------------------------------------------
# Comprehensive scenario: well-formed DATA DIVISION
# ---------------------------------------------------------------------------


class TestWellFormedDataDivision:
    """Integration tests with a realistic WORKING-STORAGE SECTION."""

    def _parse(self, tokens: list[Token]) -> DataDivisionNode:
        state = _make_state(tokens)
        return DataDivisionParser().parse(state)

    def test_full_working_storage(self) -> None:
        """
        Parse a DATA DIVISION with:

            01 CUSTOMER-REC.
               05 CUSTOMER-ID     PIC 9(5).
               05 CUSTOMER-NAME   PIC X(30).
            77 WS-COUNT           PIC 9(4).
            88 END-OF-FILE        VALUE 'Y'.
        """
        tokens = (
            _data_header()
            + _ws_header()
            # 01 CUSTOMER-REC.
            + [_num("01"), _id("CUSTOMER-REC"), _period()]
            # 05 CUSTOMER-ID PIC 9(5).
            + [_num("05"), _id("CUSTOMER-ID")]
            + _pic_clause_with_parens("9", "5")
            + [_period()]
            # 05 CUSTOMER-NAME PIC X(30).
            + [_num("05"), _id("CUSTOMER-NAME")]
            + _pic_clause_with_parens("X", "30")
            + [_period()]
            # 77 WS-COUNT PIC 9(4).
            + [_num("77"), _id("WS-COUNT")]
            + _pic_clause_with_parens("9", "4")
            + [_period()]
            # 88 END-OF-FILE VALUE 'Y'.
            + [
                _num("88"),
                _id("END-OF-FILE"),
                _kw("VALUE"),
                _str_tok("'Y'"),
                _period(),
            ]
            + [_eof()]
        )
        node = self._parse(tokens)

        assert node.working_storage is not None
        items = node.working_storage.items
        assert len(items) == 5

        # 01 CUSTOMER-REC — group
        assert isinstance(items[0], GroupItemNode)
        assert items[0].level == 1
        assert items[0].name == "CUSTOMER-REC"

        # 05 CUSTOMER-ID — elementary
        assert isinstance(items[1], ElementaryItemNode)
        assert items[1].level == 5
        assert items[1].name == "CUSTOMER-ID"
        assert "9" in items[1].picture

        # 05 CUSTOMER-NAME — elementary
        assert isinstance(items[2], ElementaryItemNode)
        assert items[2].name == "CUSTOMER-NAME"
        assert "X" in items[2].picture

        # 77 WS-COUNT — elementary
        assert isinstance(items[3], ElementaryItemNode)
        assert items[3].level == 77

        # 88 END-OF-FILE — condition name
        assert isinstance(items[4], ConditionNameNode)
        assert items[4].level == 88
        assert items[4].name == "END-OF-FILE"
        assert items[4].value == "'Y'"


# ---------------------------------------------------------------------------
# Visitor dispatch
# ---------------------------------------------------------------------------


class TestVisitorDispatch:
    """accept() on new nodes dispatches to the correct visitor method."""

    _POS = _pos()

    def test_data_division_accept_dispatches(self) -> None:
        visited: list[DataDivisionNode] = []

        class V:
            def visit_data_division(self, n: DataDivisionNode) -> None:
                visited.append(n)

        node = DataDivisionNode(start_position=self._POS, end_position=self._POS)
        node.accept(V())
        assert len(visited) == 1
        assert visited[0] is node

    def test_working_storage_accept_dispatches(self) -> None:
        visited: list[WorkingStorageSectionNode] = []

        class V:
            def visit_working_storage_section(
                self, n: WorkingStorageSectionNode
            ) -> None:
                visited.append(n)

        node = WorkingStorageSectionNode(
            start_position=self._POS, end_position=self._POS
        )
        node.accept(V())
        assert len(visited) == 1

    def test_elementary_item_accept_dispatches(self) -> None:
        visited: list[ElementaryItemNode] = []

        class V:
            def visit_elementary_item(self, n: ElementaryItemNode) -> None:
                visited.append(n)

        node = ElementaryItemNode(
            start_position=self._POS,
            end_position=self._POS,
            level=5,
            name="ID",
            picture="9",
        )
        node.accept(V())
        assert len(visited) == 1

    def test_group_item_accept_dispatches(self) -> None:
        visited: list[GroupItemNode] = []

        class V:
            def visit_group_item(self, n: GroupItemNode) -> None:
                visited.append(n)

        node = GroupItemNode(
            start_position=self._POS, end_position=self._POS, level=1, name="REC"
        )
        node.accept(V())
        assert len(visited) == 1

    def test_condition_name_accept_dispatches(self) -> None:
        visited: list[ConditionNameNode] = []

        class V:
            def visit_condition_name(self, n: ConditionNameNode) -> None:
                visited.append(n)

        node = ConditionNameNode(
            start_position=self._POS,
            end_position=self._POS,
            level=88,
            name="FLAG",
            value="'Y'",
        )
        node.accept(V())
        assert len(visited) == 1

    def test_accept_returns_none_for_unknown_visitor(self) -> None:
        pos = self._POS
        node = DataDivisionNode(start_position=pos, end_position=pos)
        result = node.accept(object())
        assert result is None


# ---------------------------------------------------------------------------
# AST node defaults and field checks
# ---------------------------------------------------------------------------


class TestASTNodeDefaults:
    """Default field values for all new AST node types."""

    _POS = _pos()

    def test_data_division_node_defaults(self) -> None:
        node = DataDivisionNode(start_position=self._POS, end_position=self._POS)
        assert node.working_storage is None

    def test_working_storage_section_node_defaults(self) -> None:
        node = WorkingStorageSectionNode(
            start_position=self._POS, end_position=self._POS
        )
        assert node.items == ()

    def test_elementary_item_value_defaults_none(self) -> None:
        node = ElementaryItemNode(
            start_position=self._POS,
            end_position=self._POS,
            level=5,
            name="X",
            picture="9",
        )
        assert node.value is None

    def test_group_item_children_defaults_empty(self) -> None:
        node = GroupItemNode(
            start_position=self._POS, end_position=self._POS, level=1, name="R"
        )
        assert node.children == ()

    def test_condition_name_value_defaults_none(self) -> None:
        node = ConditionNameNode(
            start_position=self._POS, end_position=self._POS, level=88, name="C"
        )
        assert node.value is None

    def test_all_data_item_nodes_are_astnodes(self) -> None:
        pos = self._POS
        nodes: list[ASTNode] = [
            DataDivisionNode(start_position=pos, end_position=pos),
            WorkingStorageSectionNode(start_position=pos, end_position=pos),
            ElementaryItemNode(
                start_position=pos, end_position=pos, level=5, name="X", picture="9"
            ),
            GroupItemNode(start_position=pos, end_position=pos, level=1, name="R"),
            ConditionNameNode(start_position=pos, end_position=pos, level=88, name="C"),
        ]
        for node in nodes:
            assert isinstance(node, ASTNode), f"{type(node).__name__} is not ASTNode"
