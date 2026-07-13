"""
Unit tests for :class:`app.parser.lexer.position.Position`.

Purpose:
    Verify that the ``Position`` frozen dataclass satisfies the
    immutability, equality, hashing, and repr contracts required by
    all downstream parser and diagnostic components.

Responsibilities:
    - Assert that ``Position`` instances are immutable (frozen).
    - Assert structural equality and hash consistency.
    - Assert that the dataclass ``__repr__`` includes all field values.

Dependencies:
    - :mod:`app.parser.lexer.position` — ``Position`` under test.
    - pytest

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import dataclasses

import pytest

from app.parser.lexer.position import Position

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_position() -> Position:
    """Return a representative :class:`Position` for use in multiple tests."""
    return Position(line=10, column=5, offset=200, filename="PAYROLL.cbl")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestPositionConstruction:
    """Tests that ``Position`` is constructed correctly."""

    def test_fields_are_accessible(self, sample_position: Position) -> None:
        """All four fields are accessible by name after construction."""
        assert sample_position.line == 10
        assert sample_position.column == 5
        assert sample_position.offset == 200
        assert sample_position.filename == "PAYROLL.cbl"

    def test_first_position(self) -> None:
        """A position at the very start of a file is valid."""
        pos = Position(line=1, column=1, offset=0, filename="FIRST.cbl")
        assert pos.line == 1
        assert pos.column == 1
        assert pos.offset == 0

    def test_empty_filename_is_allowed(self) -> None:
        """An empty string is a valid filename (e.g. synthetic tokens)."""
        pos = Position(line=1, column=1, offset=0, filename="")
        assert pos.filename == ""


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestPositionImmutability:
    """Tests that ``Position`` is truly immutable (frozen dataclass)."""

    def test_cannot_set_line(self, sample_position: Position) -> None:
        """Assigning to ``line`` raises :exc:`FrozenInstanceError`."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_position.line = 99  # type: ignore[misc]

    def test_cannot_set_column(self, sample_position: Position) -> None:
        """Assigning to ``column`` raises :exc:`FrozenInstanceError`."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_position.column = 99  # type: ignore[misc]

    def test_cannot_set_offset(self, sample_position: Position) -> None:
        """Assigning to ``offset`` raises :exc:`FrozenInstanceError`."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_position.offset = 99  # type: ignore[misc]

    def test_cannot_set_filename(self, sample_position: Position) -> None:
        """Assigning to ``filename`` raises :exc:`FrozenInstanceError`."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_position.filename = "OTHER.cbl"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Equality
# ---------------------------------------------------------------------------


class TestPositionEquality:
    """Tests structural equality semantics of ``Position``."""

    def test_equal_positions(self) -> None:
        """Two positions with identical field values are equal."""
        p1 = Position(line=1, column=1, offset=0, filename="A.cbl")
        p2 = Position(line=1, column=1, offset=0, filename="A.cbl")
        assert p1 == p2

    def test_different_line_not_equal(self) -> None:
        """Positions differing only in ``line`` are not equal."""
        p1 = Position(line=1, column=1, offset=0, filename="A.cbl")
        p2 = Position(line=2, column=1, offset=0, filename="A.cbl")
        assert p1 != p2

    def test_different_column_not_equal(self) -> None:
        """Positions differing only in ``column`` are not equal."""
        p1 = Position(line=1, column=1, offset=0, filename="A.cbl")
        p2 = Position(line=1, column=2, offset=0, filename="A.cbl")
        assert p1 != p2

    def test_different_offset_not_equal(self) -> None:
        """Positions differing only in ``offset`` are not equal."""
        p1 = Position(line=1, column=1, offset=0, filename="A.cbl")
        p2 = Position(line=1, column=1, offset=1, filename="A.cbl")
        assert p1 != p2

    def test_different_filename_not_equal(self) -> None:
        """Positions differing only in ``filename`` are not equal."""
        p1 = Position(line=1, column=1, offset=0, filename="A.cbl")
        p2 = Position(line=1, column=1, offset=0, filename="B.cbl")
        assert p1 != p2


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


class TestPositionHashing:
    """Tests that ``Position`` is hashable and usable in sets/dicts."""

    def test_equal_positions_have_equal_hashes(self) -> None:
        """Equal positions share the same hash value."""
        p1 = Position(line=5, column=3, offset=42, filename="X.cbl")
        p2 = Position(line=5, column=3, offset=42, filename="X.cbl")
        assert hash(p1) == hash(p2)

    def test_position_usable_as_dict_key(self, sample_position: Position) -> None:
        """A ``Position`` can be used as a dictionary key."""
        mapping = {sample_position: "token_a"}
        assert mapping[sample_position] == "token_a"

    def test_position_usable_in_set(self, sample_position: Position) -> None:
        """Identical positions collapse to a single element in a set."""
        p2 = Position(
            line=sample_position.line,
            column=sample_position.column,
            offset=sample_position.offset,
            filename=sample_position.filename,
        )
        positions = {sample_position, p2}
        assert len(positions) == 1


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestPositionRepr:
    """Tests the string representation produced by the frozen dataclass."""

    def test_repr_contains_all_fields(self, sample_position: Position) -> None:
        """The repr string contains all four field names and values."""
        r = repr(sample_position)
        assert "Position" in r
        assert "line=10" in r
        assert "column=5" in r
        assert "offset=200" in r
        assert "PAYROLL.cbl" in r
