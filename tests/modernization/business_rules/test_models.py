"""Unit tests for the Phase 4 BusinessRule model (task #112)."""

from __future__ import annotations

import pytest

from app.modernization.business_rules.models import (
    BusinessRule,
    BusinessRuleCategory,
    RuleAction,
    RuleActionKind,
    RuleVariables,
)
from app.parser.lexer.position import Position

_POS = Position(line=3, column=5, offset=40, filename="t.cbl")


def _action() -> RuleAction:
    return RuleAction(
        kind=RuleActionKind.ASSIGN,
        target="WS-RESULT",
        sources=(),
        literals=("'VALID'",),
        raw="WS-RESULT = 'VALID'",
        source_location=_POS,
    )


def _rule(**overrides) -> BusinessRule:
    base = dict(
        rule_id="BR-001",
        category=BusinessRuleCategory.CONDITIONAL_VALIDATION,
        description="When WS-STATUS = 'A', set WS-RESULT to 'VALID'.",
        condition="WS-STATUS = 'A'",
        actions=(_action(),),
        variables=RuleVariables(
            reads=("WS-STATUS",), writes=("WS-RESULT",), conditions=("WS-STATUS",)
        ),
        dependencies=("WS-STATUS",),
        source_locations=(_POS,),
        paragraph="MAIN",
        section=None,
        confidence=1.0,
    )
    base.update(overrides)
    return BusinessRule(**base)


def test_rule_is_frozen() -> None:
    rule = _rule()
    with pytest.raises(Exception):
        rule.condition = "x"  # type: ignore[misc]


def test_empty_condition_rejected() -> None:
    with pytest.raises(ValueError, match="condition cannot be empty"):
        _rule(condition="   ")


def test_no_actions_rejected() -> None:
    with pytest.raises(ValueError, match="at least one action"):
        _rule(actions=())


@pytest.mark.parametrize("bad", [-0.01, 1.5, 2.0, -1.0])
def test_confidence_out_of_range_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        _rule(confidence=bad)


@pytest.mark.parametrize("ok", [0.0, 0.5, 0.75, 1.0])
def test_confidence_in_range_accepted(ok: float) -> None:
    assert _rule(confidence=ok).confidence == ok


def test_section_is_always_none_by_default() -> None:
    # The parser does not model PROCEDURE DIVISION sections.
    assert _rule().section is None


def test_dedup_key_distinguishes_paragraph() -> None:
    a = _rule(paragraph="P1")
    b = _rule(paragraph="P2")
    assert a.dedup_key() != b.dedup_key()


def test_dedup_key_matches_same_structure() -> None:
    a = _rule(rule_id="BR-001")
    b = _rule(rule_id="BR-999")
    assert a.dedup_key() == b.dedup_key()


def test_to_dict_is_json_safe_and_deterministic() -> None:
    import json

    rule = _rule()
    d1 = rule.to_dict()
    d2 = rule.to_dict()
    assert d1 == d2
    json.dumps(d1)  # must not raise
    assert d1["rule_id"] == "BR-001"
    assert d1["category"] == "CONDITIONAL_VALIDATION"
    assert d1["actions"][0]["kind"] == "ASSIGN"
    assert d1["source_locations"][0]["line"] == 3
    assert d1["section"] is None
