"""
Unit tests for :class:`app.parser.lexer.token.Token`.

Purpose:
    Verify that the ``Token`` frozen dataclass satisfies the
    immutability, equality, hashing, and repr contracts expected by
    the parser and all downstream compiler stages.

Responsibilities:
    - Assert that ``Token`` instances are correctly constructed from
      their three required fields.
    - Assert immutability (frozen dataclass).
    - Assert structural equality and hash consistency.
    - Assert that the dataclass repr is informative.

Dependencies:
    - :mod:`app.parser.lexer.token`       — ``Token`` under test.
    - :mod:`app.parser.lexer.token_types` — ``TokenType`` enum.
    - :mod:`app.parser.lexer.position`    — ``Position`` value type.
    - pytest

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import dataclasses

import pytest

from app.parser.lexer.position import Position
from app.parser.lexer.token import Token
from app.parser.lexer.token_types import TokenType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def origin() -> Position:
    """Return a :class:`Position` at the start of a file."""
    return Position(line=1, column=1, offset=0, filename="TEST.cbl")


@pytest.fixture()
def keyword_token(origin: Position) -> Token:
    """Return a representative KEYWORD :class:`Token`."""
    return Token(
        type=TokenType.KEYWORD,
        lexeme="IDENTIFICATION",
        position=origin,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestTokenConstruction:
    """Tests that ``Token`` is constructed correctly from its fields."""

    def test_type_field(self, keyword_token: Token) -> None:
        """The ``type`` field returns the expected ``TokenType``."""
        assert keyword_token.type is TokenType.KEYWORD

    def test_lexeme_field(self, keyword_token: Token) -> None:
        """The ``lexeme`` field returns the exact source text."""
        assert keyword_token.lexeme == "IDENTIFICATION"

    def test_position_field(self, keyword_token: Token, origin: Position) -> None:
        """The ``position`` field returns the ``Position`` passed in."""
        assert keyword_token.position == origin

    def test_eof_token_with_empty_lexeme(self, origin: Position) -> None:
        """An EOF token with an empty lexeme is valid."""
        eof = Token(type=TokenType.EOF, lexeme="", position=origin)
        assert eof.type is TokenType.EOF
        assert eof.lexeme == ""

    def test_number_token(self, origin: Position) -> None:
        """A NUMBER token carries its numeric lexeme correctly."""
        tok = Token(type=TokenType.NUMBER, lexeme="42", position=origin)
        assert tok.type is TokenType.NUMBER
        assert tok.lexeme == "42"

    def test_unknown_token(self, origin: Position) -> None:
        """An UNKNOWN token preserves the unrecognised character."""
        tok = Token(type=TokenType.UNKNOWN, lexeme="@", position=origin)
        assert tok.type is TokenType.UNKNOWN
        assert tok.lexeme == "@"


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestTokenImmutability:
    """Tests that ``Token`` is truly immutable (frozen dataclass)."""

    def test_cannot_set_type(self, keyword_token: Token) -> None:
        """Assigning to ``type`` raises :exc:`FrozenInstanceError`."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            keyword_token.type = TokenType.IDENTIFIER  # type: ignore[misc]

    def test_cannot_set_lexeme(self, keyword_token: Token) -> None:
        """Assigning to ``lexeme`` raises :exc:`FrozenInstanceError`."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            keyword_token.lexeme = "OTHER"  # type: ignore[misc]

    def test_cannot_set_position(self, keyword_token: Token, origin: Position) -> None:
        """Assigning to ``position`` raises :exc:`FrozenInstanceError`."""
        new_pos = Position(line=99, column=1, offset=999, filename="X.cbl")
        with pytest.raises(dataclasses.FrozenInstanceError):
            keyword_token.position = new_pos  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Equality
# ---------------------------------------------------------------------------


class TestTokenEquality:
    """Tests structural equality semantics of ``Token``."""

    def test_equal_tokens(self, origin: Position) -> None:
        """Two tokens with identical fields are equal."""
        t1 = Token(type=TokenType.IDENTIFIER, lexeme="WS-AMOUNT", position=origin)
        t2 = Token(type=TokenType.IDENTIFIER, lexeme="WS-AMOUNT", position=origin)
        assert t1 == t2

    def test_different_type_not_equal(self, origin: Position) -> None:
        """Tokens differing only in ``type`` are not equal."""
        t1 = Token(type=TokenType.IDENTIFIER, lexeme="MOVE", position=origin)
        t2 = Token(type=TokenType.KEYWORD, lexeme="MOVE", position=origin)
        assert t1 != t2

    def test_different_lexeme_not_equal(self, origin: Position) -> None:
        """Tokens differing only in ``lexeme`` are not equal."""
        t1 = Token(type=TokenType.IDENTIFIER, lexeme="WS-A", position=origin)
        t2 = Token(type=TokenType.IDENTIFIER, lexeme="WS-B", position=origin)
        assert t1 != t2

    def test_different_position_not_equal(self) -> None:
        """Tokens differing only in ``position`` are not equal."""
        p1 = Position(line=1, column=1, offset=0, filename="A.cbl")
        p2 = Position(line=2, column=1, offset=80, filename="A.cbl")
        t1 = Token(type=TokenType.IDENTIFIER, lexeme="WS-A", position=p1)
        t2 = Token(type=TokenType.IDENTIFIER, lexeme="WS-A", position=p2)
        assert t1 != t2


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


class TestTokenHashing:
    """Tests that ``Token`` is hashable and usable in sets/dicts."""

    def test_equal_tokens_have_equal_hashes(self, origin: Position) -> None:
        """Equal tokens share the same hash value."""
        t1 = Token(type=TokenType.STRING, lexeme="HELLO", position=origin)
        t2 = Token(type=TokenType.STRING, lexeme="HELLO", position=origin)
        assert hash(t1) == hash(t2)

    def test_token_usable_as_dict_key(self, keyword_token: Token) -> None:
        """A ``Token`` can be used as a dictionary key."""
        mapping = {keyword_token: "meta"}
        assert mapping[keyword_token] == "meta"

    def test_token_usable_in_set(self, origin: Position) -> None:
        """Identical tokens collapse to one element in a set."""
        t1 = Token(type=TokenType.PERIOD, lexeme=".", position=origin)
        t2 = Token(type=TokenType.PERIOD, lexeme=".", position=origin)
        assert len({t1, t2}) == 1


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestTokenRepr:
    """Tests the string representation produced by the frozen dataclass."""

    def test_repr_contains_type(self, keyword_token: Token) -> None:
        """The repr includes the ``TokenType`` member name."""
        assert "KEYWORD" in repr(keyword_token)

    def test_repr_contains_lexeme(self, keyword_token: Token) -> None:
        """The repr includes the lexeme string."""
        assert "IDENTIFICATION" in repr(keyword_token)

    def test_repr_contains_position(self, keyword_token: Token) -> None:
        """The repr includes the nested ``Position`` representation."""
        assert "Position" in repr(keyword_token)
