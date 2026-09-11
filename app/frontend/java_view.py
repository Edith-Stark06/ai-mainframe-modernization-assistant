"""
Phase 12 (Stitch redesign) -- COBOL <-> Java view (#137), backed by the real
``POST /workspaces/{id}/modernization/java`` endpoint (#126/#127) and the
existing ``GET /workspaces/{id}/files/{filename}`` endpoint for the COBOL
source itself.

Every mapping shown comes from a real ``GeneratedJavaArtifact.
source_locations`` entry -- nothing here re-derives or guesses a
COBOL<->Java correspondence. ``behavioral_status`` is passed in by the
caller (sourced from the Java Workspace endpoint, which is the only place
behavioral-equivalence status actually lives) rather than fabricated here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.components import section_header, status_matrix
from app.frontend.theme import status_pill

__all__ = ["render_java_view"]


def render_java_view(
    java_response: Optional[Dict[str, Any]],
    cobol_source: Optional[str],
    *,
    behavioral_status: Optional[str] = None,
    error: Optional[str],
) -> None:
    section_header("COBOL ↔ Java")
    if error:
        st.error(error)
        return
    if java_response is None:
        st.info("Run analysis from the sidebar to generate Java.")
        return

    if not java_response.get("available"):
        st.markdown(status_pill("NOT AVAILABLE", "UNAVAILABLE"), unsafe_allow_html=True)
        st.caption(java_response.get("reason") or "Java generation could not run.")
        return

    project = java_response["project"]
    compilation = java_response.get("compilation")

    compile_status = (
        ("PASS" if compilation["success"] else "FAIL")
        if compilation is not None
        else "NOT_AVAILABLE"
    )
    status_matrix(
        [
            ("Generation", "PASS"),
            ("Compilation", compile_status),
            ("Behavior", behavioral_status or "NOT_AVAILABLE"),
        ]
    )

    if compilation is not None and not compilation["success"]:
        with st.expander(f"{len(compilation['diagnostics'])} compiler diagnostic(s)"):
            for d in compilation["diagnostics"]:
                st.write(
                    f"- **{d['severity']}**: {d['message']} ({d.get('file')}:{d.get('line')})"
                )

    java_files = {p: c for p, c in project["files"].items() if p.endswith(".java")}
    selected_file = st.selectbox(
        "Generated Java file", options=sorted(java_files.keys())
    )

    left, right = st.columns(2)
    with left:
        st.caption("COBOL source")
        if cobol_source:
            st.code(cobol_source, language="cobol", line_numbers=True)
        else:
            st.info("COBOL source could not be loaded.")
    with right:
        st.caption(selected_file)
        st.code(java_files.get(selected_file, ""), language="java", line_numbers=True)

    artifacts = [
        a for a in project.get("artifacts", []) if a["file_path"] == selected_file
    ]
    if not artifacts:
        st.caption("No traceability artifacts recorded for this file.")
        return

    st.markdown("**Active Business Rule**")
    labels = [
        f"{a.get('method_name') or a['class_name']} ({a['kind']})" for a in artifacts
    ]
    idx = st.selectbox(
        "Java member", options=range(len(artifacts)), format_func=lambda i: labels[i]
    )
    artifact = artifacts[idx]

    cols = st.columns(3)
    cols[0].caption(f"Mapping: {artifact['mapping_status']}")
    cols[1].caption(
        f"Business rules: {', '.join(artifact['business_rule_ids']) or '—'}"
    )
    cols[2].caption(
        f"Architecture component: {artifact.get('architecture_component_id') or '—'}"
    )

    if artifact["source_locations"]:
        for loc in artifact["source_locations"]:
            rendered = loc.get("source_path", "")
            if loc.get("line_start"):
                rendered += f":{loc['line_start']}"
                if loc.get("line_end") and loc["line_end"] != loc["line_start"]:
                    rendered += f"-{loc['line_end']}"
            if loc.get("paragraph"):
                rendered += f" ({loc['paragraph']})"
            st.caption(f"COBOL: {rendered}")
    else:
        st.caption("No COBOL source mapping recorded for this member.")
    st.caption(f"Java: {selected_file}")

    if artifact.get("unsupported_behaviors"):
        with st.expander(
            f"⚠ {len(artifact['unsupported_behaviors'])} unsupported construct(s)"
        ):
            for u in artifact["unsupported_behaviors"]:
                st.write(f"- **{u['construct_name']}**: {u['explanation']}")
