"""
Report: the modernization assessment of one file.

Purpose:
    The aggregate ``POST /workspaces/{id}/modernization/report`` response laid
    out as a document an engineer can read top to bottom and export.

Responsibilities:
    - :func:`report_markdown` -- the same report as a Markdown document.
    - :func:`render_report` -- the on-screen report and its two exports.

Non-responsibilities:
    - Computing anything. Every figure, status and sentence is taken from the
      response; a missing value is shown as unavailable, never as zero.

Design note:
    Both exports (JSON, Markdown) are built from the response already on
    screen. No PDF is generated: the backend offers no safe rendering beyond
    structured data, and a fabricated document would be worse than none.

Dependencies:
    - streamlit, app.frontend.{components,design.ui}

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import streamlit as st

from app.frontend.components import section_header, subsection
from app.frontend.design import ui
from app.frontend.overview_view import kpi_items, overall_callout

__all__ = ["render_report", "report_markdown"]


def _count(items: Optional[List[Any]]) -> str:
    return str(len(items)) if items is not None else "unavailable"


def report_markdown(report: Dict[str, Any]) -> str:
    """The report as Markdown, built only from fields of the response."""
    architecture = report.get("architecture")
    strategy = (report.get("strategy") or {}).get("primary")
    coverage = report.get("coverage")
    confidence = report.get("confidence")
    lines = [
        f"# Modernization assessment: {report['filename']}",
        "",
        f"- Overall status: **{report['overall_status']}**",
        f"- Paragraphs: {len(report.get('paragraphs') or [])}",
        f"- Business rules: {_count(report.get('business_rules'))}",
        f"- Dependencies: {_count(report.get('dependencies'))}",
        f"- Risks: {_count(report.get('risks'))}",
        f"- Components: {len(architecture['components']) if architecture else 'unavailable'}",
        (
            f"- Analysis coverage: {coverage['overall']:.0%}"
            if coverage
            else "- Analysis coverage: unavailable"
        ),
        (
            f"- Confidence: {confidence['score']:.0%}"
            if confidence
            else "- Confidence: unavailable"
        ),
        "",
        "## Strategy",
        "",
        (
            f"{strategy['strategy']}: {strategy['rationale']}"
            if strategy
            else "Not available."
        ),
        "",
        "## Risks",
        "",
    ]
    risks = report.get("risks") or []
    lines += [
        f"- **{r['title']}** ({r['severity']}): {r['explanation']}" for r in risks
    ] or ["None identified."]
    lines += ["", "## Validation stages", ""]
    stages = report.get("validation_stages") or []
    lines += [
        f"- {s['stage']}: **{s['status']}**. {s.get('summary', '')}".rstrip()
        for s in stages
    ] or ["Not run."]
    lines += ["", "## Unresolved issues", ""]
    issues = report.get("unresolved_issues") or []
    lines += [f"- {i}" for i in issues] or ["None."]
    return "\n".join(lines) + "\n"


def _render_exports(report: Dict[str, Any]) -> None:
    json_col, md_col, _ = st.columns([1.3, 1.5, 6])
    with json_col:
        st.download_button(
            "Export JSON",
            data=json.dumps(report, indent=2),
            file_name=f"{report['filename']}.modernization-report.json",
            mime="application/json",
            icon=":material/data_object:",
            key="export_report_json",
        )
    with md_col:
        st.download_button(
            "Export Markdown",
            data=report_markdown(report),
            file_name=f"{report['filename']}.modernization-report.md",
            mime="text/markdown",
            icon=":material/description:",
            key="export_report_md",
        )


def render_report(report: Optional[Dict[str, Any]], *, error: Optional[str]) -> None:
    """The report page. ``report`` is the ``/modernization/report`` response."""
    if error:
        section_header("Modernization Assessment", eyebrow="Validate")
        st.error(error)
        return
    if report is None:
        section_header("Modernization Assessment", eyebrow="Validate")
        st.info("Run analysis from the sidebar to generate a report.")
        return

    section_header(
        "Modernization Assessment",
        report["filename"],
        eyebrow=f"Validate · {report['overall_status']}",
    )
    _render_exports(report)
    ui.render(overall_callout(report["overall_status"]))

    subsection("Executive summary")
    ui.render(ui.kpi_grid(kpi_items(report)))

    subsection("Program profile")
    paragraphs = report["paragraphs"]
    ui.render(
        ui.key_values(
            [
                ("Source", str(report["source_id"])),
                ("Analysis success", "Yes" if report["analysis_success"] else "No"),
                ("Paragraphs", ", ".join(paragraphs) or "—"),
            ]
        )
    )

    architecture = report.get("architecture")
    subsection("Architecture")
    if architecture:
        st.caption(f"{len(architecture['components'])} component(s) generated.")
    else:
        st.caption(report.get("architecture_reason") or "Not available.")

    subsection("Business rules and dependencies")
    st.caption(
        f"{len(report['business_rules'] or [])} rule(s) extracted, "
        f"{len(report['dependencies'] or [])} dependency reference(s)."
    )

    subsection("Risks")
    risks = report["risks"] or []
    if risks:
        for r in risks:
            ui.render(
                ui.finding(r["title"], r["explanation"], str(r["severity"]), full=True)
            )
    else:
        st.caption(
            "No risks identified." if report["risks"] is not None else "Not available."
        )

    subsection("Modernization strategy")
    strategy = (report.get("strategy") or {}).get("primary")
    if strategy:
        ui.render(
            ui.callout(
                "info", str(strategy["strategy"]), strategy["rationale"], glyph="spark"
            )
        )
    else:
        st.caption("Not available.")

    subsection("Java and validation")
    project = report.get("project")
    compilation = report.get("compilation")
    if not project:
        st.caption(report.get("generation_reason") or "Java generation: not available.")
    elif compilation:
        ui.render(
            ui.status_badge(
                "PASS" if compilation["success"] else "FAIL",
                "Compiled" if compilation["success"] else "Did not compile",
            )
        )
    stage_cells = [
        {"stage": s["stage"], "status": s["status"], "summary": s.get("summary", "")}
        for s in report["validation_stages"]
        if s["stage"] in ("Tests", "Behavioral Equivalence", "Self Repair")
    ]
    if stage_cells:
        ui.render(ui.stage_grid(stage_cells))

    subsection("Unresolved issues")
    unsupported = report.get("unsupported_syntax") or {}
    if unsupported.get("detail"):
        st.caption(f"Unsupported constructs: {unsupported['detail']}")
    if report["unresolved_issues"]:
        for issue in report["unresolved_issues"]:
            st.write(f"- {issue}")
    else:
        ui.render(ui.callout("success", "No unresolved issues", glyph="check"))
