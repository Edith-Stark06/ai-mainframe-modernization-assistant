"""
Overview: the modernization command center.

Purpose:
    The first screen of a workspace file. It answers, in order: *Is this
    program ready to modernize? What did the analysis find? Where is the
    risk? What does the control flow look like?* -- every figure taken from
    the backend's report, none computed or guessed here.

Responsibilities:
    - :func:`overall_callout` -- the honest headline for the overall status.
    - :func:`pipeline_steps_for` -- the four-step pipeline from real fields.
    - :func:`kpi_items` -- the figures row.
    - :func:`render_overview` -- compose the page.

Non-responsibilities:
    - Fetching (see :mod:`app.frontend.state`).

Design note:
    "Ready" is only ever claimed when the backend's ``overall_status`` is
    ``PASS``. ``INCONCLUSIVE`` and ``NOT_AVAILABLE`` are shown as *not
    verified*, never as success.

Dependencies:
    - streamlit, app.frontend.{components,state,design.ui}

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from app.frontend import state
from app.frontend.client import BackendClient
from app.frontend.components import render_force_graph, subsection
from app.frontend.design import ui

__all__ = [
    "kpi_items",
    "overall_callout",
    "pipeline_steps_for",
    "render_overview",
    "severity_rows",
]

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_SEVERITY_TONE = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "neutral",
}

#: overall status -> (tone, headline, sentence)
_OVERALL = {
    "PASS": (
        "success",
        "Verified: ready for modernization",
        "Every validation stage that could run passed.",
    ),
    "FAIL": (
        "error",
        "Not ready: a stage failed",
        "A verified failure was found. Open the Validation Center for the stage and the reason.",
    ),
    "INCONCLUSIVE": (
        "warning",
        "Not yet verified",
        "At least one stage could not be checked, so this program is not cleared. "
        "Open the Validation Center to see which.",
    ),
    "NOT_AVAILABLE": (
        "neutral",
        "Validation not available",
        "Nothing has been validated for this file yet.",
    ),
}


def overall_callout(overall: Optional[str]) -> str:
    """The headline banner for the backend's ``overall_status`` (or nothing)."""
    if not overall:
        return ""
    tone, headline, sentence = _OVERALL.get(
        overall.upper(), ("neutral", f"Status: {overall}", "")
    )
    return ui.callout(tone, headline, sentence or None)


def pipeline_steps_for(report: Dict[str, Any]) -> List[Dict[str, str]]:
    """Derive the four pipeline steps from already-fetched report fields.

    Each stage is evaluated from its own signal, never cascaded off an earlier
    one: a partial parse does not by itself mean no rules were extracted or no
    Java was generated, and the stepper must say so honestly.
    """
    paragraphs = report.get("paragraphs") or []
    rules = report.get("business_rules") or []
    project = report.get("project")
    compilation = report.get("compilation")
    java_files = sum(
        1 for p in ((project or {}).get("files") or {}) if p.endswith(".java")
    )
    overall = report.get("overall_status")

    if project and compilation and compilation.get("success"):
        transform = "done"
    elif project:
        transform = "partial"
    else:
        transform = "pending"
    validate = {"PASS": "done", "FAIL": "fail", "INCONCLUSIVE": "partial"}.get(
        str(overall), "pending"
    )

    stages = report.get("validation_stages") or []
    passed = sum(1 for s in stages if s.get("status") == "PASS")
    return [
        {
            "name": "Analyze",
            "state": "done" if report.get("analysis_success") else "fail",
            "metric": f"{len(paragraphs)} paragraphs",
            "detail": (
                "Parsed deterministically"
                if report.get("analysis_success")
                else "Parse incomplete; unsupported syntax present"
            ),
        },
        {
            "name": "Understand",
            "state": "done" if rules else "pending",
            "metric": f"{len(rules)} rules",
            "detail": f"{len(report.get('dependencies') or [])} dependencies mapped",
        },
        {
            "name": "Transform",
            "state": transform,
            "metric": f"{java_files} Java files",
            "detail": (
                "Compiled"
                if transform == "done"
                else ("Generated, not compiled" if project else "Not generated")
            ),
        },
        {
            "name": "Validate",
            "state": validate,
            "metric": (
                f"{passed} of {len(stages)} stages pass" if stages else "No stages"
            ),
            "detail": (
                str(overall).replace("_", " ").capitalize() if overall else "Not run"
            ),
        },
    ]


def kpi_items(report: Dict[str, Any]) -> List[Dict[str, object]]:
    """The figures row. A figure the backend did not produce shows as an
    em dash, never a zero."""
    architecture = report.get("architecture") or {}
    project = report.get("project") or {}
    java_files = sum(1 for p in (project.get("files") or {}) if p.endswith(".java"))
    coverage = report.get("coverage")
    confidence = report.get("confidence")
    items: List[Dict[str, object]] = [
        {
            "label": "Business rules",
            "value": str(len(report.get("business_rules") or [])),
        },
        {"label": "Dependencies", "value": str(len(report.get("dependencies") or []))},
        {"label": "Risks", "value": str(len(report.get("risks") or []))},
        {
            "label": "Components",
            "value": (
                str(len(architecture.get("components") or [])) if architecture else "—"
            ),
        },
        {"label": "Java files", "value": str(java_files) if project else "—"},
    ]
    if coverage:
        items.append(
            {
                "label": "Analysis coverage",
                "value": f"{coverage['overall']:.0%}",
                "ratio": coverage["overall"],
            }
        )
    else:
        items.append({"label": "Analysis coverage", "value": "—"})
    if confidence:
        items.append(
            {
                "label": "Confidence",
                "value": f"{confidence['score']:.0%}",
                "ratio": confidence["score"],
            }
        )
    return items


def severity_rows(risks: List[Dict[str, Any]]) -> List[tuple[str, int]]:
    """``(severity, count)`` rows, most severe first, for the risk chart."""
    counts: Dict[str, int] = {}
    for risk in risks:
        key = str(risk.get("severity", "")).upper() or "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1
    return [
        (name.capitalize(), counts[name])
        for name in sorted(counts, key=lambda s: _SEVERITY_ORDER.get(s, 9))
    ]


def _render_findings(report: Dict[str, Any]) -> None:
    subsection("Key findings", "Highest severity first.")
    risks = sorted(
        report.get("risks") or [],
        key=lambda r: _SEVERITY_ORDER.get(str(r.get("severity", "")).upper(), 9),
    )
    if not risks:
        ui.render(
            ui.empty_state(
                "shield",
                "No risks identified",
                "The analysis found nothing to flag for this file.",
            )
        )
    for risk in risks[:4]:
        ui.render(
            ui.finding(
                str(risk.get("title") or risk.get("risk_id") or "Risk"),
                str(risk.get("explanation") or ""),
                str(risk.get("severity", "")),
            )
        )
    if len(risks) > 4:
        st.caption(f"{len(risks) - 4} more in the Report.")
    chart = ui.bar_chart(
        severity_rows(report.get("risks") or []),
        title="Risks by severity",
        tones={name.capitalize(): tone for name, tone in _SEVERITY_TONE.items()},
    )
    if chart:
        ui.render(chart)

    strategy = (report.get("strategy") or {}).get("primary")
    if strategy:
        ui.render(
            ui.callout(
                "info",
                f"Recommended strategy: {strategy['strategy']}",
                strategy.get("rationale"),
                glyph="spark",
            )
        )


def _render_topology() -> None:
    subsection("Control flow", "Paragraph-level flow extracted by the parser.")
    if st.session_state.modernization_error:
        st.error(st.session_state.modernization_error)
        return
    result = st.session_state.modernization_result
    if (
        result is None
        or st.session_state.modernization_result_filename != st.session_state.filename
    ):
        ui.render(
            ui.empty_state(
                "search",
                "Not analysed yet",
                "Use Refresh analysis to compute the control flow.",
            )
        )
        return
    flow = result.get("flow") or {}
    render_force_graph(
        [(n["id"], n.get("name", n["id"])) for n in flow.get("nodes", [])],
        [
            (e["source_id"], e["target_id"], e.get("edge_type", ""))
            for e in flow.get("edges", [])
        ],
        empty_message="No control-flow topology could be extracted from this file.",
    )


def render_overview(client: BackendClient, workspace_id: str, filename: str) -> None:
    """Load what the Overview needs (once per file) and draw it."""
    state.ensure_report(client, workspace_id, filename)
    state.ensure_pipeline(client, workspace_id, filename)

    report = state.current_report()
    if st.session_state.report_error:
        ui.render(ui.page_header(filename, eyebrow="Overview"))
        st.error(st.session_state.report_error)
        return
    if report is None:
        ui.render(ui.page_header(filename, eyebrow="Overview"))
        st.info("Loading modernization report...")
        return

    paragraphs = report.get("paragraphs") or []
    head, action = st.columns([6, 1.3], vertical_alignment="bottom")
    with head:
        ui.render(
            ui.page_header(
                filename,
                (
                    f"{len(paragraphs)} paragraph{'s' if len(paragraphs) != 1 else ''} analysed."
                    if paragraphs
                    else "No paragraphs were extracted from this file."
                ),
                eyebrow="Overview",
            )
        )
    with action:
        if st.button(
            "Refresh analysis",
            key="analyze_button",
            icon=":material/refresh:",
            disabled=st.session_state.loading,
            width="stretch",
        ):
            st.session_state.modernization_result_filename = None
            st.session_state.report_result_filename = None
            st.rerun()

    ui.render(overall_callout(report.get("overall_status")))
    ui.render(ui.kpi_grid(kpi_items(report)))

    subsection("Modernization pipeline", "Each step is judged on its own evidence.")
    ui.render(ui.stepper(pipeline_steps_for(report)))

    left, right = st.columns([1, 1], gap="large")
    with left:
        _render_findings(report)
    with right:
        _render_topology()

    stages = report.get("validation_stages") or []
    if stages:
        subsection("Validation stages", "Open the Validation Center for detail.")
        ui.render(
            ui.stage_grid(
                [
                    {
                        "stage": s["stage"],
                        "status": s["status"],
                        "summary": s.get("summary", ""),
                    }
                    for s in stages
                ]
            )
        )
