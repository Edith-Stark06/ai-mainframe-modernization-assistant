"""
Phase 12 (Stitch redesign) -- Modernization Report view (#141), backed by
the real ``POST /workspaces/{id}/modernization/report`` endpoint, which
itself only aggregates the same data the other endpoints expose.

The only export offered is a JSON download of the exact response already
fetched and rendered on screen -- no PDF/fabricated document is generated,
since the backend does not provide safe report rendering beyond
structured JSON (see the frontend redesign's disclosed limitations).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.components import section_header, stat_row, status_matrix
from app.frontend.theme import status_pill

__all__ = ["render_report"]


def render_report(report: Optional[Dict[str, Any]], *, error: Optional[str]) -> None:
    if error:
        section_header("Modernization Assessment")
        st.error(error)
        return
    if report is None:
        section_header("Modernization Assessment")
        st.info("Run analysis from the sidebar to generate a report.")
        return

    section_header(
        "Modernization Assessment",
        report["filename"],
        eyebrow=report["overall_status"],
    )
    st.markdown(
        status_pill(f"Overall: {report['overall_status']}", report["overall_status"]),
        unsafe_allow_html=True,
    )
    st.download_button(
        "Export JSON",
        data=json.dumps(report, indent=2),
        file_name=f"{report['filename']}.modernization-report.json",
        mime="application/json",
    )

    st.markdown("**Executive Summary**")
    architecture = report.get("architecture")
    project = report.get("project")
    stat_row(
        [
            ("Paragraphs", str(len(report["paragraphs"]))),
            ("Business Rules", str(len(report["business_rules"] or []))),
            ("Dependencies", str(len(report["dependencies"] or []))),
            ("Risks", str(len(report["risks"] or []))),
            (
                "Components",
                str(len(architecture["components"])) if architecture else "—",
            ),
            (
                "Java Files",
                (
                    str(sum(1 for p in project["files"] if p.endswith(".java")))
                    if project
                    else "—"
                ),
            ),
        ]
    )

    st.markdown("**Program Profile**")
    st.caption(
        f"Source: `{report['source_id']}` — analysis success: {report['analysis_success']}"
    )
    st.caption(f"Paragraphs: {', '.join(report['paragraphs']) or '—'}")

    st.markdown("**Architecture**")
    if architecture:
        st.caption(f"{len(architecture['components'])} component(s) generated.")
    else:
        st.caption(report.get("architecture_reason") or "Not available.")

    st.markdown("**Business Rules & Dependencies**")
    st.caption(
        f"{len(report['business_rules'] or [])} rule(s) extracted, "
        f"{len(report['dependencies'] or [])} dependency reference(s)."
    )

    st.markdown("**Risks**")
    risks = report["risks"] or []
    if risks:
        for r in risks:
            st.write(f"- **{r['title']}** ({r['severity']}) — {r['explanation']}")
    else:
        st.caption(
            "No risks identified." if report["risks"] is not None else "Not available."
        )

    st.markdown("**Modernization Strategy**")
    strategy = (report.get("strategy") or {}).get("primary")
    st.caption(
        f"{strategy['strategy']} — {strategy['rationale']}"
        if strategy
        else "Not available."
    )

    st.markdown("**Java & Validation**")
    coverage = report.get("coverage")
    confidence = report.get("confidence")
    stat_row(
        [
            ("Coverage", f"{coverage['overall']:.0%}" if coverage else "—"),
            ("Confidence", f"{confidence['score']:.0%}" if confidence else "—"),
            (
                "Compilation",
                (
                    "PASS"
                    if report["compilation"] and report["compilation"]["success"]
                    else "—"
                ),
            ),
        ]
    )
    if not project:
        st.caption(report.get("generation_reason") or "Java generation: not available.")

    stage_cells = [
        (s["stage"], s["status"])
        for s in report["validation_stages"]
        if s["stage"] in ("Tests", "Behavioral Equivalence", "Self Repair")
    ]
    if stage_cells:
        status_matrix(stage_cells)

    st.markdown("**Unresolved Issues**")
    unsupported = report.get("unsupported_syntax") or {}
    if unsupported.get("detail"):
        st.caption(f"Unsupported constructs: {unsupported['detail']}")
    if report["unresolved_issues"]:
        for issue in report["unresolved_issues"]:
            st.write(f"- {issue}")
    else:
        st.success("No unresolved issues.")
