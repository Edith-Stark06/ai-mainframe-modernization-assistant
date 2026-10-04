"""
JCL Analysis: the parsed job stream.

Purpose:
    Show a JCL file's job, its steps (program or procedure, DD statements)
    and every diagnostic the parser raised, exactly as the backend returned
    them.

Responsibilities:
    - :func:`step_rows` / :func:`diagnostic_rows` -- flatten the response for
      tables.
    - :func:`render_jcl` -- compose the page.

Non-responsibilities:
    - Parsing (deterministic, in the backend). Statements the parser does not
      understand are listed as unsupported, never guessed at.

Dependencies:
    - streamlit, app.frontend.{components,design.ui}

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from app.frontend.components import subsection
from app.frontend.design import ui

__all__ = ["diagnostic_rows", "is_jcl", "render_jcl", "step_rows"]


def is_jcl(filename: Optional[str]) -> bool:
    """Whether *filename* looks like a JCL member."""
    return bool(filename) and str(filename).lower().rsplit(".", 1)[-1] in {
        "jcl",
        "proc",
        "prc",
    }


def step_rows(program: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per step: name, program or procedure, DD count, line."""
    return [
        {
            "step": s["name"],
            "runs": s.get("program")
            or (f"PROC {s['procedure']}" if s.get("procedure") else "—"),
            "DD statements": len(s.get("dd_statements") or []),
            "line": s["line"],
        }
        for s in program.get("steps") or []
    ]


def diagnostic_rows(diagnostics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per diagnostic, in the order the parser recorded them."""
    return [
        {
            "severity": d["severity"],
            "code": d["code"],
            "line": d["line"],
            "message": d["message"],
        }
        for d in diagnostics
    ]


def render_jcl(
    result: Optional[Dict[str, Any]], *, filename: Optional[str], error: Optional[str]
) -> None:
    """The JCL page. ``result`` is the ``/jcl/analyze`` response."""
    ui.render(ui.page_header("JCL analysis", filename, eyebrow="Analyze"))
    if error:
        st.error(error)
        return
    if not is_jcl(filename):
        ui.render(
            ui.empty_state(
                "file",
                "This is not a JCL file",
                "Select a .jcl file in the sidebar. COBOL programs are analysed in the other views.",
            )
        )
        return
    if result is None:
        st.info("Parsing JCL...")
        return
    if result.get("error"):
        st.error(result["error"])
        return

    program = result.get("program") or {}
    job = program.get("job")
    steps = step_rows(program)
    unsupported = program.get("unsupported") or []
    diagnostics = result.get("diagnostics") or []
    ui.render(
        ui.kpi_grid(
            [
                {"label": "Job", "value": job["name"] if job else "—"},
                {"label": "Steps", "value": str(len(steps))},
                {"label": "Unsupported statements", "value": str(len(unsupported))},
                {"label": "Diagnostics", "value": str(len(diagnostics))},
            ]
        )
    )
    if unsupported:
        ui.render(
            ui.callout(
                "warning",
                f"{len(unsupported)} statement(s) not understood",
                "They are listed below and were not interpreted. Review them by hand.",
            )
        )

    subsection("Steps", "In execution order.")
    if steps:
        st.dataframe(steps, hide_index=True, width="stretch")
    else:
        ui.render(
            ui.empty_state("list", "No steps", "The job stream has no EXEC statements.")
        )
    if unsupported:
        subsection("Unsupported statements")
        st.dataframe(
            [
                {
                    "operation": u["operation"],
                    "name": u.get("name") or "—",
                    "line": u["line"],
                }
                for u in unsupported
            ],
            hide_index=True,
            width="stretch",
        )
    if diagnostics:
        subsection("Diagnostics", "Everything the parser raised, in order.")
        st.dataframe(diagnostic_rows(diagnostics), hide_index=True, width="stretch")
