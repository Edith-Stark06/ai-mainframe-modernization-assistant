"""
Behavioral tests for the Streamlit modernization UI (``app/frontend/app.py``).

Uses :class:`streamlit.testing.v1.AppTest` to drive the real script exactly
as a user would (filling inputs, clicking buttons) and asserts on what is
actually rendered, rather than on internal calls. The backend is mocked at
the :class:`~app.frontend.client.BackendClient` boundary only -- the API
client itself is covered separately in ``test_client.py``.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.frontend.client import BackendAPIError, BackendClient

APP_PATH = str(Path(__file__).parent.parent.parent / "app" / "frontend" / "app.py")

INVENTORY_TWO_FILES = {
    "workspace_id": "ws-1",
    "files": [
        {"filename": "MAIN.cbl", "extension": ".cbl", "file_type": "COBOL"},
        {"filename": "UTIL.cbl", "extension": ".cbl", "file_type": "COBOL"},
    ],
    "total_files": 2,
}

SUCCESSFUL_PIPELINE = {
    "flow": {
        "id": "flow-1",
        "name": "MAIN flow",
        "nodes": [
            {"id": "n1", "node_type": "PROGRAM", "name": "MAIN", "metadata": {}},
            {"id": "n2", "node_type": "EXTERNAL", "name": "SUBRTN", "metadata": {}},
        ],
        "edges": [
            {
                "id": "e1",
                "source_id": "n1",
                "target_id": "n2",
                "edge_type": "CALLS",
                "metadata": {},
            }
        ],
        "metadata": {},
    },
    "score": {
        "complexity_score": 0.42,
        "coupling_score": 0.2,
        "overall_readiness": 0.8,
        "metadata": {"node_count": 2, "edge_count": 1},
    },
    "recommendations": [
        {
            "id": "rec_ready",
            "title": "Ready for Modernization",
            "description": "This module is well-structured and ready for direct modernization.",
            "priority": "LOW",
        }
    ],
}

INSUFFICIENT_DATA_PIPELINE = {
    "flow": {
        "id": "flow-2",
        "name": "EMPTY flow",
        "nodes": [],
        "edges": [],
        "metadata": {},
    },
    "score": {
        "complexity_score": 0.0,
        "coupling_score": 0.0,
        "overall_readiness": 0.0,
        "metadata": {"node_count": 0, "edge_count": 0, "insufficient_data": True},
    },
    "recommendations": [
        {
            "id": "rec_insufficient_data",
            "title": "Insufficient Data",
            "description": "The analysis did not provide enough flow data to make solid modernization recommendations.",
            "priority": "HIGH",
        }
    ],
}


def _make_app() -> AppTest:
    at = AppTest.from_file(APP_PATH)
    at.default_timeout = 20
    return at


def _load_workspace(at: AppTest, workspace_id: str = "ws-1") -> AppTest:
    at.text_input(key="manual_ws_input").set_value(workspace_id)
    at.button(key="load_workspace_button").click().run()
    return at


def test_initial_state_prompts_for_selection():
    at = _make_app()
    at.run()

    assert not at.exception
    assert any("select a workspace and file" in info.value for info in at.info)


def test_load_workspace_lists_inventory_files(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )

    at = _make_app()
    at.run()
    _load_workspace(at)

    assert not at.exception
    select = at.selectbox(key="file_select")
    assert select.options == ["MAIN.cbl", "UTIL.cbl"]
    assert at.session_state["workspace_id"] == "ws-1"


def test_inventory_failure_shows_safe_error_not_stack_trace(monkeypatch):
    def raise_error(self, ws_id):
        raise BackendAPIError("The requested resource was not found.", 404)

    monkeypatch.setattr(BackendClient, "get_inventory", raise_error)

    at = _make_app()
    at.run()
    _load_workspace(at, "missing-ws")

    assert not at.exception
    assert any("requested resource was not found" in e.value for e in at.error)
    assert not any("Traceback" in e.value for e in at.error)


def test_successful_analysis_renders_scores_flow_and_recommendations(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws_id, filename: SUCCESSFUL_PIPELINE,
    )

    at = _make_app()
    at.run()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    assert not at.exception
    assert any("Analysis complete" in s.value for s in at.success)

    metric_values = {m.label: m.value for m in at.metric}
    assert metric_values["Complexity"] == "42%"
    assert metric_values["Coupling"] == "20%"
    assert metric_values["Overall Readiness"] == "80%"

    node_rows = at.dataframe[0].value
    assert list(node_rows["ID"]) == ["n1", "n2"]
    assert "EXTERNAL" in list(node_rows["Type"])

    assert any(
        "external" in c.value.lower()
        for c in at.caption
        if "external" in c.value.lower()
    )

    rec_titles = [e.label for e in at.expander]
    assert any("Ready for Modernization" in title for title in rec_titles)


def test_insufficient_data_does_not_claim_success(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws_id, filename: INSUFFICIENT_DATA_PIPELINE,
    )

    at = _make_app()
    at.run()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    assert not at.exception
    assert not list(at.success)
    assert any("Insufficient data" in w.value for w in at.warning)
    assert any("Empty flow generated" in i.value for i in at.info)


def test_analysis_api_failure_shows_safe_error(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )

    def raise_error(self, ws_id, filename):
        raise BackendAPIError(
            "The server encountered an error. Please try again later.", 500
        )

    monkeypatch.setattr(BackendClient, "analyze_modernization", raise_error)

    at = _make_app()
    at.run()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    assert not at.exception
    assert not list(at.success)
    assert any("server encountered an error" in e.value for e in at.error)


def test_switching_file_clears_stale_results(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws_id, filename: SUCCESSFUL_PIPELINE,
    )

    at = _make_app()
    at.run()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()
    assert any("Analysis complete" in s.value for s in at.success)

    at.selectbox(key="file_select").set_value("UTIL.cbl").run()

    assert not list(at.success)
    assert any("Click 'Analyze for Modernization' to begin" in i.value for i in at.info)


def test_recommendations_empty_state(monkeypatch):
    pipeline = {
        **SUCCESSFUL_PIPELINE,
        "recommendations": [],
    }
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient, "analyze_modernization", lambda self, ws_id, filename: pipeline
    )

    at = _make_app()
    at.run()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    assert any("No recommendations available" in i.value for i in at.info)


def test_chat_with_modernization_context_renders_answer(monkeypatch):
    captured = {}

    def fake_chat(
        self,
        workspace_id,
        query,
        filename=None,
        include_modernization_context=False,
        top_k=5,
    ):
        captured["include_modernization_context"] = include_modernization_context
        captured["filename"] = filename
        return {
            "query": query,
            "answer": "This program reads a customer file.",
            "context": [],
            "error": None,
            "modernization_data": None,
        }

    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws_id, filename: SUCCESSFUL_PIPELINE,
    )
    monkeypatch.setattr(BackendClient, "send_chat_message", fake_chat)

    at = _make_app()
    at.run()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    at.checkbox(key="include_modernization_context").set_value(True).run()
    at.chat_input(key="chat_input").set_value("What does this program do?").run()

    assert not at.exception
    assert captured["include_modernization_context"] is True
    assert captured["filename"] == "MAIN.cbl"
    assert any(
        "reads a customer file" in msg.markdown[0].value
        for msg in at.chat_message
        if msg.markdown
    )


def test_chat_api_failure_shows_safe_error(monkeypatch):
    def raise_error(
        self,
        workspace_id,
        query,
        filename=None,
        include_modernization_context=False,
        top_k=5,
    ):
        raise BackendAPIError(
            "The server encountered an error. Please try again later.", 500
        )

    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws_id, filename: SUCCESSFUL_PIPELINE,
    )
    monkeypatch.setattr(BackendClient, "send_chat_message", raise_error)

    at = _make_app()
    at.run()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()
    at.chat_input(key="chat_input").set_value("hello").run()

    assert not at.exception
    assert any("server encountered an error" in e.value for e in at.error)


def test_empty_workspace_id_cannot_be_submitted():
    at = _make_app()
    at.run()

    at.text_input(key="manual_ws_input").set_value("   ").run()

    assert at.button(key="load_workspace_button").disabled is True
