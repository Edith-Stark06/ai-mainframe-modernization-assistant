"""
Application shell.

Purpose:
    The persistent frame around every workspace view: the left navigation, the
    workspace and file pickers, the top bar, and the first-run welcome screen.

Responsibilities:
    - :data:`NAV_GROUPS` / :data:`NAV_KEYS` / :data:`NAV_ICONS` -- the information
      architecture (which views exist, how they are grouped, their widget keys).
    - :func:`render_sidebar` -- brand, workspace card, file picker, navigation,
      API status, session controls.
    - :func:`render_topbar` -- breadcrumbs, status, workspace search, help.
    - :func:`render_welcome` -- the no-workspace screen (upload or open one).
    - :func:`render_workspace_controls` -- upload / open-existing widgets.

Non-responsibilities:
    - Page content (the ``*_view`` modules) and data loading (:mod:`state`).

Design note:
    The workspace widgets live in exactly one place per run -- the welcome screen
    when no workspace is open, a sidebar popover afterwards -- because Streamlit
    rejects two widgets with the same key.

Dependencies:
    - streamlit, app.frontend.{client,state,design.ui,theme}

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from app.frontend import state
from app.frontend.client import BackendAPIError, BackendClient
from app.frontend.design import ui

__all__ = [
    "NAV_GROUPS",
    "NAV_ICONS",
    "NAV_KEYS",
    "OUTER_VIEWS",
    "render_sidebar",
    "render_topbar",
    "render_welcome",
    "render_workspace_controls",
]

# -- information architecture ------------------------------------------------

NAV_GROUPS: List[Tuple[str, List[str]]] = [
    ("Workspace", ["Overview", "Portfolio"]),
    ("Analyze", ["Business Rules", "Dependencies", "Architecture", "JCL Analysis"]),
    ("Transform", ["COBOL ↔ Java", "Java Workspace"]),
    ("Validate", ["Validation Center", "Report"]),
    ("Assistant", ["Modernization Chat"]),
]
OUTER_VIEWS: List[str] = [view for _, views in NAV_GROUPS for view in views]

#: widget keys (tests and callers address the nav buttons by these)
NAV_KEYS: Dict[str, str] = {
    "Overview": "nav_overview",
    "Portfolio": "nav_portfolio",
    "Business Rules": "nav_business_rules",
    "Dependencies": "nav_dependencies",
    "Architecture": "nav_architecture",
    "JCL Analysis": "nav_jcl",
    "COBOL ↔ Java": "nav_cobol_java",
    "Java Workspace": "nav_java_workspace",
    "Validation Center": "nav_validation_center",
    "Report": "nav_report",
    "Modernization Chat": "nav_chat",
}
NAV_ICONS: Dict[str, str] = {
    "Overview": ":material/dashboard:",
    "Portfolio": ":material/folder_open:",
    "Business Rules": ":material/rule:",
    "Dependencies": ":material/hub:",
    "Architecture": ":material/account_tree:",
    "JCL Analysis": ":material/playlist_play:",
    "COBOL ↔ Java": ":material/sync_alt:",
    "Java Workspace": ":material/code:",
    "Validation Center": ":material/verified:",
    "Report": ":material/description:",
    "Modernization Chat": ":material/auto_awesome:",
}

#: pages that make sense with a workspace but no particular file selected
_WORKSPACE_LEVEL_VIEWS = {"Portfolio"}


# -- workspace controls -------------------------------------------------------


def render_workspace_controls(client: BackendClient) -> None:
    """Upload new source files, or open an existing workspace by id.

    Used on the welcome screen and, once a workspace is open, inside the
    sidebar's *Switch workspace* popover. Keys are stable (tests rely on them).
    """
    st.markdown("**Upload source files**")
    uploaded = st.file_uploader(
        "COBOL, copybook, JCL, text or zip files",
        accept_multiple_files=True,
        key="uploader",
        help="Accepts .cbl, .cob, .cpy, .jcl, .txt and .zip. Maximum 20 MB per upload.",
    )
    if st.button(
        "Upload and create workspace",
        disabled=not uploaded,
        key="upload_button",
        type="primary",
    ):
        files = [(f.name, f.getvalue()) for f in uploaded]
        try:
            result = client.upload_files(files)
            workspace_id = result["workspace_id"]
            state.reset_workspace(workspace_id)
            state.load_inventory(client, workspace_id)
        except BackendAPIError as e:
            st.error(e.message)
        else:
            st.rerun()

    st.markdown("**Open an existing workspace**")
    options = ["(enter manually)"] + st.session_state.known_workspace_ids
    choice = st.selectbox(
        "Recent workspaces", options=options, index=0, key="known_ws_select"
    )
    manual_id = st.text_input(
        "Workspace ID",
        value="",
        key="manual_ws_input",
        placeholder="e.g. 731a56de-e52f-46a4-a52e-de7906a47897",
    )
    target_id = manual_id.strip() if choice == "(enter manually)" else choice
    if st.button(
        "Open workspace",
        disabled=not target_id.strip(),
        key="load_workspace_button",
    ):
        state.reset_workspace(target_id.strip())
        state.load_inventory(client, target_id.strip())
        st.rerun()


def render_welcome(client: BackendClient) -> None:
    """The first-run screen: explains the three steps and offers both ways in."""
    greeting = st.session_state.engineer_name or "there"
    ui.render(
        ui.page_header(
            f"Welcome, {greeting}",
            "Understand, transform and validate your COBOL programs. "
            "Every result comes from deterministic analysis of your own source.",
            eyebrow="Get started",
        )
    )
    ui.render(
        ui.welcome_steps(
            [
                (
                    "Bring your source",
                    "Upload COBOL, copybooks or JCL, or reopen a workspace you already created.",
                ),
                (
                    "Review the analysis",
                    "Business rules, dependencies, risks and a target architecture, extracted without an LLM.",
                ),
                (
                    "Check the Java",
                    "Generated Java is compiled and validated; anything unverified is labelled as such.",
                ),
            ]
        )
    )
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            render_workspace_controls(client)
    with right:
        ui.render(
            ui.empty_state(
                "folder",
                "No workspace yet",
                "Upload a file to create one. Your files stay in this deployment's workspace folder.",
            )
        )


# -- sidebar ------------------------------------------------------------------


@st.cache_data(ttl=15, show_spinner=False)
def _api_status(_client: BackendClient) -> str:
    """``"online"`` / ``"offline"`` for the API, cached briefly so the check
    does not run on every rerun."""
    try:
        return (
            "online" if _client.get_health().get("status") == "healthy" else "offline"
        )
    except BackendAPIError:
        return "offline"


def _file_detail(files: List[Dict[str, Any]]) -> str:
    n = len(files)
    return f"{n} file{'s' if n != 1 else ''}" if n else "Empty"


def _render_file_picker() -> None:
    files = st.session_state.inventory_files
    if st.session_state.inventory_error:
        st.error(st.session_state.inventory_error)
        return
    if not files:
        st.caption("No files found in this workspace.")
        return
    filenames = [f["filename"] for f in files]
    current = st.session_state.filename
    index = filenames.index(current) if current in filenames else 0
    selected = st.selectbox(
        "Source file", options=filenames, index=index, key="file_select"
    )
    if selected != current:
        # A different file must not inherit the previous file's conversation.
        st.session_state.messages = []
    st.session_state.filename = selected


def render_sidebar(client: BackendClient) -> None:
    """The left rail. Must be called inside ``with st.sidebar:``."""
    if st.button(
        "Back to landing", key="back_to_landing", icon=":material/arrow_back:"
    ):
        st.session_state.stage = "landing"
        st.rerun()

    ui.render(ui.brand())

    workspace_id = st.session_state.workspace_id
    ui.render(
        ui.workspace_card(
            workspace_id,
            _file_detail(st.session_state.inventory_files) if workspace_id else None,
        )
    )

    if workspace_id:
        with st.popover(
            "Switch workspace", icon=":material/swap_horiz:", width="stretch"
        ):
            render_workspace_controls(client)
        _render_file_picker()

    active = st.session_state.active_view
    for index, (group_label, views) in enumerate(NAV_GROUPS):
        first = " ds-nav-group--first" if index == 0 else ""
        ui.render(f'<div class="ds-nav-group{first}">{ui.esc(group_label)}</div>')
        for view in views:
            if st.button(
                view,
                key=NAV_KEYS[view],
                icon=NAV_ICONS[view],
                type="primary" if view == active else "secondary",
                width="stretch",
            ):
                st.session_state.active_view = view
                st.rerun()

    with st.container(key="side_footer"):
        ui.render('<div class="ds-nav-group">Session</div>')
        status = _api_status(client)
        ui.render(
            '<div class="ds-side-status">'
            + ui.badge(
                f"API {status}",
                "success" if status == "online" else "error",
                "check" if status == "online" else "x",
            )
            + "</div>"
        )
        st.caption(f"Signed in locally as {st.session_state.engineer_name or 'Guest'}")
        if st.button("Log out", key="logout_button", icon=":material/logout:"):
            st.session_state.clear()
            st.session_state.stage = "entry"
            st.rerun()


# -- top bar ------------------------------------------------------------------


def _render_search(client: BackendClient) -> None:
    """Plain-text search across every file of the workspace
    (``GET /workspaces/{id}/search``): substring matching, not semantic."""
    workspace_id = st.session_state.workspace_id
    if not workspace_id:
        return
    query = st.text_input(
        "Search workspace files",
        key="search_query_input",
        placeholder="Search workspace files",
        label_visibility="collapsed",
    )
    if not query or not query.strip():
        return
    try:
        result = client.search_workspace(workspace_id, query)
    except BackendAPIError as exc:
        st.caption(f"Search failed: {exc}")
        return
    matches = result.get("matches") or []
    with st.popover(
        f"{len(matches)} result{'s' if len(matches) != 1 else ''}"
        + (" (more exist)" if result.get("truncated") else ""),
        width="stretch",
    ):
        if not matches:
            st.caption(f"No matches for {query!r}.")
        for m in matches[:20]:
            st.markdown(f"**{m['filename']}** · line {m['line']}")
            st.code(m["snippet"], language="cobol")


def render_topbar(
    client: BackendClient, view: str, overall_status: Optional[str]
) -> None:
    """Breadcrumbs and status on the left; search and help on the right."""
    workspace_id = st.session_state.workspace_id
    crumbs = [f"Workspace {workspace_id[:8]}" if workspace_id else "No workspace", view]
    status_html = ui.status_badge(overall_status) if overall_status else ""
    with st.container(key="topbar"):
        left, search_col, help_col = st.columns(
            [5, 3, 1.1], vertical_alignment="center"
        )
        with left:
            ui.render(
                '<div style="display:flex;align-items:center;gap:.8rem;flex-wrap:wrap">'
                + ui.breadcrumbs(
                    crumbs, file=st.session_state.filename if workspace_id else None
                )
                + status_html
                + "</div>"
            )
        with search_col:
            _render_search(client)
        with help_col:
            with st.popover("Help", icon=":material/help:", width="stretch"):
                st.markdown("**Mainframe Modernization Assistant**")
                st.caption(
                    "Understand, transform and validate COBOL programs. Every result "
                    "comes from deterministic analysis of your source; nothing is fabricated."
                )
                st.caption(
                    "Pick a file in the sidebar, then work through Analyze, Transform and "
                    "Validate. The assistant answers questions about the selected file."
                )
