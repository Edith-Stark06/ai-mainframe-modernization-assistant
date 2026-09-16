"""Unit tests for the strategy models (task #114)."""

from __future__ import annotations

import pytest

from app.modernization.strategy.models import (
    STRATEGY_PRECEDENCE,
    ModernizationStrategy,
    StrategyRecommendation,
)


def _rec(**over) -> StrategyRecommendation:
    base = dict(
        recommendation_id="STRAT-001",
        strategy=ModernizationStrategy.REFACTOR,
        is_primary=True,
        rationale="localized complexity",
        evidence=("parse complete",),
    )
    base.update(over)
    return StrategyRecommendation(**base)


def test_frozen() -> None:
    with pytest.raises(Exception):
        _rec().is_primary = False  # type: ignore[misc]


def test_requires_rationale() -> None:
    with pytest.raises(ValueError, match="rationale cannot be empty"):
        _rec(rationale=" ")


def test_requires_evidence() -> None:
    with pytest.raises(ValueError, match="at least one evidence"):
        _rec(evidence=())


@pytest.mark.parametrize("bad", [-0.1, 1.2])
def test_confidence_range(bad: float) -> None:
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        _rec(confidence=bad)


def test_precedence_is_total_and_rewrite_first() -> None:
    assert len(set(STRATEGY_PRECEDENCE.values())) == len(ModernizationStrategy)
    assert STRATEGY_PRECEDENCE[ModernizationStrategy.REWRITE] == 0
    assert STRATEGY_PRECEDENCE[ModernizationStrategy.REHOST] == max(
        STRATEGY_PRECEDENCE.values()
    )


def test_to_dict_json_safe() -> None:
    import json

    d = _rec(referenced_risk_ids=("RISK-external-call-001",)).to_dict()
    json.dumps(d)
    assert d["strategy"] == "REFACTOR"
    assert d["is_primary"] is True
    assert d["referenced_risk_ids"] == ["RISK-external-call-001"]
