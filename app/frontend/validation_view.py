"""
Phase 12 -- Validation Center view (#140), backed by the real
``POST /workspaces/{id}/modernization/validation`` endpoint.

Renders exactly the PASS / FAIL / INCONCLUSIVE / NOT_AVAILABLE status
the backend computed for each stage. Never renders "Ready for
Modernization" or any equivalent claim unless ``overall_status`` is
genuinely "PASS".
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from app.frontend.theme import status_pill

__all__ = ["render_validation"]

_OVERALL_HEADLINE = {
    "PASS": "READY FOR MODERNIZATION",
    "FAIL": "NOT READY — VERIFIED FAILURE",
    "INCONCLUSIVE": "INCONCLUSIVE — NOT ALL STAGES COULD BE VERIFIED",
    "NOT_AVAILABLE": "VALIDATION NOT AVAILABLE",
}


def render_validation(validation: Dict[str, Any] | None, *, error: str | None) -> None:
    st.subheader("Validation Center")
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

    cols = st.columns(3)
    for i, stage in enumerate(validation["stages"]):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(
                    f"**{stage['stage']}**  \n"
                    + status_pill(stage["status"], stage["status"]),
                    unsafe_allow_html=True,
                )
                st.caption(stage["summary"])
                if stage.get("details"):
                    with st.expander("Details"):
                        st.json(stage["details"])
