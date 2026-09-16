"""
Behavioral tests for the Streamlit modernization UI (``app/frontend/app.py``).

Uses :class:`streamlit.testing.v1.AppTest` to drive the real script exactly
as a user would (filling inputs, clicking buttons) and asserts on what is
actually rendered, rather than on internal calls. The backend is mocked at
the :class:`~app.frontend.client.BackendClient` boundary only -- the API
client itself is covered separately in ``test_client.py``.
"""

import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app.frontend.client import BackendAPIError, BackendClient

APP_PATH = str(Path(__file__).parent.parent.parent / "app" / "frontend" / "app.py")

#: mirrors app.py's private _NAV_KEYS -- the sidebar nav buttons that
#: replaced the old `st.radio(key="active_view")` tab bar.
_NAV_KEYS = {
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


def _open_view(at: AppTest, view: str) -> AppTest:
    at.button(key=_NAV_KEYS[view]).click().run()
    return at


@pytest.fixture(autouse=True)
def _default_report_and_java_workspace_stubs(monkeypatch):
    """Overview (the default active_view once a file is selected) now
    lazily fetches the aggregate /modernization/report on open. Give
    every test a safe empty stub instead of a real network call; a test
    that cares about report content sets its own, more specific
    ``monkeypatch.setattr`` in its own body, which -- running after this
    fixture's setup -- wins."""
    monkeypatch.setattr(
        BackendClient, "get_modernization_report", lambda self, ws_id, filename: {}
    )
    monkeypatch.setattr(
        BackendClient, "get_java_workspace", lambda self, ws_id, filename: {}
    )


def _snapshot_and_pop_app_frontend_modules() -> dict:
    """
    Pop `app`, `app.frontend`, and every `app.frontend.*` submodule (client,
    chat_view, java_workspace, ...) out of sys.modules, returning what was
    there so it can be restored afterward.

    Popping only ("app", "app.frontend", "app.frontend.client") -- as this
    used to do -- is not enough: app.py's own module-level imports pull in
    every app.frontend.* view submodule (chat_view, java_workspace, etc.),
    and each of those does its own `from app.frontend.client import
    BackendAPIError`. When a test forces app.py to re-execute with a
    poisoned/missing `app` cache, those submodules get fresh module objects
    with their own fresh BackendAPIError class -- but if only client.py's
    entry gets restored afterward, a view submodule imported during the
    poisoned run keeps referencing the *stale* fresh class forever (Python
    never re-executes an already-cached module), so its
    `except BackendAPIError` stops matching exceptions raised by the
    restored, real client module in every later test. Popping/restoring the
    whole app.frontend.* subtree keeps every submodule's BackendAPIError
    reference consistent with the one tests raise against.
    """
    names = [
        n
        for n in sys.modules
        if n == "app" or n == "app.frontend" or n.startswith("app.frontend.")
    ]
    return {n: sys.modules.pop(n) for n in names}


def _restore_app_frontend_modules(snapshot: dict) -> None:
    for n in [
        n
        for n in sys.modules
        if n == "app" or n == "app.frontend" or n.startswith("app.frontend.")
    ]:
        if n not in snapshot:
            del sys.modules[n]
    sys.modules.update(snapshot)


def test_entrypoint_survives_streamlit_sys_path_bootstrap():
    """
    Regression test for a real startup failure: `streamlit run app/frontend/app.py`
    inserts the script's own directory (app/frontend) at the front of sys.path
    (streamlit.web.bootstrap._fix_sys_path). Since the entrypoint is itself
    named app.py, Python then resolves the top-level `app` package to that
    very file instead of the real app/ package at the project root, and
    `from app.frontend.client import ...` fails with:
        ModuleNotFoundError: No module named 'app.frontend'; 'app' is not a package

    This reproduces the real Streamlit bootstrap ordering precisely (not a
    guess at the mechanism -- the actual streamlit function), with the
    project root explicitly made absent from sys.path first (worst case,
    stronger than merely "not first"), so a regression here fails with the
    same traceback a user would see.
    """
    from streamlit.web.bootstrap import _fix_sys_path

    project_root = str(Path(APP_PATH).resolve().parents[2])
    script_dir = str(Path(APP_PATH).resolve().parent)

    original_sys_path = list(sys.path)
    app_modules_snapshot = _snapshot_and_pop_app_frontend_modules()
    try:
        # Simulate the worst case explicitly: the project root is entirely
        # absent from sys.path (not merely present-but-later), and
        # app/frontend is not yet at the front either -- _fix_sys_path is
        # what puts it there, exactly as the real bootstrap does.
        sys.path[:] = [p for p in sys.path if p not in (project_root, "", script_dir)]
        assert project_root not in sys.path
        assert script_dir not in sys.path

        _fix_sys_path(APP_PATH)
        assert (
            sys.path[0] == script_dir
        ), "test setup did not reproduce streamlit's sys.path bootstrap"
        assert (
            project_root not in sys.path[:1]
        ), "test setup should not already have the project root fixing the bug"

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=20)

        assert not list(at.exception), [str(e.value) for e in at.exception]

        # app must resolve to the real top-level package (app/__init__.py),
        # not to this entry script (app/frontend/app.py) being mistaken for it.
        resolved_app = sys.modules.get("app")
        assert resolved_app is not None, "app was not imported during script execution"
        assert hasattr(resolved_app, "__path__"), (
            "app resolved to a plain module, not the app/ package -- "
            f"__file__={getattr(resolved_app, '__file__', None)!r}"
        )
        assert Path(resolved_app.__file__).name == "__init__.py"
        assert Path(resolved_app.__file__).parent == Path(project_root) / "app"

        # app.frontend.client must have actually imported successfully.
        client_module = sys.modules.get("app.frontend.client")
        assert client_module is not None
        assert hasattr(client_module, "BackendClient")
        assert hasattr(client_module, "BackendAPIError")
    finally:
        sys.path[:] = original_sys_path
        _restore_app_frontend_modules(app_modules_snapshot)
        # st.cache_resource is a process-wide cache that outlives this
        # AppTest run. It may have cached a BackendClient instance built
        # from the module state that existed during this test (before the
        # restoration above), which would otherwise leak into later tests
        # and make their BackendClient monkeypatches silently not apply.
        st.cache_resource.clear()


def test_entrypoint_recovers_from_poisoned_app_module_cache():
    """
    Regression test for a second, independent failure mode: if the
    top-level `app` name was already resolved to something other than the
    real app/ package -- e.g. this very script, mistaken for it while
    app/frontend sat ahead of the project root on sys.path -- Python caches
    that in sys.modules and would keep reusing it even after sys.path is
    corrected, since `import app` checks sys.modules first. The entrypoint
    must detect and discard a non-package `app` cache entry so the import
    re-resolves fresh.
    """
    import types

    original_sys_path = list(sys.path)
    app_modules_snapshot = _snapshot_and_pop_app_frontend_modules()
    try:
        # Poison the cache exactly the way the real bug would: `app` bound
        # to a plain module (no __path__), standing in for app.py itself.
        fake_app_module = types.ModuleType("app")
        assert not hasattr(fake_app_module, "__path__")
        sys.modules["app"] = fake_app_module

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=20)

        assert not list(at.exception), [str(e.value) for e in at.exception]

        resolved_app = sys.modules.get("app")
        assert (
            resolved_app is not fake_app_module
        ), "the poisoned app module cache entry was never replaced"
        assert hasattr(resolved_app, "__path__")
    finally:
        sys.path[:] = original_sys_path
        _restore_app_frontend_modules(app_modules_snapshot)
        # See the matching comment in test_entrypoint_survives_streamlit_sys_path_bootstrap.
        st.cache_resource.clear()


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


def _make_app(*, enter_workspace: bool = True) -> AppTest:
    """Build and run the app. By default also navigates through the new
    landing -> entry gate into the workspace stage (as "Guest"), since
    every pre-existing test below exercises workspace/sidebar behavior,
    not the landing/entry screens themselves (those have their own
    dedicated tests). Pass enter_workspace=False to stop at landing.
    """
    at = AppTest.from_file(APP_PATH)
    at.default_timeout = 20
    at.run()
    if enter_workspace:
        at.button(key="landing_enter_platform").click().run()
        at.button(key="entry_guest").click().run()
    return at


def _load_workspace(at: AppTest, workspace_id: str = "ws-1") -> AppTest:
    at.text_input(key="manual_ws_input").set_value(workspace_id)
    at.button(key="load_workspace_button").click().run()
    return at


def test_initial_state_prompts_for_selection():
    at = _make_app()

    assert not at.exception
    assert any("select a workspace and file" in info.value for info in at.info)


def test_load_workspace_lists_inventory_files(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )

    at = _make_app()
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
    _load_workspace(at, "missing-ws")

    assert not at.exception
    assert any("requested resource was not found" in e.value for e in at.error)
    assert not any("Traceback" in e.value for e in at.error)


def test_successful_analysis_renders_pipeline_and_topology(monkeypatch):
    """Overview's Critical Topology panel renders the real, already-fetched
    control-flow graph -- never a fabricated relationship. (Scores/Flow-as-
    tables/Recommendations were dropped from Overview in the Stitch
    redesign in favor of the compact stat row + pipeline stepper + Key
    Findings + Critical Topology composition -- see report_result-driven
    tests below for those.)"""
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws_id, filename: SUCCESSFUL_PIPELINE,
    )

    at = _make_app()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    assert not at.exception
    full_text = " ".join(m.value for m in at.markdown)
    assert "MAIN" in full_text
    assert "SUBRTN" in full_text
    assert any("2 node(s), 1 edge(s)" in c.value for c in at.caption)


def test_insufficient_data_topology_shows_honest_empty_state(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws_id, filename: INSUFFICIENT_DATA_PIPELINE,
    )

    at = _make_app()
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    assert not at.exception
    assert any("Empty flow generated" in i.value for i in at.info)
    assert (
        "READY FOR MODERNIZATION" not in " ".join(m.value for m in at.markdown).upper()
    )


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
    _load_workspace(at)
    at.button(key="analyze_button").click().run()

    assert not at.exception
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
    _load_workspace(at)
    at.button(key="analyze_button").click().run()
    full_text = " ".join(m.value for m in at.markdown)
    assert "SUBRTN" in full_text

    at.selectbox(key="file_select").set_value("UTIL.cbl").run()

    assert any(
        "Click 'Analyze for Modernization' in the sidebar to see topology" in i.value
        for i in at.info
    )


def test_switching_file_clears_stale_chat_history(monkeypatch):
    """
    Regression: chat messages about a previously selected file must not
    remain displayed as if they were part of an ongoing conversation about
    a newly selected file. Modernization Chat is now its own sidebar view
    (no longer nested inside Overview), and no longer depends on the
    "Analyze for Modernization" pipeline having run first.
    """
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_TWO_FILES
    )
    monkeypatch.setattr(
        BackendClient,
        "send_chat_message",
        lambda self, workspace_id, query, filename=None, include_modernization_context=False, top_k=5: {
            "query": query,
            "answer": "This is about MAIN.cbl.",
            "context": [],
            "error": None,
            "modernization_data": None,
        },
    )

    at = _make_app()
    _load_workspace(at)
    _open_view(at, "Modernization Chat")
    at.chat_input(key="chat_input").set_value("What does this do?").run()

    assert len(at.session_state["messages"]) == 2

    at.selectbox(key="file_select").set_value("UTIL.cbl").run()

    assert at.session_state["messages"] == []


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
    monkeypatch.setattr(BackendClient, "send_chat_message", fake_chat)

    at = _make_app()
    _load_workspace(at)
    _open_view(at, "Modernization Chat")

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
    monkeypatch.setattr(BackendClient, "send_chat_message", raise_error)

    at = _make_app()
    _load_workspace(at)
    _open_view(at, "Modernization Chat")
    at.chat_input(key="chat_input").set_value("hello").run()

    assert not at.exception
    assert any("server encountered an error" in e.value for e in at.error)


def test_empty_workspace_id_cannot_be_submitted():
    at = _make_app()

    at.text_input(key="manual_ws_input").set_value("   ").run()

    assert at.button(key="load_workspace_button").disabled is True
