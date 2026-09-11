"""
Phase 12 (Stitch redesign) -- Java Workspace view, backed by the real
``POST /workspaces/{id}/modernization/java-workspace`` endpoint.

Shows generation/compilation/behavioral/self-repair status, generated
Java files, candidate lineage, repair history, diagnostics, human
review, and the audit trail -- all rendered directly from the API
response. Quality-loop fields (iterations, repair history, human
review, audit trail) are honestly empty here (no AI provider
configured in this environment) and are rendered as an explicit
NOT AVAILABLE state, never inferred or fabricated from the fact that a
candidate exists.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.components import section_header, status_matrix
from app.frontend.theme import status_pill

__all__ = ["render_java_workspace"]


def render_java_workspace(
    workspace: Optional[Dict[str, Any]], *, error: Optional[str]
) -> None:
    section_header("Java Workspace")
    if error:
        st.error(error)
        return
    if workspace is None:
        st.info("Run analysis from the sidebar to populate the Java workspace.")
        return

    gen_status = "PASS" if workspace["generation_available"] else "FAIL"
    repair_status = "PASS" if workspace["quality_loop_available"] else "NOT_AVAILABLE"
    status_matrix(
        [
            ("Generation", gen_status),
            ("Compilation", workspace["compilation_status"]),
            ("Behavioral Validation", workspace["behavioral_status"]),
            ("Self Repair", repair_status),
        ]
    )

    if not workspace["generation_available"]:
        st.warning(
            workspace.get("generation_reason") or "Java generation is unavailable."
        )
        return

    st.markdown("**Project**")
    project = workspace["project"]
    for path in sorted(project["files"].keys()):
        if path.endswith(".java"):
            with st.expander(path):
                st.code(project["files"][path], language="java")

    if not workspace["compilation"]["success"]:
        with st.expander("Diagnostics (compilation)"):
            for d in workspace["compilation"]["diagnostics"]:
                st.write(
                    f"- **{d['severity']}**: {d['message']} ({d.get('file')}:{d.get('line')})"
                )

    st.markdown("**Candidate Lineage**")
    lineage = workspace.get("candidate_lineage") or []
    if not lineage:
        st.caption("No candidate identity available.")
    for candidate in lineage:
        origin = "repair" if candidate["created_from_repair"] else "initial generation"
        st.write(
            f"- `{candidate['candidate_id']}` (v{candidate['version']}, from {origin})"
        )

    st.markdown("**Repair History**")
    st.markdown(
        status_pill("NOT AVAILABLE", "UNAVAILABLE"),
        unsafe_allow_html=True,
    )
    st.caption(workspace["quality_loop_reason"])
    st.caption(
        f"Iterations: {workspace['iteration_count']} · "
        f"Repairs applied: {workspace['repair_count']}"
    )

    st.markdown("**Human Review**")
    if workspace["human_review_checkpoints"]:
        for checkpoint in workspace["human_review_checkpoints"]:
            st.write(f"- {checkpoint['reason']} ({checkpoint['status']})")
    else:
        st.caption(
            "Required: Yes"
            if workspace["human_review_required"]
            else "No checkpoints recorded."
        )

    st.markdown("**Audit Trail**")
    if workspace["audit_trail"]:
        for event in workspace["audit_trail"]:
            st.write(
                f"- [{event['sequence']}] {event['event_type']} — {event['decision']}"
            )
    else:
        st.caption(
            "No audit trail -- the quality loop has not been run for this analysis."
        )
