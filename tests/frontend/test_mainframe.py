"""
Tests for :mod:`app.frontend.mainframe` -- the AI Core state model.

Pure unit tests: ``compute_chip_state`` must be a direct, honest
function of backend facts, never a guess or a timer.
"""

import sys
from unittest.mock import MagicMock

mock_st = MagicMock()
sys.modules.setdefault("streamlit", mock_st)

from app.frontend.mainframe import (  # noqa: E402
    SUBSYSTEM_LABELS,
    ChipState,
    compute_chip_state,
)


def test_no_result_is_idle():
    state = compute_chip_state(
        has_analysis_result=False,
        is_loading=False,
        insufficient_data=False,
        risk_count=0,
    )
    assert state is ChipState.IDLE


def test_loading_is_analyzing_regardless_of_other_facts():
    state = compute_chip_state(
        has_analysis_result=True, is_loading=True, insufficient_data=True, risk_count=5
    )
    assert state is ChipState.ANALYZING


def test_clean_result_is_analysis_complete():
    state = compute_chip_state(
        has_analysis_result=True,
        is_loading=False,
        insufficient_data=False,
        risk_count=0,
    )
    assert state is ChipState.ANALYSIS_COMPLETE


def test_insufficient_data_is_warning_not_a_fake_success():
    state = compute_chip_state(
        has_analysis_result=True, is_loading=False, insufficient_data=True, risk_count=0
    )
    assert state is ChipState.WARNING


def test_risks_present_is_warning():
    state = compute_chip_state(
        has_analysis_result=True,
        is_loading=False,
        insufficient_data=False,
        risk_count=3,
    )
    assert state is ChipState.WARNING


def test_unreachable_states_are_never_produced_by_compute_chip_state():
    """JAVA_GENERATED / COMPILED / BEHAVIOR_* / VERIFIED require backend
    surfaces (Java generation, compilation, behavioral validation) that
    have no API route yet -- compute_chip_state must never claim them."""
    unreachable = {
        ChipState.JAVA_GENERATED,
        ChipState.COMPILED,
        ChipState.BEHAVIOR_INCONCLUSIVE,
        ChipState.BEHAVIOR_FAIL,
        ChipState.VERIFIED,
    }
    reachable = set()
    for has_result in (True, False):
        for loading in (True, False):
            for insufficient in (True, False):
                for risks in (0, 1, 5):
                    reachable.add(
                        compute_chip_state(
                            has_analysis_result=has_result,
                            is_loading=loading,
                            insufficient_data=insufficient,
                            risk_count=risks,
                        )
                    )
    assert reachable.isdisjoint(unreachable)


def test_five_subsystem_labels_for_the_landing_diagram():
    """The diagram's left-side subsystem labels are purely illustrative
    under the Stitch redesign (navigation moved to the sidebar in
    app.py) -- this just guards against an accidental empty/duplicate
    label list."""
    assert len(SUBSYSTEM_LABELS) == 5
    assert len(set(SUBSYSTEM_LABELS)) == 5
