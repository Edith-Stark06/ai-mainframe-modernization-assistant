"""
Regression tests for numeric-prefixed COBOL word formation (task #106).

Purpose:
    COBOL user-defined words may begin with digits — procedure names such
    as ``0000-MAIN`` and ``3000-VALIDATE-INPUT`` are the common case.
    :meth:`~app.parser.lexer.lexer.CobolLexer.tokenize` dispatches on
    ``ch.isdigit()`` before it dispatches on ``_WORD_START`` (which holds
    only letters), so those names used to be split into three tokens —
    ``NUMBER('0000')``, ``UNKNOWN('-')``, ``IDENTIFIER('MAIN')`` — and
    the procedure parser could not read them as paragraph labels.

    These tests pin both halves of the rule: the names are recovered, and
    the numeric and arithmetic forms that must *not* change are asserted
    explicitly, because the risk in this area is a fix that quietly turns
    numeric literals into identifiers.

    Tests drive the real pipeline (source → ``CobolLexer`` → parser →
    AST) rather than the scanning helpers in isolation.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any

import pytest

from app.parser.lexer.lexer import CobolLexer
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.program_parser import ProgramParser
from app.parser.syntax.token_stream import TokenStream

_ID = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"


def _tokenize(source: str) -> list[Token]:
    """Tokenise *source* with the real production lexer."""
    return CobolLexer().tokenize(source, filename="t.cbl")


def _body(source: str) -> list[tuple[str, str]]:
    """Return ``(token type name, lexeme)`` pairs, excluding EOF."""
    return [
        (t.type.name, t.lexeme)
        for t in _tokenize(source)
        if t.type is not TokenType.EOF
    ]


def _parse(source: str) -> tuple[Any, ParserState]:
    """Parse *source* end to end, returning ``(program, state)``."""
    state = ParserState(TokenStream(_tokenize(source)))
    return ProgramParser()._parse_program(state), state


# ===========================================================================
# A — numeric-prefixed procedure names
# ===========================================================================


class TestNumericPrefixedNamesLexAsOneWord:
    """The names are recovered as single IDENTIFIER tokens."""

    @pytest.mark.parametrize(
        "name",
        [
            "0000-MAIN",
            "1000-INITIALIZE",
            "2000-PROCESS",
            "3000-VALIDATE-INPUT",
            "9000-END-PROCESS",
            "4510-FORMAT-AUDIT",
        ],
    )
    def test_name_is_a_single_identifier(self, name: str) -> None:
        """The whole lexeme arrives in one IDENTIFIER token."""
        assert _body(f"{name}.") == [("IDENTIFIER", name), ("PERIOD", ".")]

    def test_paragraph_labels_reach_the_ast(self) -> None:
        """
        The end-to-end goal: paragraph names carrying the complete
        lexeme.  Before this change the PROCEDURE DIVISION parsed to
        zero paragraphs.
        """
        source = (
            _ID + "PROCEDURE DIVISION.\n"
            "0000-MAIN.\n"
            '    DISPLAY "A".\n'
            "1000-INIT.\n"
            '    DISPLAY "B".\n'
            "2000-PROCESS.\n"
            "    STOP RUN.\n"
        )
        program, _ = _parse(source)
        paragraphs = program.procedure_division.paragraphs

        assert [p.name for p in paragraphs] == [
            "0000-MAIN",
            "1000-INIT",
            "2000-PROCESS",
        ]
        assert [len(p.statements) for p in paragraphs] == [1, 1, 1]

    def test_perform_target_keeps_the_whole_name(self) -> None:
        """A PERFORM target is the complete numeric-prefixed name."""
        source = (
            _ID + "PROCEDURE DIVISION.\n"
            "0000-MAIN.\n"
            "    PERFORM 1000-INITIALIZE.\n"
            "    STOP RUN.\n"
            "1000-INITIALIZE.\n"
            '    DISPLAY "X".\n'
        )
        program, _ = _parse(source)
        first = program.procedure_division.paragraphs[0]

        assert first.statements[0].target == "1000-INITIALIZE"


# ===========================================================================
# B — ordinary hyphenated names are unchanged
# ===========================================================================


class TestOrdinaryNamesUnchanged:
    """Alphabetic-leading words keep their existing classification."""

    @pytest.mark.parametrize(
        "name",
        ["CUSTOMER-UPDATE", "WS-CUSTOMER-ID", "MAIN-PARA", "COMP-3", "WS-A1", "A"],
    )
    def test_identifier_unchanged(self, name: str) -> None:
        """Ordinary identifiers still lex as one IDENTIFIER token."""
        assert _body(name) == [("IDENTIFIER", name)]

    def test_alphabetic_paragraph_still_parses(self) -> None:
        """The pre-existing paragraph style keeps working."""
        source = _ID + "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"
        program, state = _parse(source)

        assert [p.name for p in program.procedure_division.paragraphs] == ["MAIN-PARA"]
        assert state.diagnostics == []


# ===========================================================================
# C — numeric literals stay numeric
# ===========================================================================


class TestNumericLiteralsUnchanged:
    """The central risk of this change: digits must stay digits."""

    @pytest.mark.parametrize(
        "literal", ["0", "9", "01", "0000", "123", "000123", "20260728"]
    )
    def test_plain_number_is_still_a_number(self, literal: str) -> None:
        """A run of digits with no hyphen+letter after it stays NUMBER."""
        assert _body(literal) == [("NUMBER", literal)]

    def test_level_numbers_and_pictures_still_parse(self) -> None:
        """Level numbers are NUMBER tokens, so data items still parse."""
        source = (
            _ID + "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
            "01 WS-COUNT PIC 9(4).\n"
            "77 WS-TOTAL PIC 9(8) VALUE 0.\n"
            "PROCEDURE DIVISION.\nMAIN.\n    STOP RUN.\n"
        )
        program, state = _parse(source)
        items = program.data_division.working_storage.items

        assert [i.name for i in items] == ["WS-COUNT", "WS-TOTAL"]
        assert [i.picture for i in items] == ["9(4)", "9(8)"]
        assert state.diagnostics == []


# ===========================================================================
# D — hyphen arithmetic and operators are unchanged
# ===========================================================================


class TestHyphenBehaviourUnchanged:
    """
    The hyphen must only join a word when a letter follows it directly.
    A fix that made every hyphen part of an identifier would break these.
    """

    def test_spaced_subtraction_unchanged(self) -> None:
        """``B - C`` keeps the hyphen as its own token."""
        assert _body("COMPUTE A = B - C") == [
            ("KEYWORD", "COMPUTE"),
            ("IDENTIFIER", "A"),
            ("OPERATOR_EQ", "="),
            ("IDENTIFIER", "B"),
            ("UNKNOWN", "-"),
            ("IDENTIFIER", "C"),
        ]

    def test_signed_literal_unchanged(self) -> None:
        """``VALUE -1`` keeps the sign separate from the digits."""
        assert _body("VALUE -1") == [
            ("KEYWORD", "VALUE"),
            ("UNKNOWN", "-"),
            ("NUMBER", "1"),
        ]

    def test_move_and_comparison_unchanged(self) -> None:
        """Statements with no digits at all are untouched."""
        assert _body("MOVE A TO B") == [
            ("KEYWORD", "MOVE"),
            ("IDENTIFIER", "A"),
            ("IDENTIFIER", "TO"),
            ("IDENTIFIER", "B"),
        ]
        assert ("OPERATOR_EQ", "=") in _body("IF A NOT = B")

    def test_arithmetic_statement_still_parses(self) -> None:
        """An ADD statement over numeric operands is unaffected."""
        source = (
            _ID + "PROCEDURE DIVISION.\nMAIN.\n"
            "    ADD 1 TO WS-COUNT.\n    STOP RUN.\n"
        )
        program, state = _parse(source)

        assert len(program.procedure_division.paragraphs[0].statements) == 2
        assert state.diagnostics == []


# ===========================================================================
# E — ambiguous forms do not silently become identifiers
# ===========================================================================


class TestAmbiguousFormsNotAbsorbed:
    """
    Only ``digits + '-' + letter`` starts a word.  Everything else keeps
    the tokenisation it had before, so no new identifier is invented.
    """

    def test_date_like_digits_stay_numeric(self) -> None:
        """``2026-09-02`` — the DATE-WRITTEN form — is not an identifier."""
        assert _body("2026-09-02") == [
            ("NUMBER", "2026"),
            ("UNKNOWN", "-"),
            ("NUMBER", "09"),
            ("UNKNOWN", "-"),
            ("NUMBER", "02"),
        ]

    def test_digit_hyphen_digit_stays_numeric(self) -> None:
        """No letter after the hyphen means no word."""
        assert _body("123-456") == [
            ("NUMBER", "123"),
            ("UNKNOWN", "-"),
            ("NUMBER", "456"),
        ]

    def test_trailing_hyphen_is_not_absorbed(self) -> None:
        """
        A hyphen with nothing word-like after it stays a separate token
        rather than being swallowed into the name.
        """
        assert _body("0000- MAIN") == [
            ("NUMBER", "0000"),
            ("UNKNOWN", "-"),
            ("IDENTIFIER", "MAIN"),
        ]

    def test_word_stops_before_trailing_hyphen(self) -> None:
        """A numeric-prefixed word does not consume a dangling hyphen."""
        assert _body("0000-MAIN- ") == [
            ("IDENTIFIER", "0000-MAIN"),
            ("UNKNOWN", "-"),
        ]

    def test_date_written_clause_value_is_unchanged(self) -> None:
        """
        End-to-end guard: the identification clause that contains a
        date-like value parses exactly as it did before.
        """
        source = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\nDATE-WRITTEN. 2026-09-02.\n"
        program, state = _parse(source)

        assert program.identification_division.date_written.value == "2026 - 09 - 02"
        assert state.diagnostics == []


# ===========================================================================
# F — reserved words are unaffected
# ===========================================================================


class TestReservedWordsUnchanged:
    """Keyword classification is untouched by this change."""

    @pytest.mark.parametrize(
        "word", ["MOVE", "PERFORM", "DISPLAY", "IF", "STOP", "WORKING-STORAGE", "PIC"]
    )
    def test_keyword_still_keyword(self, word: str) -> None:
        """Reserved words still lex as KEYWORD."""
        assert _body(word) == [("KEYWORD", word)]

    def test_numeric_prefixed_word_is_never_a_keyword(self) -> None:
        """No reserved word begins with a digit, so these are IDENTIFIERs."""
        for name in ("0000-MAIN", "1000-DISPLAY", "2000-MOVE"):
            types = {t for t, _ in _body(name)}
            assert types == {"IDENTIFIER"}
