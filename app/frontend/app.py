"""Streamlit UI for the AI-Powered Mainframe Modernization Assistant."""

import sys
from pathlib import Path

# `streamlit run app/frontend/app.py` inserts this script's own directory
# (app/frontend) at the front of sys.path (streamlit.web.bootstrap._fix_sys_path).
# Since this script is itself named app.py, Python then resolves the
# top-level `app` package to this very file instead of the real app/
# package at the project root, and `from app.frontend.client import ...`
# fails with "No module named 'app.frontend'; 'app' is not a package".
# Force the project root to the front of sys.path -- removing any existing
# entry first, in case it is already present but not first -- so it always
# wins the lookup regardless of what streamlit's bootstrap already did.
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT in sys.path:
    sys.path.remove(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

# Defense in depth: if `app` was already resolved (and cached in
# sys.modules) to something other than the real app/ package before the
# sys.path fix above ran -- e.g. this very script, mistaken for it -- the
# import below would keep reusing that cached, wrong module instead of
# re-resolving it via the now-corrected sys.path. Drop it so it re-resolves
# fresh. A correct `app` package always has __path__; a plain module (this
# script) does not.
if not hasattr(sys.modules.get("app"), "__path__"):
    sys.modules.pop("app", None)
    sys.modules.pop("app.frontend", None)

import streamlit as st  # noqa: E402

from app.frontend import state  # noqa: E402
from app.frontend.architecture_view import render_architecture  # noqa: E402
from app.frontend.chat_view import render_chat  # noqa: E402
from app.frontend.client import BackendClient  # noqa: E402
from app.frontend.dependencies_view import render_dependencies  # noqa: E402
from app.frontend.design import ui  # noqa: E402
from app.frontend.design.logo import ASSET_DIR  # noqa: E402
from app.frontend.entry import render_entry  # noqa: E402
from app.frontend.java_view import render_java_view  # noqa: E402
from app.frontend.java_workspace import render_java_workspace  # noqa: E402
from app.frontend.jcl_view import is_jcl, render_jcl  # noqa: E402
from app.frontend.landing import render_landing  # noqa: E402
from app.frontend.overview_view import render_overview  # noqa: E402
from app.frontend.portfolio_view import render_portfolio  # noqa: E402
from app.frontend.report_view import render_report  # noqa: E402
from app.frontend.rules_view import render_business_rules  # noqa: E402
from app.frontend.shell import (  # noqa: E402
    OUTER_VIEWS,
    render_sidebar,
    render_topbar,
    render_welcome,
)
from app.frontend.theme import inject_base_theme  # noqa: E402
from app.frontend.validation_view import render_validation  # noqa: E402

#: views that work with a workspace but no particular file selected
_WORKSPACE_LEVEL = {"Portfolio"}


@st.cache_resource
def get_client() -> BackendClient:
    """The one backend client shared by every session."""
    return BackendClient()


def _report_for_file() -> dict | None:
    """The cached report, but only if it belongs to the selected file."""
    return state.current_report()


def _render_workspace_body(client: BackendClient, view: str) -> None:
    """Load what *view* needs for the selected file and draw it."""
    workspace_id = st.session_state.workspace_id
    filename = st.session_state.filename
    ss = st.session_state

    if view == "Overview":
        render_overview(client, workspace_id, filename)
    elif view == "Business Rules":
        state.ensure_intelligence(client, workspace_id, filename)
        render_business_rules(ss.intelligence_result, error=ss.intelligence_error)
    elif view == "Dependencies":
        state.ensure_analysis(client, workspace_id, filename)
        render_dependencies(
            ss.analysis_result,
            error=ss.analysis_error,
            dot_loader=lambda kind: client.export_graph_dot(
                workspace_id, filename, kind
            ),
            filename=filename,
        )
    elif view == "Architecture":
        state.ensure_architecture(client, workspace_id, filename)
        render_architecture(ss.architecture_result, error=ss.architecture_error)
    elif view == "JCL Analysis":
        if is_jcl(filename):
            state.ensure_jcl(client, workspace_id, filename)
        render_jcl(ss.jcl_result, filename=filename, error=ss.jcl_error)
    elif view == "COBOL ↔ Java":
        state.ensure_java_generation(client, workspace_id, filename)
        state.ensure_cobol_source(client, workspace_id, filename)
        state.ensure_java_workspace(client, workspace_id, filename)
        behavioral_status = None
        if (
            ss.java_workspace_result is not None
            and ss.java_workspace_result_filename == filename
        ):
            behavioral_status = ss.java_workspace_result.get("behavioral_status")
        render_java_view(
            ss.java_generation_result,
            ss.cobol_source,
            behavioral_status=behavioral_status,
            error=ss.java_generation_error,
        )
    elif view == "Java Workspace":
        state.ensure_java_workspace(client, workspace_id, filename)
        render_java_workspace(ss.java_workspace_result, error=ss.java_workspace_error)
    elif view == "Validation Center":
        state.ensure_validation(client, workspace_id, filename)
        state.ensure_report(client, workspace_id, filename)
        render_validation(
            ss.validation_result, report=_report_for_file(), error=ss.validation_error
        )
    elif view == "Report":
        state.ensure_report(client, workspace_id, filename)
        render_report(ss.report_result, error=ss.report_error)
    elif view == "Modernization Chat":
        state.ensure_report(client, workspace_id, filename)
        render_chat(client, workspace_id, filename, report=_report_for_file())


def _render_landing_stage() -> None:
    """The marketing landing page; its buttons move on to the entry stage."""

    # Stage transitions mutate session_state mid-script; without an explicit
    # rerun, Streamlit finishes rendering the CURRENT (landing) branch before
    # the new stage takes effect and the click appears to do nothing.
    def _enter_platform() -> None:
        st.session_state.intro_seen = True
        st.session_state.stage = "entry"
        st.rerun()

    def _watch_intro() -> None:
        st.session_state.intro_seen = True
        st.rerun()

    render_landing(
        on_enter_platform=_enter_platform,
        on_login=_enter_platform,
        on_watch_intro=_watch_intro,
        intro_seen=st.session_state.intro_seen,
    )


def _render_entry_stage() -> None:
    """The local, session-only sign-in screen."""

    def _continue(name: str) -> None:
        st.session_state.engineer_name = name
        st.session_state.stage = "workspace"
        st.rerun()

    render_entry(on_continue=_continue)


def _render_workspace_stage(client: BackendClient) -> None:
    """Sidebar + top bar + the active view."""
    # An invisible anchor element, deliberately rendered before `with
    # st.sidebar:` below. Without *some* real main-body element preceding it,
    # `st.sidebar` being the very first thing this stage renders confuses
    # Streamlit's delta-path reconciliation on the rerun that transitions from
    # the entry stage into this one: the entry screen's widgets survive into
    # the workspace stage's tree and later crash on a stale session_state
    # lookup. Confirmed empirically with AppTest; it must stay a plain,
    # native Streamlit element.
    st.empty()

    with st.sidebar:
        render_sidebar(client)

    view = st.session_state.active_view
    if view not in OUTER_VIEWS:
        view = "Overview"
        st.session_state.active_view = view

    report = _report_for_file()
    render_topbar(client, view, report.get("overall_status") if report else None)

    if not st.session_state.workspace_id:
        render_welcome(client)
    elif view == "Portfolio":
        state.load_summary(client, st.session_state.workspace_id)
        render_portfolio(
            st.session_state.inventory_files,
            st.session_state.summary,
            workspace_id=st.session_state.workspace_id,
        )
    elif not st.session_state.filename:
        ui.render(
            ui.empty_state(
                "file",
                "No file selected",
                "This workspace has no files to analyse. Switch workspace in the sidebar.",
            )
        )
    else:
        _render_workspace_body(client, view)


FAVICON = ASSET_DIR / "favicon.png"


def main() -> None:
    """Entry point: configure the page and route to the current stage."""
    st.set_page_config(
        page_title="Mainframe Modernization Assistant",
        page_icon=str(FAVICON),
        layout="wide",
    )
    state.init_session_state()
    inject_base_theme(extra=("chat.css",))
    client = get_client()

    stage = st.session_state.stage
    if stage == "landing":
        _render_landing_stage()
    elif stage == "entry":
        _render_entry_stage()
    else:
        _render_workspace_stage(client)


main()
