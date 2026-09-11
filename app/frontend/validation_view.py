"""
Phase 12 (Stitch redesign) -- Validation Center view (#140), backed by the
real ``POST /workspaces/{id}/modernization/validation`` endpoint.

Renders exactly the PASS / FAIL / INCONCLUSIVE / NOT_AVAILABLE status the
backend computed for each stage. Never renders "Ready for Modernization"
or any equivalent claim unless ``overall_status`` is genuinely "PASS".

``report`` is an optional, already-fetched ``/modernization/report``
response (same lazy-fetch pattern as every other view) used only to source
the real Coverage/Risks counts for the numeric stat row -- it is not
fetched or computed here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from app.frontend.components import (
    section_header,
    selectable_table,
    stat_row,
    status_matrix,
)
from app.frontend.theme import status_pill

__all__ = ["render_validation"]

_OVERALL_HEADLINE = {
    "PASS": "READY FOR MODERNIZATION",
    "FAIL": "NOT READY — VERIFIED FAILURE",
    "INCONCLUSIVE": "INCONCLUSIVE — NOT ALL STAGES COULD BE VERIFIED",
    "NOT_AVAILABLE": "VALIDATION NOT AVAILABLE",
}

_BEHAVIORAL_STAGE_NAMES = {"Behavioral Equivalence", "COBOL Tests"}
_BLOCKING_STATUSES = {"FAIL", "INCONCLUSIVE"}


def _validation_stat_items(
    stages: List[Dict[str, Any]], report: Optional[Dict[str, Any]]
) -> List[tuple[str, str]]:
    coverage = (report or {}).get("coverage")
    coverage_pct = f"{coverage['overall']:.0%}" if coverage else "—"
    behavioral_passes = sum(
        1
        for s in stages
        if s["stage"] in _BEHAVIORAL_STAGE_NAMES and s["status"] == "PASS"
    )
    inconclusive = sum(1 for s in stages if s["status"] == "INCONCLUSIVE")
    risks = report.get("risks") if report is not None else None
    risk_count = str(len(risks)) if risks is not None else "—"
    return [
        ("Analysis Coverage", coverage_pct),
        ("Behavioral Passes", str(behavioral_passes)),
        ("Inconclusive", str(inconclusive)),
        ("Risks", risk_count),
    ]


def render_validation(
    validation: Optional[Dict[str, Any]],
    *,
    report: Optional[Dict[str, Any]] = None,
    error: Optional[str],
) -> None:
    section_header("Validation Center")
    if error:
        st.error(error)
        return
    if validation is None:
        st.info("Run analysis from the sidebar to validate this file.")
        return

    overall = validation["overall_status"]
    st.markdown(
        f'<div class="mf-panel" style="text-align:center;">'
        f"{status_pill(_OVERALL_HEADLINE[overall], overall)}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Overall status reflects Parser, Analysis, Java Generation, "
        "Compilation, and Behavioral Equivalence only -- Risks, Unsupported "
        "Syntax, COBOL Tests, and Self Repair are informational and never "
        "gate this rollup on their own."
    )

    stages: List[Dict[str, Any]] = validation["stages"]
    status_matrix([(s["stage"], s["status"]) for s in stages])
    stat_row(_validation_stat_items(stages, report))

    blocking = [s for s in stages if s["status"] in _BLOCKING_STATUSES]
    st.markdown("**Blocking Issues**")
    if not blocking:
        st.caption("No blocking issues -- every gating stage passed.")
        return

    records = [
        {
            "Stage": s["stage"],
            "Status": s["status"],
            "Summary": s["summary"],
            "_stage": s,
        }
        for s in blocking
    ]
    selected = selectable_table(
        records, ["Stage", "Status", "Summary"], key="blocking_issues_table"
    )
    if selected is not None and selected["_stage"].get("details"):
        with st.expander(f"Details -- {selected['_stage']['stage']}"):
            st.json(selected["_stage"]["details"])
