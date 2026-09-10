"""
Phase 12 -- Modernization Report view (#141), backed by the real
``POST /workspaces/{id}/modernization/report`` endpoint, which itself
only aggregates the same data the other new endpoints expose.

The only export offered is a JSON download of the exact response
already fetched and rendered on screen -- no PDF/fabricated document is
generated, since the backend does not provide safe report rendering
beyond structured JSON.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import streamlit as st

from app.frontend.theme import status_pill

__all__ = ["render_report"]


def render_report(report: Dict[str, Any] | None, *, error: str | None) -> None:
    st.subheader("Modernization Report")
    if error:
        st.error(error)
        return
    if report is None:
        st.info("Run analysis from the sidebar to generate a report.")
        return

    st.markdown(
        status_pill(f"Overall: {report['overall_status']}", report["overall_status"]),
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download report (JSON)",
        data=json.dumps(report, indent=2),
        file_name=f"{report['filename']}.modernization-report.json",
        mime="application/json",
    )

    st.markdown("### 1. Program Overview")
    st.write(
        f"Source: `{report['source_id']}` — analysis success: {report['analysis_success']}"
    )
    st.caption(
        f"{len(report['paragraphs'])} paragraph(s): {', '.join(report['paragraphs'])}"
    )

    st.markdown("### 2. Architecture")
    if report["architecture"]:
        st.caption(
            f"{len(report['architecture']['components'])} component(s) generated."
        )
    else:
        st.caption(report.get("architecture_reason") or "Not available.")

    st.markdown("### 3. Business Rules")
    st.caption(f"{len(report['business_rules'] or [])} rule(s) extracted.")

    st.markdown("### 4. Dependencies")
    st.caption(f"{len(report['dependencies'] or [])} dependency reference(s).")

    st.markdown("### 5. Risks")
    risks = report["risks"] or []
    if risks:
        for r in risks:
            st.write(f"- **{r['title']}** ({r['severity']}) — {r['explanation']}")
    else:
        st.caption(
            "No risks identified." if report["risks"] is not None else "Not available."
        )

    st.markdown("### 6. Coverage & 7. Confidence")
    cov_cols = st.columns(2)
    if report["coverage"]:
        cov_cols[0].metric("Coverage", f"{report['coverage']['overall']:.0%}")
    if report["confidence"]:
        cov_cols[1].metric("Confidence", f"{report['confidence']['score']:.0%}")

    st.markdown("### 8. Strategy")
    strategy = (report.get("strategy") or {}).get("primary")
    st.caption(
        f"{strategy['strategy']} — {strategy['rationale']}"
        if strategy
        else "Not available."
    )

    st.markdown("### 9-10. Generated Java & Compilation")
    if report["project"]:
        st.caption(f"{len(report['project']['files'])} file(s) generated.")
        if report["compilation"]:
            st.caption(
                f"Compilation: {'PASS' if report['compilation']['success'] else 'FAIL'}"
            )
    else:
        st.caption(report.get("generation_reason") or "Not available.")

    st.markdown("### 11-13. Tests, Behavioral Validation, Self-Repair")
    for stage_name in ("Tests", "Behavioral Equivalence", "Self Repair"):
        stage = next(
            (s for s in report["validation_stages"] if s["stage"] == stage_name), None
        )
        if stage:
            st.markdown(
                f"{stage['stage']}: " + status_pill(stage["status"], stage["status"]),
                unsafe_allow_html=True,
            )

    st.markdown("### 14. Unsupported Constructs")
    unsupported = report.get("unsupported_syntax") or {}
    st.caption(unsupported.get("detail", "Not available."))

    st.markdown("### 15. Unresolved Issues")
    if report["unresolved_issues"]:
        for issue in report["unresolved_issues"]:
            st.write(f"- {issue}")
    else:
        st.success("No unresolved issues.")
