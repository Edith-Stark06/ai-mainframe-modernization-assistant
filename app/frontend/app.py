"""Streamlit UI for the AI-Powered Mainframe Modernization Assistant."""

from typing import Any, Dict, List, Optional

import streamlit as st

from app.frontend.client import BackendAPIError, BackendClient

PRIORITY_ICONS = {"HIGH": "\U0001f534", "MEDIUM": "\U0001f7e0", "LOW": "\U0001f7e2"}


@st.cache_resource
def get_client() -> BackendClient:
    return BackendClient()


def _init_session_state() -> None:
    defaults: Dict[str, Any] = {
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


def _load_inventory(client: BackendClient, workspace_id: str) -> None:
    try:
        inventory = client.get_inventory(workspace_id)
        st.session_state.inventory_files = inventory.get("files", [])
        st.session_state.inventory_error = None
    except BackendAPIError as e:
        st.session_state.inventory_files = []
        st.session_state.inventory_error = e.message


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
        use_container_width=True,
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
            use_container_width=True,
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


def _render_chat(
    client: BackendClient, workspace_id: str, filename: Optional[str]
) -> None:
    st.subheader("Modernization Chat")

    include_context = st.checkbox(
        "Include modernization context for this file",
        value=False,
        disabled=not filename,
        key="include_modernization_context",
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt = st.chat_input("Ask about this source file", key="chat_input")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    chat_res = client.send_chat_message(
                        workspace_id=workspace_id,
                        query=prompt,
                        filename=filename,
                        include_modernization_context=include_context,
                    )
                    error = chat_res.get("error")
                    if error:
                        st.warning(error)
                    answer = chat_res.get("answer") or "No response generated."
                    st.write(answer)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer}
                    )
                except BackendAPIError as e:
                    st.error(e.message)


def _render_results() -> None:
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
        _render_chat(
            get_client(), st.session_state.workspace_id, st.session_state.filename
        )


def main() -> None:
    st.set_page_config(
        page_title="Mainframe Modernization Assistant",
        page_icon="\U0001f916",
        layout="wide",
    )
    _init_session_state()
    client = get_client()

    st.title("\U0001f916 AI-Powered Mainframe Modernization Assistant")

    with st.sidebar:
        _render_workspace_selection(client)

    if st.session_state.loading:
        st.info("Loading modernization analysis...")
    elif not st.session_state.workspace_id or not st.session_state.filename:
        st.info("Please select a workspace and file from the sidebar.")
    else:
        _render_results()


main()
