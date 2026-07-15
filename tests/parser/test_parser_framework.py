"""
Tests for the COBOL Parser Framework.

Purpose:
    Verify that the parser framework components — TokenStream,
    ParserState, CobolParser, and the parser error hierarchy — behave
    correctly in isolation and in combination.

Coverage:
    - TokenStream: construction, current(), peek(), advance(), eof().
    - TokenStream: expect() happy-path and error cases.
    - ParserState: construction, current_token, position, error_count,
                   record_error(), has_errors.
    - CobolParser: construction and parse() returning an empty ProgramNode.
    - UnexpectedTokenError: attributes and inheritance.
    - UnexpectedEOFError: attributes and inheritance.

Non-responsibilities:
    - COBOL grammar rules (no division / statement parsing).
    - Semantic analysis.

Dependencies:
    - :mod:`app.parser.syntax.token_stream`   — TokenStream.
    - :mod:`app.parser.syntax.parser_state`   — ParserState.
    - :mod:`app.parser.syntax.parser`         — CobolParser.
    - :mod:`app.parser.syntax.parser_errors`  — error hierarchy.
    - :mod:`app.parser.syntax.parser_exceptions` — ParserError base.
    - :mod:`app.parser.lexer.token`           — Token.
    - :mod:`app.parser.lexer.token_types`     — TokenType.
    - :mod:`app.parser.lexer.position`        — Position.
    - :mod:`app.parser.ast.program`           — ProgramNode.
    - :mod:`pytest`                           — test framework.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import pytest

from app.parser.ast.program import ProgramNode
from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType
from app.parser.syntax.parser import CobolParser
from app.parser.syntax.parser_errors import UnexpectedEOFError, UnexpectedTokenError
from app.parser.syntax.parser_exceptions import ParserError
from app.parser.syntax.parser_state import ParserState
from app.parser.syntax.token_stream import TokenStream

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_POS = Position(line=1, column=1, offset=0, filename="test.cbl")
_POS2 = Position(line=2, column=5, offset=40, filename="test.cbl")
_POS3 = Position(line=3, column=1, offset=80, filename="test.cbl")


def _tok(ttype: TokenType, lexeme: str = "", pos: Position = _POS) -> Token:
    """Create a token with the given type, lexeme and position."""
    return Token(type=ttype, lexeme=lexeme, position=pos)


def _eof(pos: Position = _POS) -> Token:
    """Create an EOF sentinel token."""
    return _tok(TokenType.EOF, "", pos)


def _kw(lexeme: str, pos: Position = _POS) -> Token:
    """Create a KEYWORD token."""
    return _tok(TokenType.KEYWORD, lexeme, pos)


def _id(lexeme: str, pos: Position = _POS) -> Token:
    """Create an IDENTIFIER token."""
    return _tok(TokenType.IDENTIFIER, lexeme, pos)


def _period(pos: Position = _POS) -> Token:
    """Create a PERIOD token."""
    return _tok(TokenType.PERIOD, ".", pos)


# ---------------------------------------------------------------------------
# TokenStream — construction
# ---------------------------------------------------------------------------


class TestTokenStreamConstruction:
    """TokenStream construction and validation."""

    def test_requires_at_least_one_token(self) -> None:
        """An empty list raises ValueError."""
        with pytest.raises(ValueError, match="at least one token"):
            TokenStream([])

    def test_single_eof_token(self) -> None:
        """A stream containing only EOF is valid."""
        stream = TokenStream([_eof()])
        assert stream.eof() is True

    def test_len_reflects_token_count(self) -> None:
        stream = TokenStream([_kw("IDENTIFICATION"), _eof()])
        assert len(stream) == 2


# ---------------------------------------------------------------------------
# TokenStream — current()
# ---------------------------------------------------------------------------


class TestTokenStreamCurrent:
    """TokenStream.current() returns the token at the cursor."""

    def test_current_is_first_token(self) -> None:
        kw = _kw("IDENTIFICATION")
        stream = TokenStream([kw, _eof()])
        assert stream.current() is kw

    def test_current_after_advance(self) -> None:
        kw = _kw("IDENTIFICATION")
        eof = _eof()
        stream = TokenStream([kw, eof])
        stream.advance()
        assert stream.current() is eof


# ---------------------------------------------------------------------------
# TokenStream — peek()
# ---------------------------------------------------------------------------


class TestTokenStreamPeek:
    """TokenStream.peek() returns the token ahead without advancing."""

    def test_peek_default_is_one_ahead(self) -> None:
        kw = _kw("IDENTIFICATION")
        eof = _eof()
        stream = TokenStream([kw, eof])
        assert stream.peek() is eof

    def test_peek_does_not_advance(self) -> None:
        kw = _kw("IDENTIFICATION")
        stream = TokenStream([kw, _eof()])
        stream.peek()
        assert stream.current() is kw

    def test_peek_beyond_end_returns_eof(self) -> None:
        eof = _eof()
        stream = TokenStream([eof])
        assert stream.peek(offset=10) is eof

    def test_peek_zero_returns_current(self) -> None:
        kw = _kw("DATA")
        stream = TokenStream([kw, _eof()])
        assert stream.peek(offset=0) is kw

    def test_peek_multiple_positions(self) -> None:
        t1 = _kw("A")
        t2 = _kw("B")
        t3 = _kw("C")
        eof = _eof()
        stream = TokenStream([t1, t2, t3, eof])
        assert stream.peek(1) is t2
        assert stream.peek(2) is t3
        assert stream.peek(3) is eof


# ---------------------------------------------------------------------------
# TokenStream — advance()
# ---------------------------------------------------------------------------


class TestTokenStreamAdvance:
    """TokenStream.advance() consumes and returns the current token."""

    def test_advance_returns_current(self) -> None:
        kw = _kw("IDENTIFICATION")
        stream = TokenStream([kw, _eof()])
        returned = stream.advance()
        assert returned is kw

    def test_advance_moves_cursor(self) -> None:
        kw = _kw("IDENTIFICATION")
        eof = _eof()
        stream = TokenStream([kw, eof])
        stream.advance()
        assert stream.current() is eof

    def test_advance_at_eof_is_idempotent(self) -> None:
        eof = _eof()
        stream = TokenStream([eof])
        result1 = stream.advance()
        result2 = stream.advance()
        assert result1 is eof
        assert result2 is eof
        assert stream.eof() is True

    def test_advance_sequential(self) -> None:
        t1 = _kw("A")
        t2 = _kw("B")
        eof = _eof()
        stream = TokenStream([t1, t2, eof])
        assert stream.advance() is t1
        assert stream.advance() is t2
        assert stream.advance() is eof
        assert stream.eof() is True


# ---------------------------------------------------------------------------
# TokenStream — eof()
# ---------------------------------------------------------------------------


class TestTokenStreamEof:
    """TokenStream.eof() correctly detects end-of-stream."""

    def test_eof_true_on_eof_token(self) -> None:
        stream = TokenStream([_eof()])
        assert stream.eof() is True

    def test_eof_false_before_eof(self) -> None:
        stream = TokenStream([_kw("IDENTIFICATION"), _eof()])
        assert stream.eof() is False

    def test_eof_true_after_consuming_all(self) -> None:
        stream = TokenStream([_kw("X"), _eof()])
        stream.advance()
        assert stream.eof() is True


# ---------------------------------------------------------------------------
# TokenStream — expect()
# ---------------------------------------------------------------------------


class TestTokenStreamExpect:
    """TokenStream.expect() consumes matching tokens and raises on mismatch."""

    def test_expect_matching_type_returns_token(self) -> None:
        kw = _kw("IDENTIFICATION")
        stream = TokenStream([kw, _eof()])
        result = stream.expect(TokenType.KEYWORD)
        assert result is kw

    def test_expect_advances_cursor(self) -> None:
        kw = _kw("IDENTIFICATION")
        eof = _eof()
        stream = TokenStream([kw, eof])
        stream.expect(TokenType.KEYWORD)
        assert stream.current() is eof

    def test_expect_mismatch_raises_unexpected_token(self) -> None:
        kw = _kw("IDENTIFICATION")
        stream = TokenStream([kw, _eof()])
        with pytest.raises(UnexpectedTokenError) as exc_info:
            stream.expect(TokenType.PERIOD)
        err = exc_info.value
        assert err.found_type is TokenType.KEYWORD
        assert err.expected_type is TokenType.PERIOD
        assert err.found_lexeme == "IDENTIFICATION"

    def test_expect_eof_when_more_expected_raises_unexpected_eof(self) -> None:
        stream = TokenStream([_eof()])
        with pytest.raises(UnexpectedEOFError):
            stream.expect(TokenType.KEYWORD)

    def test_expect_eof_type_on_eof_succeeds(self) -> None:
        eof = _eof()
        stream = TokenStream([eof])
        result = stream.expect(TokenType.EOF)
        assert result is eof

    def test_expect_carries_position_info(self) -> None:
        kw = _kw("MOVE", pos=_POS2)
        stream = TokenStream([kw, _eof()])
        with pytest.raises(UnexpectedTokenError) as exc_info:
            stream.expect(TokenType.PERIOD)
        err = exc_info.value
        assert err.line == _POS2.line
        assert err.column == _POS2.column
        assert err.offset == _POS2.offset


# ---------------------------------------------------------------------------
# TokenStream — position property
# ---------------------------------------------------------------------------


class TestTokenStreamPosition:
    """TokenStream.position reflects the cursor index."""

    def test_initial_position_is_zero(self) -> None:
        stream = TokenStream([_eof()])
        assert stream.position == 0

    def test_position_increments_on_advance(self) -> None:
        stream = TokenStream([_kw("X"), _eof()])
        assert stream.position == 0
        stream.advance()
        assert stream.position == 1


# ---------------------------------------------------------------------------
# ParserState — construction and properties
# ---------------------------------------------------------------------------


class TestParserState:
    """ParserState tracks token, position, and error count."""

    def _make_state(self, *tokens: Token) -> ParserState:
        return ParserState(TokenStream(list(tokens)))

    def test_initial_error_count_is_zero(self) -> None:
        state = self._make_state(_eof())
        assert state.error_count == 0

    def test_has_errors_false_initially(self) -> None:
        state = self._make_state(_eof())
        assert state.has_errors is False

    def test_record_error_increments_count(self) -> None:
        state = self._make_state(_eof())
        state.record_error()
        assert state.error_count == 1

    def test_record_error_multiple_times(self) -> None:
        state = self._make_state(_eof())
        state.record_error()
        state.record_error()
        state.record_error()
        assert state.error_count == 3

    def test_has_errors_true_after_record(self) -> None:
        state = self._make_state(_eof())
        state.record_error()
        assert state.has_errors is True

    def test_current_token_is_first(self) -> None:
        kw = _kw("IDENTIFICATION")
        state = self._make_state(kw, _eof())
        assert state.current_token is kw

    def test_position_initially_zero(self) -> None:
        state = self._make_state(_eof())
        assert state.position == 0

    def test_position_advances_with_stream(self) -> None:
        kw = _kw("DATA")
        state = self._make_state(kw, _eof())
        state.stream.advance()
        assert state.position == 1

    def test_stream_property_returns_token_stream(self) -> None:
        state = self._make_state(_eof())
        assert isinstance(state.stream, TokenStream)


# ---------------------------------------------------------------------------
# CobolParser — construction and parse()
# ---------------------------------------------------------------------------


class TestCobolParser:
    """CobolParser.parse() returns an empty ProgramNode."""

    def test_parser_can_be_instantiated(self) -> None:
        parser = CobolParser()
        assert parser is not None

    def test_parse_returns_program_node(self) -> None:
        parser = CobolParser()
        tokens = [_eof()]
        result = parser.parse(tokens)
        assert isinstance(result, ProgramNode)

    def test_empty_program_has_no_divisions(self) -> None:
        parser = CobolParser()
        program = parser.parse([_eof()])
        assert program.identification_division is None
        assert program.environment_division is None
        assert program.data_division is None
        assert program.procedure_division is None

    def test_parse_with_extra_tokens_still_returns_program(self) -> None:
        """Extra tokens before EOF do not crash the framework stub."""
        parser = CobolParser()
        tokens = [
            _kw("IDENTIFICATION"),
            _kw("DIVISION"),
            _period(),
            _eof(),
        ]
        result = parser.parse(tokens)
        assert isinstance(result, ProgramNode)

    def test_parser_satisfies_protocol(self) -> None:
        """CobolParser structurally satisfies ParserProtocol."""
        from app.parser.syntax.parser_interfaces import ParserProtocol

        parser = CobolParser()
        assert isinstance(parser, ParserProtocol)

    def test_start_position_from_first_token(self) -> None:
        pos = Position(line=5, column=3, offset=100, filename="prog.cbl")
        eof = _eof(pos=pos)
        parser = CobolParser()
        program = parser.parse([eof])
        assert program.start_position == pos

    def test_parse_empty_token_list_raises(self) -> None:
        """An empty token list (no EOF) raises ValueError."""
        parser = CobolParser()
        with pytest.raises(ValueError):
            parser.parse([])


# ---------------------------------------------------------------------------
# UnexpectedTokenError
# ---------------------------------------------------------------------------


class TestUnexpectedTokenError:
    """UnexpectedTokenError attributes and inheritance."""

    def _make(self, **kwargs: object) -> UnexpectedTokenError:
        return UnexpectedTokenError(
            found_lexeme=kwargs.get("found_lexeme", "MOVE"),  # type: ignore[arg-type]
            found_type=kwargs.get("found_type", TokenType.KEYWORD),  # type: ignore[arg-type]
            expected_type=kwargs.get("expected_type", TokenType.PERIOD),  # type: ignore[arg-type]
            line=kwargs.get("line", 1),  # type: ignore[arg-type]
            column=kwargs.get("column", 1),  # type: ignore[arg-type]
            offset=kwargs.get("offset", 0),  # type: ignore[arg-type]
        )

    def test_inherits_parser_error(self) -> None:
        err = self._make()
        assert isinstance(err, ParserError)

    def test_inherits_exception(self) -> None:
        err = self._make()
        assert isinstance(err, Exception)

    def test_found_lexeme_stored(self) -> None:
        err = UnexpectedTokenError(
            found_lexeme="PERFORM",
            found_type=TokenType.KEYWORD,
            line=0,
            column=0,
            offset=0,
        )
        assert err.found_lexeme == "PERFORM"

    def test_found_type_stored(self) -> None:
        err = self._make(found_type=TokenType.IDENTIFIER)
        assert err.found_type is TokenType.IDENTIFIER

    def test_expected_type_stored(self) -> None:
        err = self._make(expected_type=TokenType.PERIOD)
        assert err.expected_type is TokenType.PERIOD

    def test_expected_type_none_by_default(self) -> None:
        err = UnexpectedTokenError(
            found_lexeme="X",
            found_type=TokenType.IDENTIFIER,
            line=0,
            column=0,
            offset=0,
        )
        assert err.expected_type is None

    def test_message_includes_lexeme(self) -> None:
        err = self._make(found_lexeme="MOVE")
        assert "MOVE" in str(err)

    def test_position_attributes(self) -> None:
        err = self._make(line=7, column=12, offset=300)
        assert err.line == 7
        assert err.column == 12
        assert err.offset == 300

    def test_can_be_caught_as_parser_error(self) -> None:
        with pytest.raises(ParserError):
            raise self._make()

    def test_str_includes_line_and_column(self) -> None:
        err = self._make(line=4, column=9)
        assert "4" in str(err)
        assert "9" in str(err)


# ---------------------------------------------------------------------------
# UnexpectedEOFError
# ---------------------------------------------------------------------------


class TestUnexpectedEOFError:
    """UnexpectedEOFError attributes and inheritance."""

    def test_inherits_parser_error(self) -> None:
        err = UnexpectedEOFError(line=1, column=1, offset=0)
        assert isinstance(err, ParserError)

    def test_inherits_exception(self) -> None:
        err = UnexpectedEOFError()
        assert isinstance(err, Exception)

    def test_message_mentions_eof(self) -> None:
        err = UnexpectedEOFError()
        assert "eof" in str(err).lower() or "end" in str(err).lower()

    def test_defaults_are_zero(self) -> None:
        err = UnexpectedEOFError()
        assert err.line == 0
        assert err.column == 0
        assert err.offset == 0

    def test_position_stored(self) -> None:
        err = UnexpectedEOFError(line=20, column=1, offset=800)
        assert err.line == 20
        assert err.column == 1
        assert err.offset == 800

    def test_can_be_caught_as_parser_error(self) -> None:
        with pytest.raises(ParserError):
            raise UnexpectedEOFError(line=1, column=1, offset=0)

    def test_can_be_raised_and_caught_directly(self) -> None:
        with pytest.raises(UnexpectedEOFError):
            raise UnexpectedEOFError(line=5, column=3, offset=150)
