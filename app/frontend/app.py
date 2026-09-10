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

from typing import Any, Dict, List, Optional  # noqa: E402

import streamlit as st  # noqa: E402

from app.frontend.architecture_view import render_architecture  # noqa: E402
from app.frontend.chat_view import render_chat  # noqa: E402
from app.frontend.client import BackendAPIError, BackendClient  # noqa: E402
from app.frontend.dependencies_view import render_dependencies  # noqa: E402
from app.frontend.entry import render_entry  # noqa: E402
from app.frontend.java_view import render_java_view  # noqa: E402
from app.frontend.java_workspace import render_java_workspace  # noqa: E402
from app.frontend.landing import render_landing  # noqa: E402
from app.frontend.mainframe import (  # noqa: E402
    ChipState,
    compute_chip_state,
    render_ai_core_status,
    render_mainframe_diagram,
    render_subsystem_nav,
)
from app.frontend.report_view import render_report  # noqa: E402
from app.frontend.rules_view import (  # noqa: E402
    render_business_rules,
    render_risks_and_strategy,
)
from app.frontend.theme import inject_base_theme  # noqa: E402
from app.frontend.validation_view import render_validation  # noqa: E402

PRIORITY_ICONS = {"HIGH": "\U0001f534", "MEDIUM": "\U0001f7e0", "LOW": "\U0001f7e2"}

OUTER_VIEWS = [
    "Overview",
    "Business Rules",
    "Dependencies",
    "Architecture",
    "COBOL ↔ Java",
    "Java Workspace",
    "Validation Center",
    "Report",
]


@st.cache_resource
def get_client() -> BackendClient:
    return BackendClient()


def _init_session_state() -> None:
    defaults: Dict[str, Any] = {
        # -- app-wide navigation stage ---------------------------------
        "stage": "landing",  # "landing" | "entry" | "workspace"
        "intro_seen": False,
        "engineer_name": None,
        "active_view": "Overview",
        # -- existing workspace/analysis state (unchanged) -------------
        "workspace_id": None,
        "known_workspace_ids": [],
        "inventory_files": [],
        "inventory_error": None,
        "filename": None,
        "modernization_result": None,
        "modernization_result_filename": None,
        "modernization_error": None,
        "loading": False,
        "messages": [],
        # -- new, lazily-loaded views (#134 / #135) ---------------------
        "analysis_result": None,
        "analysis_result_filename": None,
        "analysis_error": None,
        "intelligence_result": None,
        "intelligence_result_filename": None,
        "intelligence_error": None,
        # -- new, lazily-loaded views (Architecture / Java / Validation / Report) --
        "architecture_result": None,
        "architecture_result_filename": None,
        "architecture_error": None,
        "java_generation_result": None,
        "java_generation_result_filename": None,
        "java_generation_error": None,
        "cobol_source": None,
        "cobol_source_filename": None,
        "validation_result": None,
        "validation_result_filename": None,
        "validation_error": None,
        "report_result": None,
        "report_result_filename": None,
        "report_error": None,
        "java_workspace_result": None,
        "java_workspace_result_filename": None,
        "java_workspace_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_workspace(workspace_id: str) -> None:
    """Switch to a (new or existing) workspace, clearing all downstream state."""
    st.session_state.workspace_id = workspace_id
    if workspace_id not in st.session_state.known_workspace_ids:
        st.session_state.known_workspace_ids.append(workspace_id)
    st.session_state.inventory_files = []
    st.session_state.inventory_error = None
    st.session_state.filename = None
    st.session_state.modernization_result = None
    st.session_state.modernization_result_filename = None
    st.session_state.modernization_error = None
    st.session_state.messages = []
    st.session_state.analysis_result = None
    st.session_state.analysis_result_filename = None
    st.session_state.analysis_error = None
    st.session_state.intelligence_result = None
    st.session_state.intelligence_result_filename = None
    st.session_state.intelligence_error = None
    st.session_state.architecture_result = None
    st.session_state.architecture_result_filename = None
    st.session_state.architecture_error = None
    st.session_state.java_generation_result = None
    st.session_state.java_generation_result_filename = None
    st.session_state.java_generation_error = None
    st.session_state.cobol_source = None
    st.session_state.cobol_source_filename = None
    st.session_state.validation_result = None
    st.session_state.validation_result_filename = None
    st.session_state.validation_error = None
    st.session_state.report_result = None
    st.session_state.report_result_filename = None
    st.session_state.report_error = None
    st.session_state.java_workspace_result = None
    st.session_state.java_workspace_result_filename = None
    st.session_state.java_workspace_error = None


def _load_inventory(client: BackendClient, workspace_id: str) -> None:
    try:
        inventory = client.get_inventory(workspace_id)
        st.session_state.inventory_files = inventory.get("files", [])
        st.session_state.inventory_error = None
    except BackendAPIError as e:
        st.session_state.inventory_files = []
        st.session_state.inventory_error = e.message


def _ensure_analysis(client: BackendClient, workspace_id: str, filename: str) -> None:
    """Lazily fetch (and cache by filename) the /analyze response -- only
    when a view that needs it is actually opened, per the "do not reload
    large analysis artifacts unnecessarily" performance rule."""
    if st.session_state.analysis_result_filename == filename:
        return
    try:
        with st.spinner("Loading dependency analysis..."):
            st.session_state.analysis_result = client.get_analysis(
                workspace_id, filename
            )
        st.session_state.analysis_result_filename = filename
        st.session_state.analysis_error = None
    except BackendAPIError as e:
        st.session_state.analysis_result = None
        st.session_state.analysis_result_filename = filename
        st.session_state.analysis_error = e.message


def _ensure_intelligence(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    if st.session_state.intelligence_result_filename == filename:
        return
    try:
        with st.spinner("Extracting business rules, risks, and strategy..."):
            st.session_state.intelligence_result = (
                client.get_modernization_intelligence(workspace_id, filename)
            )
        st.session_state.intelligence_result_filename = filename
        st.session_state.intelligence_error = None
    except BackendAPIError as e:
        st.session_state.intelligence_result = None
        st.session_state.intelligence_result_filename = filename
        st.session_state.intelligence_error = e.message


def _ensure_architecture(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    if st.session_state.architecture_result_filename == filename:
        return
    try:
        with st.spinner("Deriving architecture..."):
            st.session_state.architecture_result = client.get_architecture(
                workspace_id, filename
            )
        st.session_state.architecture_result_filename = filename
        st.session_state.architecture_error = None
    except BackendAPIError as e:
        st.session_state.architecture_result = None
        st.session_state.architecture_result_filename = filename
        st.session_state.architecture_error = e.message


def _ensure_java_generation(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    if st.session_state.java_generation_result_filename == filename:
        return
    try:
        with st.spinner("Generating and compiling Java..."):
            st.session_state.java_generation_result = client.get_java_generation(
                workspace_id, filename
            )
        st.session_state.java_generation_result_filename = filename
        st.session_state.java_generation_error = None
    except BackendAPIError as e:
        st.session_state.java_generation_result = None
        st.session_state.java_generation_result_filename = filename
        st.session_state.java_generation_error = e.message


def _ensure_cobol_source(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    if st.session_state.cobol_source_filename == filename:
        return
    try:
        data = client.get_file_content(workspace_id, filename)
        st.session_state.cobol_source = data.get("content")
    except BackendAPIError:
        st.session_state.cobol_source = None
    st.session_state.cobol_source_filename = filename


def _ensure_validation(client: BackendClient, workspace_id: str, filename: str) -> None:
    if st.session_state.validation_result_filename == filename:
        return
    try:
        with st.spinner("Validating..."):
            st.session_state.validation_result = client.get_validation(
                workspace_id, filename
            )
        st.session_state.validation_result_filename = filename
        st.session_state.validation_error = None
    except BackendAPIError as e:
        st.session_state.validation_result = None
        st.session_state.validation_result_filename = filename
        st.session_state.validation_error = e.message


def _ensure_report(client: BackendClient, workspace_id: str, filename: str) -> None:
    if st.session_state.report_result_filename == filename:
        return
    try:
        with st.spinner("Building modernization report..."):
            st.session_state.report_result = client.get_modernization_report(
                workspace_id, filename
            )
        st.session_state.report_result_filename = filename
        st.session_state.report_error = None
    except BackendAPIError as e:
        st.session_state.report_result = None
        st.session_state.report_result_filename = filename
        st.session_state.report_error = e.message


def _ensure_java_workspace(
    client: BackendClient, workspace_id: str, filename: str
) -> None:
    if st.session_state.java_workspace_result_filename == filename:
        return
    try:
        with st.spinner("Loading Java workspace..."):
            st.session_state.java_workspace_result = client.get_java_workspace(
                workspace_id, filename
            )
        st.session_state.java_workspace_result_filename = filename
        st.session_state.java_workspace_error = None
    except BackendAPIError as e:
        st.session_state.java_workspace_result = None
        st.session_state.java_workspace_result_filename = filename
        st.session_state.java_workspace_error = e.message


def _render_workspace_selection(client: BackendClient) -> None:
    st.header("Source Selection")

    with st.expander(
        "Upload new source files", expanded=not st.session_state.workspace_id
    ):
        uploaded = st.file_uploader(
            "Mainframe source files (.cbl, .cob, .cpy, .jcl, .txt, .zip)",
            accept_multiple_files=True,
            key="uploader",
        )
        if st.button("Upload", disabled=not uploaded, key="upload_button"):
            files = [(f.name, f.getvalue()) for f in uploaded]
            try:
                result = client.upload_files(files)
                workspace_id = result["workspace_id"]
                _reset_workspace(workspace_id)
                _load_inventory(client, workspace_id)
                st.success(f"Uploaded {result.get('total_files', len(files))} file(s).")
            except BackendAPIError as e:
                st.error(e.message)

    with st.expander("Use an existing workspace", expanded=False):
        options = ["(enter manually)"] + st.session_state.known_workspace_ids
        choice = st.selectbox(
            "Known workspaces", options=options, index=0, key="known_ws_select"
        )
        manual_id = st.text_input("Workspace ID", value="", key="manual_ws_input")
        target_id = manual_id.strip() if choice == "(enter manually)" else choice

        if st.button(
            "Load Workspace",
            disabled=not target_id.strip(),
            key="load_workspace_button",
        ):
            _reset_workspace(target_id.strip())
            _load_inventory(client, target_id.strip())

    if st.session_state.workspace_id:
        st.caption(f"Active workspace: `{st.session_state.workspace_id}`")

        if st.session_state.inventory_error:
            st.error(st.session_state.inventory_error)
        elif not st.session_state.inventory_files:
            st.info("No files found in this workspace.")
        else:
            filenames = [f["filename"] for f in st.session_state.inventory_files]
            current = st.session_state.filename
            index = filenames.index(current) if current in filenames else 0
            selected = st.selectbox(
                "Source File", options=filenames, index=index, key="file_select"
            )
            if selected != current:
                # Switching files must not leave the previous file's chat
                # transcript displayed as if it were part of an ongoing
                # conversation about the newly selected file.
                st.session_state.messages = []
            st.session_state.filename = selected

            if st.button(
                "Analyze for Modernization",
                disabled=st.session_state.loading or not selected,
                key="analyze_button",
            ):
                st.session_state.loading = True
                st.session_state.modernization_result = None
                st.session_state.modernization_error = None
                try:
                    with st.spinner("Analyzing..."):
                        data = client.analyze_modernization(
                            st.session_state.workspace_id, selected
                        )
                    st.session_state.modernization_result = data
                    st.session_state.modernization_result_filename = selected
                except BackendAPIError as e:
                    st.session_state.modernization_error = e.message
                finally:
                    st.session_state.loading = False

    st.markdown("---")
    render_ai_core_status(_current_chip_state())


def _current_chip_state() -> ChipState:
    result = st.session_state.modernization_result
    has_result = (
        result is not None
        and st.session_state.modernization_result_filename == st.session_state.filename
    )
    insufficient = False
    risk_count = 0
    if has_result:
        insufficient = bool(
            (result.get("score", {}) or {}).get("metadata", {}).get("insufficient_data")
        ) or not (result.get("flow", {}) or {}).get("nodes")
    intel = st.session_state.intelligence_result
    if (
        intel is not None
        and st.session_state.intelligence_result_filename == st.session_state.filename
    ):
        risk_count = len(intel.get("risks", []))
    return compute_chip_state(
        has_analysis_result=has_result,
        is_loading=st.session_state.loading,
        insufficient_data=insufficient,
        risk_count=risk_count,
    )


def _render_scores(score: Dict[str, Any]) -> None:
    st.subheader("Modernization Scores")
    insufficient = bool(score.get("metadata", {}).get("insufficient_data"))
    if insufficient:
        st.caption("Scores are not meaningful: insufficient flow data was extracted.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Complexity", f"{score.get('complexity_score', 0.0) * 100:.0f}%")
    col2.metric("Coupling", f"{score.get('coupling_score', 0.0) * 100:.0f}%")
    col3.metric(
        "Overall Readiness", f"{score.get('overall_readiness', 0.0) * 100:.0f}%"
    )


def _render_flow(flow: Dict[str, Any]) -> None:
    st.subheader("Program Flow")
    nodes: List[Dict[str, Any]] = flow.get("nodes", [])
    edges: List[Dict[str, Any]] = flow.get("edges", [])

    if not nodes:
        st.info(
            "Empty flow generated. No process flow could be extracted from this file."
        )
        return

    external_count = sum(1 for n in nodes if n.get("node_type") == "EXTERNAL")
    st.caption(f"{len(nodes)} node(s), {len(edges)} edge(s)")
    if external_count:
        st.caption(
            f"⚠️ {external_count} external/unresolved reference(s) — these "
            "represent calls to code outside this file and are not resolved locally."
        )

    st.write("**Nodes**")
    st.dataframe(
        [
            {"ID": n.get("id"), "Name": n.get("name"), "Type": n.get("node_type")}
            for n in nodes
        ],
        width="stretch",
        hide_index=True,
    )

    st.write("**Edges**")
    if not edges:
        st.caption("No edges detected.")
    else:
        st.dataframe(
            [
                {
                    "Source": e.get("source_id"),
                    "Target": e.get("target_id"),
                    "Type": e.get("edge_type"),
                }
                for e in edges
            ],
            width="stretch",
            hide_index=True,
        )


def _render_recommendations(recommendations: List[Dict[str, Any]]) -> None:
    st.subheader("Recommendations")
    if not recommendations:
        st.info("No recommendations available for this file.")
        return

    for rec in recommendations:
        priority = rec.get("priority", "")
        icon = PRIORITY_ICONS.get(priority, "ℹ️")
        with st.expander(f"{icon} [{priority}] {rec.get('title', 'Recommendation')}"):
            st.write(rec.get("description", ""))


def _render_overview() -> None:
    """The original modernization-pipeline results: scores, flow,
    recommendations, and chat -- unchanged in behavior, restyled in place."""
    if st.session_state.modernization_error:
        st.error(st.session_state.modernization_error)
        return

    result = st.session_state.modernization_result
    if (
        result is None
        or st.session_state.modernization_result_filename != st.session_state.filename
    ):
        st.info("Click 'Analyze for Modernization' to begin.")
        return

    score = result.get("score", {})
    flow = result.get("flow", {})
    recommendations = result.get("recommendations", [])
    insufficient = bool(
        score.get("metadata", {}).get("insufficient_data")
    ) or not flow.get("nodes")

    if insufficient:
        st.warning(
            "Insufficient data was available to generate meaningful modernization "
            "results for this file."
        )
    else:
        st.success("Analysis complete.")

    tab1, tab2, tab3, tab4 = st.tabs(["Scores", "Flow", "Recommendations", "Chat"])
    with tab1:
        _render_scores(score)
    with tab2:
        _render_flow(flow)
    with tab3:
        _render_recommendations(recommendations)
    with tab4:
        render_chat(
            get_client(), st.session_state.workspace_id, st.session_state.filename
        )

    render_risks_and_strategy(
        st.session_state.intelligence_result
        if st.session_state.intelligence_result_filename == st.session_state.filename
        else None
    )


def _real_architecture_components() -> Optional[List[str]]:
    """Real component names for the mainframe diagram's "modern
    architecture" panel -- only when Architecture has actually been
    fetched for the current file; never fabricated."""
    arch = st.session_state.architecture_result
    if (
        arch is None
        or st.session_state.architecture_result_filename != st.session_state.filename
        or not arch.get("available")
    ):
        return None
    return [c["name"] for c in arch["architecture"]["components"]]


def _render_workspace_body(client: BackendClient) -> None:
    workspace_id = st.session_state.workspace_id
    filename = st.session_state.filename

    render_mainframe_diagram(
        _current_chip_state(),
        mode="live",
        architecture_components=_real_architecture_components(),
    )

    def _select_view(target: str) -> None:
        st.session_state.active_view = target

    render_subsystem_nav(_select_view)

    view = st.radio(
        "View",
        options=OUTER_VIEWS,
        horizontal=True,
        key="active_view",
        label_visibility="collapsed",
    )

    if view == "Overview":
        _render_overview()
    elif view == "Business Rules":
        _ensure_intelligence(client, workspace_id, filename)
        render_business_rules(
            st.session_state.intelligence_result,
            error=st.session_state.intelligence_error,
        )
    elif view == "Dependencies":
        _ensure_analysis(client, workspace_id, filename)
        render_dependencies(
            st.session_state.analysis_result, error=st.session_state.analysis_error
        )
    elif view == "Architecture":
        _ensure_architecture(client, workspace_id, filename)
        render_architecture(
            st.session_state.architecture_result,
            error=st.session_state.architecture_error,
        )
    elif view == "COBOL ↔ Java":
        _ensure_java_generation(client, workspace_id, filename)
        _ensure_cobol_source(client, workspace_id, filename)
        render_java_view(
            st.session_state.java_generation_result,
            st.session_state.cobol_source,
            error=st.session_state.java_generation_error,
        )
    elif view == "Java Workspace":
        _ensure_java_workspace(client, workspace_id, filename)
        render_java_workspace(
            st.session_state.java_workspace_result,
            error=st.session_state.java_workspace_error,
        )
    elif view == "Validation Center":
        _ensure_validation(client, workspace_id, filename)
        render_validation(
            st.session_state.validation_result, error=st.session_state.validation_error
        )
    elif view == "Report":
        _ensure_report(client, workspace_id, filename)
        render_report(
            st.session_state.report_result, error=st.session_state.report_error
        )


def _render_landing_stage() -> None:
    # Stage transitions mutate session_state mid-script; without an
    # explicit rerun, Streamlit finishes rendering the CURRENT (landing)
    # branch before the new stage takes effect, and the click would
    # appear to do nothing until some later, unrelated interaction.
    def _enter_platform() -> None:
        st.session_state.intro_seen = True
        st.session_state.stage = "entry"
        st.rerun()

    def _login() -> None:
        st.session_state.intro_seen = True
        st.session_state.stage = "entry"
        st.rerun()

    def _watch_intro() -> None:
        st.session_state.intro_seen = True
        st.rerun()

    render_landing(
        on_enter_platform=_enter_platform,
        on_login=_login,
        on_watch_intro=_watch_intro,
        intro_seen=st.session_state.intro_seen,
    )


def _render_entry_stage() -> None:
    def _continue(name: str) -> None:
        st.session_state.engineer_name = name
        st.session_state.stage = "workspace"
        st.rerun()

    render_entry(on_continue=_continue)


def _render_workspace_stage(client: BackendClient) -> None:
    greeting = st.session_state.engineer_name or "Engineer"
    st.title("\U0001f916 AI-Powered Mainframe Modernization Assistant")
    st.caption(f"Welcome, {greeting}. Session is local to this browser tab.")

    with st.sidebar:
        _render_workspace_selection(client)

    if st.session_state.loading:
        st.info("Loading modernization analysis...")
    elif not st.session_state.workspace_id or not st.session_state.filename:
        st.info("Please select a workspace and file from the sidebar.")
        render_mainframe_diagram(ChipState.IDLE, mode="live")
    else:
        _render_workspace_body(client)


def main() -> None:
    st.set_page_config(
        page_title="Mainframe Modernization Assistant",
        page_icon="\U0001f916",
        layout="wide",
    )
    _init_session_state()
    inject_base_theme()
    client = get_client()

    stage = st.session_state.stage
    if stage == "landing":
        _render_landing_stage()
    elif stage == "entry":
        _render_entry_stage()
    else:
        _render_workspace_stage(client)


main()
