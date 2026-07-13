"""
Unit tests for :class:`app.parser.lexer.token_types.TokenType`.

Purpose:
    Verify that the ``TokenType`` enumeration contains exactly the
    members required by the TASK-005 specification, that all values
    are unique (enforced by ``@unique``), and that enumeration
    behaviour is correct.

Responsibilities:
    - Assert the presence of every specified enum member by name.
    - Assert that no duplicate values exist.
    - Assert that members are retrievable by name and by value.
    - Assert that the total member count matches the specification.

Dependencies:
    - :mod:`app.parser.lexer.token_types` — ``TokenType`` under test.
    - pytest

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest

from app.parser.lexer.token_types import TokenType

# ---------------------------------------------------------------------------
# Expected specification
# ---------------------------------------------------------------------------

#: The exact set of member names mandated by TASK-005.
REQUIRED_MEMBERS: frozenset[str] = frozenset(
    {
        "IDENTIFIER",
        "KEYWORD",
        "STRING",
        "NUMBER",
        "LEVEL_NUMBER",
        "PIC",
        "PERIOD",
        "COMMA",
        "LPAREN",
        "RPAREN",
        "EOF",
        "UNKNOWN",
    }
)


# ---------------------------------------------------------------------------
# Member presence
# ---------------------------------------------------------------------------


class TestTokenTypeMembersExist:
    """Tests that every member required by the specification is present."""

    @pytest.mark.parametrize("name", sorted(REQUIRED_MEMBERS))
    def test_required_member_exists(self, name: str) -> None:
        """Each required member name resolves to a ``TokenType`` instance."""
        member = TokenType[name]
        assert isinstance(member, TokenType)
        assert member.name == name

    def test_total_member_count(self) -> None:
        """The enum contains exactly the number of members in the spec."""
        assert len(TokenType) == len(REQUIRED_MEMBERS)

    def test_no_extra_members(self) -> None:
        """No member names exist beyond those required by the spec."""
        actual_names = {m.name for m in TokenType}
        assert actual_names == REQUIRED_MEMBERS


# ---------------------------------------------------------------------------
# Value uniqueness
# ---------------------------------------------------------------------------


class TestTokenTypeUniqueness:
    """Tests that all enum values are unique (guaranteed by ``@unique``)."""

    def test_all_values_are_distinct(self) -> None:
        """Every ``TokenType`` member has a distinct value."""
        values = [m.value for m in TokenType]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Lookup by value
# ---------------------------------------------------------------------------


class TestTokenTypeValueLookup:
    """Tests that members can be retrieved by their string value."""

    def test_identifier_value(self) -> None:
        """``TokenType.IDENTIFIER`` has value ``'identifier'``."""
        assert TokenType("identifier") is TokenType.IDENTIFIER

    def test_keyword_value(self) -> None:
        """``TokenType.KEYWORD`` has value ``'keyword'``."""
        assert TokenType("keyword") is TokenType.KEYWORD

    def test_string_value(self) -> None:
        """``TokenType.STRING`` has value ``'string'``."""
        assert TokenType("string") is TokenType.STRING

    def test_number_value(self) -> None:
        """``TokenType.NUMBER`` has value ``'number'``."""
        assert TokenType("number") is TokenType.NUMBER

    def test_level_number_value(self) -> None:
        """``TokenType.LEVEL_NUMBER`` has value ``'level_number'``."""
        assert TokenType("level_number") is TokenType.LEVEL_NUMBER

    def test_pic_value(self) -> None:
        """``TokenType.PIC`` has value ``'pic'``."""
        assert TokenType("pic") is TokenType.PIC

    def test_period_value(self) -> None:
        """``TokenType.PERIOD`` has value ``'period'``."""
        assert TokenType("period") is TokenType.PERIOD

    def test_comma_value(self) -> None:
        """``TokenType.COMMA`` has value ``'comma'``."""
        assert TokenType("comma") is TokenType.COMMA

    def test_lparen_value(self) -> None:
        """``TokenType.LPAREN`` has value ``'lparen'``."""
        assert TokenType("lparen") is TokenType.LPAREN

    def test_rparen_value(self) -> None:
        """``TokenType.RPAREN`` has value ``'rparen'``."""
        assert TokenType("rparen") is TokenType.RPAREN

    def test_eof_value(self) -> None:
        """``TokenType.EOF`` has value ``'eof'``."""
        assert TokenType("eof") is TokenType.EOF

    def test_unknown_value(self) -> None:
        """``TokenType.UNKNOWN`` has value ``'unknown'``."""
        assert TokenType("unknown") is TokenType.UNKNOWN


# ---------------------------------------------------------------------------
# Identity and comparison
# ---------------------------------------------------------------------------


class TestTokenTypeIdentity:
    """Tests identity and comparison semantics of ``TokenType``."""

    def test_member_is_itself(self) -> None:
        """Each member is identical to itself."""
        assert TokenType.EOF is TokenType.EOF

    def test_different_members_are_not_equal(self) -> None:
        """Two distinct members are not equal."""
        assert TokenType.IDENTIFIER is not TokenType.KEYWORD

    def test_invalid_value_raises_value_error(self) -> None:
        """Constructing a ``TokenType`` with an unknown value raises."""
        with pytest.raises(ValueError):
            TokenType("not_a_valid_token_type")

    def test_invalid_name_raises_key_error(self) -> None:
        """Accessing a ``TokenType`` by an unknown name raises."""
        with pytest.raises(KeyError):
            _ = TokenType["NOT_A_MEMBER"]
