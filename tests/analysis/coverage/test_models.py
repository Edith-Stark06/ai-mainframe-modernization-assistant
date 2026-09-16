"""Unit tests for the #115 coverage models."""

from __future__ import annotations

import json

import pytest

from app.analysis.coverage.models import (
    CoverageDimension,
    CoverageReport,
    CoverageStatus,
    UnsupportedSyntaxCoverage,
)


def _dim(name: str, ratio: float, status: CoverageStatus) -> CoverageDimension:
    return CoverageDimension(
        name=name, ratio=ratio, covered=1, total=2, status=status, detail="x"
    )


@pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -5.0])
def test_dimension_rejects_out_of_bounds_ratio(bad: float) -> None:
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        CoverageDimension(
            name="x", ratio=bad, covered=0, total=1, status=CoverageStatus.PARTIAL
        )


def test_dimension_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        CoverageDimension(
            name="x", ratio=0.5, covered=-1, total=1, status=CoverageStatus.PARTIAL
        )


def test_not_measurable_is_excluded_from_measurable() -> None:
    d = _dim("x", 1.0, CoverageStatus.NOT_MEASURABLE)
    assert d.measurable is False
    assert _dim("y", 0.5, CoverageStatus.PARTIAL).measurable is True


def _report(overall: float, dims_status: CoverageStatus) -> CoverageReport:
    d = _dim("d", overall if overall > 0 else 0.5, dims_status)
    return CoverageReport(
        lexical=d,
        parser=d,
        statement=d,
        ast=d,
        ir=d,
        control_flow=d,
        dependency=d,
        business_rule=d,
        unsupported_syntax=UnsupportedSyntaxCoverage(0, 0),
        overall=overall,
        overall_status=dims_status,
    )


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_report_rejects_out_of_bounds_overall(bad: float) -> None:
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        _report(bad, CoverageStatus.PARTIAL)


def test_report_dimensions_tuple_has_eight_named_stages() -> None:
    r = _report(1.0, CoverageStatus.COMPLETE)
    assert [d.name for d in r.dimensions] == [
        "d",
        "d",
        "d",
        "d",
        "d",
        "d",
        "d",
        "d",
    ]
    assert len(r.dimensions) == 8


def test_report_to_dict_json_safe() -> None:
    r = _report(0.75, CoverageStatus.PARTIAL)
    d = r.to_dict()
    json.dumps(d)
    assert d["overall"] == 0.75
    assert d["overall_status"] == "PARTIAL"
    assert set(d) == {
        "overall",
        "overall_status",
        "dimensions",
        "unsupported_syntax",
        "notes",
    }


def test_unsupported_syntax_rejects_negative() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        UnsupportedSyntaxCoverage(distinct_codes=-1, total_occurrences=0)
