"""Tests for business rule normalization."""

from app.analysis.rules.models import BusinessRule
from app.analysis.rules.normalization import normalize_business_rule
from app.parser.lexer.position import Position


def test_normalize_canonical_condition() -> None:
    """A condition is tokenised and reconstructed with exact spacing and uppercase."""
    rule = BusinessRule(condition="years-service    >   5", actions=("X = 1",))
    normalized = normalize_business_rule(rule)
    assert normalized.condition == "YEARS-SERVICE > 5"


def test_normalize_canonical_actions() -> None:
    """Actions are tokenised and reconstructed with exact spacing and uppercase."""
    rule = BusinessRule(condition="A > B", actions=("  bonus  =   salary * 0.20  ",))
    normalized = normalize_business_rule(rule)
    assert normalized.actions == ("BONUS = SALARY * 0 . 20",)


def test_normalize_multiple_actions() -> None:
    """All actions in a rule are normalized."""
    rule = BusinessRule(
        condition="A > B",
        actions=(
            "  x = 1 ",
            "y   =   2",
        ),
    )
    normalized = normalize_business_rule(rule)
    assert normalized.actions == ("X = 1", "Y = 2")


def test_normalize_preserves_source_location() -> None:
    """The original source location is passed to the normalized rule."""
    pos = Position(line=10, column=5, offset=100, filename="TEST.cbl")
    rule = BusinessRule(condition="X = 1", actions=("Y = 2",), source_location=pos)
    normalized = normalize_business_rule(rule)
    assert normalized.source_location is pos


def test_normalize_deterministic_output() -> None:
    """Different whitespace variants produce the exact same normalized rule."""
    rule1 = BusinessRule(condition="A>B", actions=("C=1",))
    rule2 = BusinessRule(condition="A > B", actions=("C = 1",))
    rule3 = BusinessRule(condition=" A  >  B ", actions=(" C  =  1 ",))

    norm1 = normalize_business_rule(rule1)
    norm2 = normalize_business_rule(rule2)
    norm3 = normalize_business_rule(rule3)

    assert norm1 == norm2 == norm3


def test_normalize_semantic_preservation() -> None:
    """String literals are preserved exactly, avoiding case modification."""
    rule = BusinessRule(condition="A = 'hello world'", actions=("DISPLAY 'Msg'",))
    normalized = normalize_business_rule(rule)
    assert normalized.condition == "A = 'hello world'"
    assert normalized.actions == ("DISPLAY 'Msg'",)


def test_normalize_unsupported_input() -> None:
    """If the lexer rejects the input, it falls back to basic string normalization."""
    # An unclosed string literal will cause a LexerError
    rule = BusinessRule(condition="A = 'unclosed", actions=("B = 1",))
    normalized = normalize_business_rule(rule)
    assert normalized.condition == "A = 'UNCLOSED"
    assert normalized.actions == ("B = 1",)
