"""Tests for business rule domain models."""

import pytest
from app.analysis.rules.models import BusinessRule
from app.parser.lexer.position import Position


def test_valid_rule_single_action() -> None:
    """A valid rule can be created with a single action."""
    rule = BusinessRule(
        condition="YEARS-SERVICE > 5", actions=("BONUS = SALARY * .20",)
    )
    assert rule.condition == "YEARS-SERVICE > 5"
    assert rule.actions == ("BONUS = SALARY * .20",)
    assert rule.source_location is None


def test_valid_rule_multiple_actions() -> None:
    """A valid rule can be created with multiple actions."""
    rule = BusinessRule(
        condition="YEARS-SERVICE > 5",
        actions=("BONUS = SALARY * .20", "HOLIDAY-DAYS = 25"),
    )
    assert rule.condition == "YEARS-SERVICE > 5"
    assert rule.actions == ("BONUS = SALARY * .20", "HOLIDAY-DAYS = 25")
    assert len(rule.actions) == 2


def test_rule_with_source_location() -> None:
    """A rule can carry a precise source location."""
    pos = Position(line=10, column=5, offset=100, filename="TEST.cbl")
    rule = BusinessRule(condition="X = Y", actions=("Z = 1",), source_location=pos)
    assert rule.source_location == pos
    assert rule.source_location.line == 10
    assert rule.source_location.filename == "TEST.cbl"


def test_rule_equality() -> None:
    """Rules with identical contents evaluate as equal and share a hash."""
    pos = Position(line=1, column=1, offset=0, filename="A.cbl")
    rule1 = BusinessRule(condition="A > B", actions=("C = 1",), source_location=pos)
    rule2 = BusinessRule(condition="A > B", actions=("C = 1",), source_location=pos)
    assert rule1 == rule2
    assert hash(rule1) == hash(rule2)


def test_rule_inequality() -> None:
    """Rules with differing contents evaluate as not equal."""
    rule1 = BusinessRule(condition="A > B", actions=("C = 1",))
    rule2 = BusinessRule(condition="A > B", actions=("C = 2",))
    rule3 = BusinessRule(condition="A < B", actions=("C = 1",))

    assert rule1 != rule2
    assert rule1 != rule3
    assert rule2 != rule3


def test_rule_immutability() -> None:
    """Rules are frozen and cannot be mutated after creation."""
    rule = BusinessRule(condition="A > B", actions=("C = 1",))
    with pytest.raises(Exception):
        # dataclasses.FrozenInstanceError is a subclass of Exception
        rule.condition = "X > Y"  # type: ignore[misc]


def test_rule_invalid_empty_condition() -> None:
    """A rule cannot be created with an empty condition."""
    with pytest.raises(ValueError, match="cannot be empty"):
        BusinessRule(condition="", actions=("A = B",))


def test_rule_invalid_empty_actions() -> None:
    """A rule cannot be created with zero actions."""
    with pytest.raises(ValueError, match="must have at least one action"):
        BusinessRule(condition="A > B", actions=())
