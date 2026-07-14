"""
Unit tests for :class:`app.parser.lexer.source_format.SourceFormat`.

Purpose:
    Verify that the ``SourceFormat`` enumeration contains exactly the
    members required by TASK-007, that all values are unique, and that
    the enumeration lookup and identity behaviour is correct.

Responsibilities:
    - Assert the presence of ``UNKNOWN``, ``FIXED``, and ``FREE``.
    - Assert that no extra members exist.
    - Assert value uniqueness (guaranteed by ``@unique``).
    - Assert member retrieval by name and by value.

Dependencies:
    - :mod:`app.parser.lexer.source_format` — ``SourceFormat`` under test.
    - pytest

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest

from app.parser.lexer.source_format import SourceFormat

# ---------------------------------------------------------------------------
# Expected specification
# ---------------------------------------------------------------------------

#: The exact set of member names mandated by TASK-007.
REQUIRED_MEMBERS: frozenset[str] = frozenset({"UNKNOWN", "FIXED", "FREE"})


# ---------------------------------------------------------------------------
# Member presence
# ---------------------------------------------------------------------------


class TestSourceFormatMembersExist:
    """Tests that every required member is present in the enumeration."""

    @pytest.mark.parametrize("name", sorted(REQUIRED_MEMBERS))
    def test_required_member_exists(self, name: str) -> None:
        """Each required member name resolves to a ``SourceFormat`` instance."""
        member = SourceFormat[name]
        assert isinstance(member, SourceFormat)
        assert member.name == name

    def test_total_member_count(self) -> None:
        """The enum contains exactly three members."""
        assert len(SourceFormat) == len(REQUIRED_MEMBERS)

    def test_no_extra_members(self) -> None:
        """No member names exist beyond those required by the spec."""
        actual_names = {m.name for m in SourceFormat}
        assert actual_names == REQUIRED_MEMBERS


# ---------------------------------------------------------------------------
# Value uniqueness
# ---------------------------------------------------------------------------


class TestSourceFormatUniqueness:
    """Tests that all enum values are distinct."""

    def test_all_values_are_distinct(self) -> None:
        """Every ``SourceFormat`` member has a distinct string value."""
        values = [m.value for m in SourceFormat]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Value correctness
# ---------------------------------------------------------------------------


class TestSourceFormatValues:
    """Tests that string values match the documented specification."""

    def test_unknown_value(self) -> None:
        """``SourceFormat.UNKNOWN`` has value ``'unknown'``."""
        assert SourceFormat.UNKNOWN.value == "unknown"

    def test_fixed_value(self) -> None:
        """``SourceFormat.FIXED`` has value ``'fixed'``."""
        assert SourceFormat.FIXED.value == "fixed"

    def test_free_value(self) -> None:
        """``SourceFormat.FREE`` has value ``'free'``."""
        assert SourceFormat.FREE.value == "free"


# ---------------------------------------------------------------------------
# Lookup by value
# ---------------------------------------------------------------------------


class TestSourceFormatValueLookup:
    """Tests that members can be retrieved by their string value."""

    def test_lookup_unknown(self) -> None:
        """``SourceFormat('unknown')`` returns ``UNKNOWN``."""
        assert SourceFormat("unknown") is SourceFormat.UNKNOWN

    def test_lookup_fixed(self) -> None:
        """``SourceFormat('fixed')`` returns ``FIXED``."""
        assert SourceFormat("fixed") is SourceFormat.FIXED

    def test_lookup_free(self) -> None:
        """``SourceFormat('free')`` returns ``FREE``."""
        assert SourceFormat("free") is SourceFormat.FREE

    def test_invalid_value_raises(self) -> None:
        """Constructing with an unknown value raises ``ValueError``."""
        with pytest.raises(ValueError):
            SourceFormat("not_a_format")


# ---------------------------------------------------------------------------
# Identity and comparison
# ---------------------------------------------------------------------------


class TestSourceFormatIdentity:
    """Tests identity and comparison semantics."""

    def test_member_is_itself(self) -> None:
        """Each member is identical to itself."""
        assert SourceFormat.FIXED is SourceFormat.FIXED

    def test_distinct_members_are_not_equal(self) -> None:
        """Two distinct members are never equal."""
        assert SourceFormat.FIXED is not SourceFormat.FREE
        assert SourceFormat.FIXED is not SourceFormat.UNKNOWN
        assert SourceFormat.FREE is not SourceFormat.UNKNOWN

    def test_invalid_name_raises(self) -> None:
        """Accessing by unknown name raises ``KeyError``."""
        with pytest.raises(KeyError):
            _ = SourceFormat["NOT_A_FORMAT"]
