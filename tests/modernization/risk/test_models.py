"""Unit tests for the ModernizationRisk model (task #113)."""

from __future__ import annotations

import pytest

from app.modernization.risk.models import (
    SEVERITY_ORDER,
    ModernizationRisk,
    RiskCategory,
    RiskSeverity,
)


def _risk(**overrides) -> ModernizationRisk:
    base = dict(
        risk_id="RISK-external-call-001",
        category=RiskCategory.EXTERNAL_CALL,
        severity=RiskSeverity.MEDIUM,
        title="External CALL dependency: PAY",
        explanation="calls a separately compiled unit",
        evidence=("1 CALL site to 'PAY'",),
        recommended_mitigation="document the interface",
    )
    base.update(overrides)
    return ModernizationRisk(**base)


def test_frozen() -> None:
    with pytest.raises(Exception):
        _risk().severity = RiskSeverity.LOW  # type: ignore[misc]


def test_requires_evidence() -> None:
    with pytest.raises(ValueError, match="at least one evidence"):
        _risk(evidence=())


def test_requires_explanation() -> None:
    with pytest.raises(ValueError, match="explanation cannot be empty"):
        _risk(explanation="  ")


@pytest.mark.parametrize("bad", [-0.1, 1.01, 5.0])
def test_confidence_range(bad: float) -> None:
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        _risk(confidence=bad)


def test_occurrence_count_min() -> None:
    with pytest.raises(ValueError, match="occurrence_count"):
        _risk(occurrence_count=0)


def test_severity_order_is_total_and_critical_first() -> None:
    assert SEVERITY_ORDER[RiskSeverity.CRITICAL] < SEVERITY_ORDER[RiskSeverity.HIGH]
    assert SEVERITY_ORDER[RiskSeverity.HIGH] < SEVERITY_ORDER[RiskSeverity.MEDIUM]
    assert SEVERITY_ORDER[RiskSeverity.MEDIUM] < SEVERITY_ORDER[RiskSeverity.LOW]
    assert len(set(SEVERITY_ORDER.values())) == 4


def test_dedup_key() -> None:
    a = _risk(affected_components=("P1", "P2"))
    b = _risk(affected_components=("P2", "P1"))
    assert a.dedup_key() == b.dedup_key()
    c = _risk(title="different")
    assert a.dedup_key() != c.dedup_key()


def test_to_dict_json_safe() -> None:
    import json

    d = _risk().to_dict()
    json.dumps(d)
    assert d["category"] == "EXTERNAL_CALL"
    assert d["severity"] == "MEDIUM"
    assert d["occurrence_count"] == 1
