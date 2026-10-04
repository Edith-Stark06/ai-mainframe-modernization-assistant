"""
Session state and lazy loading.

Purpose:
    Everything the workspace UI remembers between Streamlit reruns, and the
    loaders that fetch each view's data the first time that view is opened
    (never on startup -- large analysis artifacts are not reloaded needlessly)
    and cache it per file.

Responsibilities:
    - :func:`init_session_state` -- defaults for every key.
    - :func:`reset_workspace` -- switch workspace and clear everything derived.
    - :func:`load_inventory` / :func:`load_summary` -- the workspace's files.
    - ``ensure_*`` -- fetch-once-per-file loaders for each view.
    - :func:`current_report` -- the cached report for the selected file, if any.

Non-responsibilities:
    - Rendering (see the ``*_view`` modules and :mod:`app.frontend.shell`).

Design note:
    Each cached result is stored as ``<name>_result`` / ``<name>_result_filename``
    / ``<name>_error``. A loader is a no-op while ``<name>_result_filename``
    equals the selected file, and on failure records the safe message from
    :class:`~app.frontend.client.BackendAPIError` -- never a stack trace.

Dependencies:
    - streamlit, app.frontend.client

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import streamlit as st

from app.frontend.client import BackendAPIError, BackendClient

__all__ = [
    "CACHED_RESULTS",
    "current_report",
    "ensure_analysis",
    "ensure_architecture",
    "ensure_cobol_source",
    "ensure_intelligence",
    "ensure_java_generation",
    "ensure_java_workspace",
    "ensure_jcl",
    "ensure_pipeline",
    "ensure_report",
    "ensure_validation",
    "init_session_state",
    "load_inventory",
    "load_summary",
    "reset_workspace",
]

#: every per-file cached result (the name of its ``<name>_result`` key).
CACHED_RESULTS = (
    "modernization",
    "analysis",
    "intelligence",
    "architecture",
    "java_generation",
    "validation",
    "report",
    "java_workspace",
    "jcl",
)


def init_session_state() -> None:
    """Give every session-state key its default, once."""
    defaults: Dict[str, Any] = {
        # -- navigation stage ------------------------------------------
        "stage": "landing",  # "landing" | "entry" | "workspace"
        "intro_seen": False,
        "engineer_name": None,
        "active_view": "Overview",
        # -- workspace ---------------------------------------------------
        "workspace_id": None,
        "known_workspace_ids": [],
        "inventory_files": [],
        "inventory_error": None,
        "summary": None,
        "filename": None,
        "loading": False,
        "messages": [],
        # -- non-JSON-shaped caches --------------------------------------
        "cobol_source": None,
        "cobol_source_filename": None,
    }
    for name in CACHED_RESULTS:
        defaults[f"{name}_result"] = None
        defaults[f"{name}_result_filename"] = None
        defaults[f"{name}_error"] = None
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_workspace(workspace_id: str) -> None:
    """Switch to a (new or existing) workspace, clearing all downstream state."""
    st.session_state.workspace_id = workspace_id
    if workspace_id not in st.session_state.known_workspace_ids:
        st.session_state.known_workspace_ids.append(workspace_id)
    st.session_state.inventory_files = []
    st.session_state.inventory_error = None
    st.session_state.summary = None
    st.session_state.filename = None
    st.session_state.messages = []
    st.session_state.cobol_source = None
    st.session_state.cobol_source_filename = None
    for name in CACHED_RESULTS:
        st.session_state[f"{name}_result"] = None
        st.session_state[f"{name}_result_filename"] = None
        st.session_state[f"{name}_error"] = None


def load_inventory(client: BackendClient, workspace_id: str) -> None:
    """Fetch the workspace's file list into session state."""
    try:
        inventory = client.get_inventory(workspace_id)
        st.session_state.inventory_files = inventory.get("files", [])
        st.session_state.inventory_error = None
    except BackendAPIError as e:
        st.session_state.inventory_files = []
        st.session_state.inventory_error = e.message


def load_summary(client: BackendClient, workspace_id: str) -> None:
    """Fetch the workspace totals once; a failure leaves ``summary`` as
    ``None`` (the Portfolio computes what it needs from the inventory)."""
    if st.session_state.summary is not None:
        return
    try:
        st.session_state.summary = client.get_summary(workspace_id)
    except BackendAPIError:
        st.session_state.summary = None


def _ensure(
    name: str,
    filename: str,
    loader: Callable[[], Any],
    spinner: str,
) -> None:
    """Fetch ``name`` for ``filename`` once and cache it (or its safe error)."""
    if st.session_state[f"{name}_result_filename"] == filename:
        return
    try:
        with st.spinner(spinner):
            st.session_state[f"{name}_result"] = loader()
        st.session_state[f"{name}_error"] = None
    except BackendAPIError as e:
        st.session_state[f"{name}_result"] = None
        st.session_state[f"{name}_error"] = e.message
    st.session_state[f"{name}_result_filename"] = filename


def ensure_pipeline(client: BackendClient, workspace_id: str, filename: str) -> None:
    """The control-flow / scoring pipeline result (Overview's topology)."""
    _ensure(
        "modernization",
        filename,
        lambda: client.analyze_modernization(workspace_id, filename),
        "Analyzing control flow...",
    )


def ensure_analysis(client: BackendClient, workspace_id: str, filename: str) -> None:
    """The ``/analyze`` response (dependencies and graphs)."""
    _ensure(
        "analysis",
        filename,
        lambda: client.get_analysis(workspace_id, filename),
        "Loading dependency analysis...",
    )


def ensure_intelligence(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    """Business rules, risks and strategy."""
    _ensure(
        "intelligence",
        filename,
        lambda: client.get_modernization_intelligence(workspace_id, filename),
        "Extracting business rules, risks, and strategy...",
    )


def ensure_architecture(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    """The derived target architecture."""
    _ensure(
        "architecture",
        filename,
        lambda: client.get_architecture(workspace_id, filename),
        "Deriving architecture...",
    )


def ensure_java_generation(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    """The generated Java and its compilation result."""
    _ensure(
        "java_generation",
        filename,
        lambda: client.get_java_generation(workspace_id, filename),
        "Generating and compiling Java...",
    )


def ensure_validation(client: BackendClient, workspace_id: str, filename: str) -> None:
    """Per-stage validation status."""
    _ensure(
        "validation",
        filename,
        lambda: client.get_validation(workspace_id, filename),
        "Validating...",
    )


def ensure_report(client: BackendClient, workspace_id: str, filename: str) -> None:
    """The aggregate modernization report."""
    _ensure(
        "report",
        filename,
        lambda: client.get_modernization_report(workspace_id, filename),
        "Building modernization report...",
    )


def ensure_java_workspace(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    """The Java workspace (candidates, repair history, audit trail)."""
    _ensure(
        "java_workspace",
        filename,
        lambda: client.get_java_workspace(workspace_id, filename),
        "Loading Java workspace...",
    )


def ensure_jcl(client: BackendClient, workspace_id: str, filename: str) -> None:
    """The parsed JCL job for a ``.jcl`` file."""
    _ensure(
        "jcl",
        filename,
        lambda: client.analyze_jcl(workspace_id, filename),
        "Parsing JCL...",
    )


def ensure_cobol_source(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    """The raw source text (the COBOL side of the split view)."""
    if st.session_state.cobol_source_filename == filename:
        return
    try:
        st.session_state.cobol_source = client.get_file_content(
            workspace_id, filename
        ).get("content")
    except BackendAPIError:
        st.session_state.cobol_source = None
    st.session_state.cobol_source_filename = filename


def current_report() -> Optional[Dict[str, Any]]:
    """The cached report for the selected file, or ``None`` if there is none
    (not loaded yet, failed, or loaded for a different file)."""
    report = st.session_state.report_result
    if (
        report is not None
        and st.session_state.report_result_filename == st.session_state.filename
    ):
        return report
    return None
