"""
Portfolio: every file in the workspace at a glance.

Purpose:
    The workspace-level page. It lists what was uploaded -- counts by file
    type, total size, and a searchable file table -- and lets the user open
    any file in the analysis views.

Responsibilities:
    - :func:`type_rows` / :func:`format_bytes` -- pure presentation helpers.
    - :func:`render_portfolio` -- compose the page.

Non-responsibilities:
    - Per-file analysis (that happens in the other views, on demand; the
      Portfolio never analyses every file, so it stays fast on large
      workspaces).

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

from app.frontend.components import selectable_table, subsection
from app.frontend.design import ui

__all__ = ["format_bytes", "render_portfolio", "type_rows"]


def format_bytes(size: int) -> str:
    """A human-readable size: ``512 B``, ``3.4 KB``, ``1.2 MB``."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"  # pragma: no cover - loop always returns


def type_rows(files: List[Dict[str, Any]]) -> List[tuple[str, int]]:
    """``(file type, count)`` rows, most common first, computed from the
    inventory itself so they always agree with the table below."""
    counts: Dict[str, int] = {}
    for f in files:
        key = str(f.get("file_type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def render_portfolio(
    files: List[Dict[str, Any]], summary: Optional[Dict[str, Any]], *, workspace_id: str
) -> None:
    """The workspace overview: figures, composition and the file table."""
    ui.render(
        ui.page_header(
            f"Workspace {workspace_id[:8]}",
            "Every uploaded file. Pick one in the sidebar to analyse it.",
            eyebrow="Portfolio",
        )
    )
    if not files:
        ui.render(
            ui.empty_state(
                "folder",
                "This workspace has no files",
                "Upload COBOL, copybook or JCL files from Switch workspace in the sidebar.",
            )
        )
        return

    total_size = (
        int(summary["total_size_bytes"])
        if summary and "total_size_bytes" in summary
        else sum(int(f.get("size_bytes") or 0) for f in files)
    )
    kinds = type_rows(files)
    ui.render(
        ui.kpi_grid(
            [
                {"label": "Files", "value": str(len(files))},
                {"label": "Total size", "value": format_bytes(total_size)},
                {"label": "File types", "value": str(len(kinds))},
            ]
        )
    )

    left, right = st.columns([2, 3], gap="large")
    with left:
        subsection("Composition", "Files by type.")
        ui.render(
            ui.bar_chart(
                kinds,
                title="Files by type",
                caption=f"{len(files)} file{'s' if len(files) != 1 else ''} in total.",
            )
        )
    with right:
        subsection("Files", "Select a row to make it the current file.")
        rows = [
            {
                "filename": f["filename"],
                "type": f.get("file_type", ""),
                "size": format_bytes(int(f.get("size_bytes") or 0)),
            }
            for f in files
        ]
        picked = selectable_table(
            rows, ["filename", "type", "size"], key="portfolio_table"
        )
        if picked and picked["filename"] != st.session_state.filename:
            st.session_state.filename = picked["filename"]
            st.session_state.messages = []
            st.session_state.active_view = "Overview"
            st.rerun()
