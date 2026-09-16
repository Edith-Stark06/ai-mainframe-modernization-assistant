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

from typing import Any, Dict, List, Optional, Tuple  # noqa: E402

import streamlit as st  # noqa: E402

from app.frontend.architecture_view import render_architecture  # noqa: E402
from app.frontend.chat_view import render_chat  # noqa: E402
from app.frontend.client import BackendAPIError, BackendClient  # noqa: E402
from app.frontend.components import (  # noqa: E402
    pipeline_steps,
    render_force_graph,
    section_header,
    stat_row,
)
from app.frontend.dependencies_view import render_dependencies  # noqa: E402
from app.frontend.entry import render_entry  # noqa: E402
from app.frontend.java_view import render_java_view  # noqa: E402
from app.frontend.java_workspace import render_java_workspace  # noqa: E402
from app.frontend.landing import render_landing  # noqa: E402
from app.frontend.mainframe import (  # noqa: E402
    ChipState,
    chip_label_and_status,
    compute_chip_state,
)
from app.frontend.report_view import render_report  # noqa: E402
from app.frontend.rules_view import (  # noqa: E402
    SEVERITY_TO_STATUS,
    render_business_rules,
)
from app.frontend.theme import inject_base_theme, status_pill  # noqa: E402
from app.frontend.validation_view import render_validation  # noqa: E402

# -- left sidebar navigation ------------------------------------------------
# Grouped exactly per the locked Stitch design: Overview stands alone,
# then ANALYSIS / TRANSFORMATION / VALIDATION / AI. Each entry is a real
# st.button (Streamlit cannot bind arbitrary custom nav widgets), styled in
# theme.py so the active one reads as a highlighted row rather than
# Streamlit's default filled button.
NAV_GROUPS: List[Tuple[Optional[str], List[str]]] = [
    (None, ["Overview"]),
    ("ANALYSIS", ["Business Rules", "Dependencies", "Architecture"]),
    ("TRANSFORMATION", ["COBOL ↔ Java", "Java Workspace"]),
    ("VALIDATION", ["Validation Center", "Report"]),
    ("AI", ["Modernization Chat"]),
]
OUTER_VIEWS: List[str] = [view for _, views in NAV_GROUPS for view in views]

_NAV_KEYS: Dict[str, str] = {
    "Overview": "nav_overview",
    "Business Rules": "nav_business_rules",
    "Dependencies": "nav_dependencies",
    "Architecture": "nav_architecture",
    "COBOL ↔ Java": "nav_cobol_java",
    "Java Workspace": "nav_java_workspace",
    "Validation Center": "nav_validation_center",
    "Report": "nav_report",
    "Modernization Chat": "nav_chat",
}

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


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


# -- sidebar: navigation + compact workspace/file/session block -------------


def _render_sidebar_nav() -> None:
    st.markdown(
        '<div class="mf-nav-brand">MAINFRAME<br/>MODERNIZATION'
        '<span class="mf-tagline">UNDERSTAND · TRANSFORM · VALIDATE</span></div>',
        unsafe_allow_html=True,
    )
    active = st.session_state.active_view
    for group_label, views in NAV_GROUPS:
        if group_label:
            group_cls = (
                "mf-nav-group mf-nav-group--ai"
                if group_label == "AI"
                else "mf-nav-group"
            )
            st.markdown(
                f'<div class="{group_cls}">{group_label}</div>',
                unsafe_allow_html=True,
            )
        for view in views:
            if st.button(
                view,
                key=_NAV_KEYS[view],
                type="primary" if view == active else "secondary",
                use_container_width=True,
            ):
                st.session_state.active_view = view
                st.rerun()


def _render_workspace_selection(client: BackendClient) -> None:
    st.markdown(
        '<div class="mf-nav-group" style="margin-left:0;">WORKSPACE</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Change workspace", expanded=not st.session_state.workspace_id):
        st.markdown("**Upload new source files**")
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

        st.markdown("**Use an existing workspace**")
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

    if not st.session_state.workspace_id:
        st.caption("No workspace selected.")
        greeting = st.session_state.engineer_name or "Guest"
        st.caption(f"Session: {greeting}")
        return

    st.caption(f"Workspace: `{st.session_state.workspace_id}`")

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

    greeting = st.session_state.engineer_name or "Guest"
    st.caption(f"Session: {greeting}")


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


# -- top bar ------------------------------------------------------------


def _render_topbar() -> None:
    """The thin header row above the workspace: filename/COBOL badge/honest
    status on the left, a real Help popover (static product copy -- no
    fabricated capability) and the session line on the right. No search box
    is rendered: no backend search endpoint exists, and a non-functional
    search input would be a fake affordance."""
    filename = st.session_state.filename or "No file selected"
    label, word = chip_label_and_status(_current_chip_state())
    greeting = st.session_state.engineer_name or "Guest"

    left, help_col, session_col = st.columns([6, 1, 2])
    with left:
        st.markdown(
            f'<div class="mf-topbar-left">'
            f'<span class="mf-topbar-file">{filename}</span>'
            f'<span class="mf-topbar-badge">COBOL</span>'
            f"&nbsp;&nbsp;{status_pill(label, word)}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with help_col:
        with st.popover("Help", use_container_width=True):
            st.markdown("**Mainframe Modernization Assistant**")
            st.caption(
                "Understand, transform, and validate COBOL programs. Every "
                "result shown is grounded in real backend analysis -- "
                "nothing is fabricated."
            )
            st.caption(
                "Start in the sidebar: select or upload a workspace, choose "
                "a source file, then use Analysis / Transformation / "
                "Validation / AI to explore it."
            )
    with session_col:
        st.markdown(
            f'<div class="mf-topbar-session">{greeting} &middot; session-local</div>',
            unsafe_allow_html=True,
        )
    st.markdown('<div class="mf-topbar-rule"></div>', unsafe_allow_html=True)


# -- Overview: modernization command center ------------------------------


def _pipeline_step_states(report: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Derive the four pipeline-stepper states purely from real,
    already-fetched report fields -- same class of derivation as
    ``compute_chip_state``: no timers, no guesses.

    Each stage is evaluated independently from its own real signal, never
    cascaded off an earlier stage's flag: a partial/unclean parse
    (``analysis_success`` False, e.g. from unsupported COBOL constructs)
    does not by itself mean no business rules were extracted or no Java
    was generated -- the pipeline is resilient and best-effort, and the
    stepper must reflect that honestly instead of hiding real downstream
    results behind an unrelated upstream flag.
    """
    analyze_state = "done" if report.get("analysis_success") else "fail"

    rules = report.get("business_rules") or []
    understand_state = "done" if rules else "pending"

    project = report.get("project")
    compilation = report.get("compilation")
    if project and compilation and compilation.get("success"):
        transform_state = "done"
    elif project:
        transform_state = "partial"
    else:
        transform_state = "pending"

    overall = report.get("overall_status")
    if overall == "PASS":
        validate_state = "done"
    elif overall == "FAIL":
        validate_state = "fail"
    elif overall == "INCONCLUSIVE":
        validate_state = "partial"
    else:
        validate_state = "pending"

    return [
        ("ANALYZE", analyze_state),
        ("UNDERSTAND", understand_state),
        ("TRANSFORM", transform_state),
        ("VALIDATE", validate_state),
    ]


def _overview_stat_items(report: Dict[str, Any]) -> List[Tuple[str, str]]:
    architecture = report.get("architecture") or {}
    components = architecture.get("components") or []
    services = sum(1 for c in components if c.get("type") == "SERVICE")
    project = report.get("project") or {}
    java_files = sum(1 for p in (project.get("files") or {}) if p.endswith(".java"))
    coverage = report.get("coverage")
    coverage_pct = f"{coverage['overall']:.0%}" if coverage else "—"
    return [
        ("Business Rules", str(len(report.get("business_rules") or []))),
        ("Dependencies", str(len(report.get("dependencies") or []))),
        ("Risks", str(len(report.get("risks") or []))),
        ("Services", str(services)),
        ("Java Files", str(java_files)),
        ("Coverage", coverage_pct),
    ]


def _render_key_findings(report: Dict[str, Any]) -> None:
    st.markdown("**Key Findings**")
    risks = sorted(
        report.get("risks") or [],
        key=lambda r: _SEVERITY_ORDER.get(str(r.get("severity", "")).upper(), 9),
    )[:4]
    if not risks:
        st.caption("No risks identified.")
    for risk in risks:
        status = SEVERITY_TO_STATUS.get(str(risk.get("severity", "")).upper(), "WARN")
        st.markdown(
            status_pill(risk.get("title", risk.get("risk_id", "")), status),
            unsafe_allow_html=True,
        )
        st.caption(risk.get("explanation", ""))

    strategy = (report.get("strategy") or {}).get("primary")
    if strategy:
        st.caption(
            f"Recommended strategy: **{strategy['strategy']}** — "
            f"{strategy.get('rationale', '')}"
        )


def _render_critical_topology() -> None:
    st.markdown("**Critical Topology**")
    if st.session_state.modernization_error:
        st.error(st.session_state.modernization_error)
        return

    result = st.session_state.modernization_result
    has_result = (
        result is not None
        and st.session_state.modernization_result_filename == st.session_state.filename
    )
    if not has_result:
        st.info("Click 'Analyze for Modernization' in the sidebar to see topology.")
        return

    flow = result.get("flow") or {}
    nodes = [(n["id"], n.get("name", n["id"])) for n in flow.get("nodes", [])]
    edges = [
        (e["source_id"], e["target_id"], e.get("edge_type", ""))
        for e in flow.get("edges", [])
    ]
    render_force_graph(
        nodes,
        edges,
        empty_message=(
            "Empty flow generated. No control-flow topology could be "
            "extracted from this file."
        ),
    )


def _render_overview() -> None:
    filename = st.session_state.filename
    if st.session_state.report_error:
        st.error(st.session_state.report_error)
        return

    report = st.session_state.report_result
    has_report = (
        report is not None and st.session_state.report_result_filename == filename
    )
    if not has_report:
        st.info("Loading modernization report...")
        return

    paragraphs = report.get("paragraphs") or []
    subtitle = (
        f"{len(paragraphs)} paragraph(s) analyzed."
        if paragraphs
        else "No paragraphs were extracted from this file."
    )
    section_header(filename or "", subtitle)

    stat_row(_overview_stat_items(report))

    st.markdown("**Modernization Pipeline**")
    pipeline_steps(_pipeline_step_states(report))

    left, right = st.columns([1, 1], gap="large")
    with left:
        _render_key_findings(report)
    with right:
        _render_critical_topology()


def _render_workspace_body(client: BackendClient) -> None:
    workspace_id = st.session_state.workspace_id
    filename = st.session_state.filename

    view = st.session_state.active_view
    if view not in OUTER_VIEWS:
        view = "Overview"
        st.session_state.active_view = view

    if view == "Overview":
        _ensure_report(client, workspace_id, filename)
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
        _ensure_java_workspace(client, workspace_id, filename)
        behavioral_status = None
        if (
            st.session_state.java_workspace_result is not None
            and st.session_state.java_workspace_result_filename == filename
        ):
            behavioral_status = st.session_state.java_workspace_result.get(
                "behavioral_status"
            )
        render_java_view(
            st.session_state.java_generation_result,
            st.session_state.cobol_source,
            behavioral_status=behavioral_status,
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
        _ensure_report(client, workspace_id, filename)
        report_for_validation = (
            st.session_state.report_result
            if st.session_state.report_result_filename == filename
            else None
        )
        render_validation(
            st.session_state.validation_result,
            report=report_for_validation,
            error=st.session_state.validation_error,
        )
    elif view == "Report":
        _ensure_report(client, workspace_id, filename)
        render_report(
            st.session_state.report_result, error=st.session_state.report_error
        )
    elif view == "Modernization Chat":
        _ensure_report(client, workspace_id, filename)
        report_for_chat = (
            st.session_state.report_result
            if st.session_state.report_result_filename == filename
            else None
        )
        render_chat(client, workspace_id, filename, report=report_for_chat)


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
    # An invisible anchor element, deliberately rendered before `with
    # st.sidebar:` below. Without *some* real main-body element preceding
    # it, `st.sidebar` being the very first thing this stage renders
    # confuses Streamlit's delta-path reconciliation on the rerun that
    # transitions from the entry stage into this one: the entry screen's
    # widgets (Sign In / Continue as Guest, its text inputs) survive into
    # the workspace stage's tree instead of being cleared, and later crash
    # on a stale session_state lookup once any widget below triggers
    # another rerun (e.g. clicking "Load Workspace"). Confirmed empirically
    # with streamlit.testing.v1.AppTest; a raw `unsafe_allow_html` markdown
    # block does not have the same anchoring effect, so this must stay a
    # plain, native Streamlit element.
    st.empty()

    with st.sidebar:
        _render_sidebar_nav()
        _render_workspace_selection(client)

    _render_topbar()

    if st.session_state.loading:
        st.info("Loading modernization analysis...")
    elif not st.session_state.workspace_id or not st.session_state.filename:
        st.info("Please select a workspace and file from the sidebar.")
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
