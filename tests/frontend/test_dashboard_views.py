"""
Tests for the dashboard's view helpers and the redesigned shell behaviours.

The pure helpers (overview, portfolio, JCL, report) are tested directly; the
shell and chat behaviours are driven through the real app with
:class:`streamlit.testing.v1.AppTest`, mocked at the ``BackendClient``
boundary like the rest of the frontend tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
from streamlit.testing.v1 import AppTest

from app.frontend.client import BackendAPIError, BackendClient
from app.frontend.jcl_view import diagnostic_rows, is_jcl, step_rows
from app.frontend.overview_view import (
    kpi_items,
    overall_callout,
    pipeline_steps_for,
    severity_rows,
)
from app.frontend.portfolio_view import format_bytes, type_rows
from app.frontend.report_view import report_markdown

APP_PATH = str(Path(__file__).parent.parent.parent / "app" / "frontend" / "app.py")

REPORT: Dict[str, Any] = {
    "filename": "MAIN.cbl",
    "source_id": "src-1",
    "analysis_success": True,
    "paragraphs": ["MAIN-PARA", "CALC"],
    "business_rules": [{"rule_id": "BR-1"}, {"rule_id": "BR-2"}],
    "dependencies": [{"type": "PERFORM"}],
    "risks": [
        {
            "title": "Shared WS-STATUS",
            "severity": "HIGH",
            "explanation": "Written twice.",
        },
        {"title": "Shared WS-X", "severity": "MEDIUM", "explanation": "Also shared."},
        {"title": "Shared WS-Y", "severity": "MEDIUM", "explanation": "Also shared."},
    ],
    "strategy": {"primary": {"strategy": "PHASED_MIGRATION", "rationale": "Large."}},
    "architecture": {"components": [{"name": "A"}, {"name": "B"}]},
    "project": {"files": {"src/A.java": "x", "pom.xml": "y"}},
    "compilation": {"success": True},
    "coverage": {"overall": 0.5},
    "confidence": {"score": 0.9},
    "validation_stages": [
        {"stage": "Parser", "status": "PASS", "summary": "ok"},
        {"stage": "Tests", "status": "INCONCLUSIVE", "summary": "not run"},
    ],
    "overall_status": "INCONCLUSIVE",
    "unresolved_issues": ["Tests: not run"],
}


# ----------------------------------------------------------------- overview


@pytest.mark.parametrize(
    ("status", "tone", "word"),
    [
        ("PASS", "success", "ready for modernization"),
        ("FAIL", "error", "Not ready"),
        ("INCONCLUSIVE", "warning", "Not yet verified"),
        ("NOT_AVAILABLE", "neutral", "not available"),
    ],
)
def test_overall_callout_matches_the_backend_status(
    status: str, tone: str, word: str
) -> None:
    html = overall_callout(status)
    assert f"ds-callout--{tone}" in html
    assert word.lower() in html.lower()


def test_ready_is_claimed_only_for_pass() -> None:
    for status in ("FAIL", "INCONCLUSIVE", "NOT_AVAILABLE", "UNKNOWN"):
        assert "ready for modernization" not in overall_callout(status).lower()


def test_no_status_means_no_banner() -> None:
    assert overall_callout(None) == ""


def test_pipeline_steps_are_judged_independently() -> None:
    steps = {s["name"]: s for s in pipeline_steps_for(REPORT)}
    assert steps["Analyze"]["state"] == "done"
    assert steps["Transform"]["state"] == "done"
    assert steps["Validate"]["state"] == "partial"
    assert steps["Transform"]["metric"] == "1 Java files"
    assert steps["Validate"]["metric"] == "1 of 2 stages pass"


def test_a_failed_parse_does_not_hide_downstream_results() -> None:
    steps = {
        s["name"]: s for s in pipeline_steps_for({**REPORT, "analysis_success": False})
    }
    assert steps["Analyze"]["state"] == "fail"
    assert steps["Understand"]["state"] == "done"
    assert steps["Transform"]["state"] == "done"


def test_pipeline_with_nothing_is_pending_not_done() -> None:
    steps = pipeline_steps_for({"analysis_success": False})
    assert [s["state"] for s in steps] == ["fail", "pending", "pending", "pending"]


def test_kpis_show_a_dash_for_missing_figures_never_zero() -> None:
    items = {
        i["label"]: i for i in kpi_items({"business_rules": [], "dependencies": []})
    }
    assert items["Business rules"]["value"] == "0"
    assert items["Components"]["value"] == "—"
    assert items["Java files"]["value"] == "—"
    assert items["Analysis coverage"]["value"] == "—"
    assert "Confidence" not in items


def test_kpi_ratios_come_from_the_report() -> None:
    items = {i["label"]: i for i in kpi_items(REPORT)}
    assert items["Analysis coverage"]["ratio"] == 0.5
    assert items["Confidence"]["value"] == "90%"
    assert items["Components"]["value"] == "2"


def test_severity_rows_are_most_severe_first() -> None:
    assert severity_rows(REPORT["risks"]) == [("High", 1), ("Medium", 2)]
    assert severity_rows([]) == []


# ---------------------------------------------------------------- portfolio


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1024, "1.0 KB"),
        (4000, "3.9 KB"),
        (5 * 1024**2, "5.0 MB"),
    ],
)
def test_format_bytes(size: int, text: str) -> None:
    assert format_bytes(size) == text


def test_type_rows_count_from_the_inventory() -> None:
    files = [{"file_type": "COBOL"}, {"file_type": "JCL"}, {"file_type": "COBOL"}, {}]
    assert type_rows(files) == [("COBOL", 2), ("JCL", 1), ("unknown", 1)]


# --------------------------------------------------------------------- JCL


def test_is_jcl() -> None:
    assert is_jcl("RUN.JCL") and is_jcl("a.jcl") and is_jcl("X.proc")
    assert not is_jcl("MAIN.cbl") and not is_jcl(None) and not is_jcl("")


def test_step_rows_show_program_or_procedure() -> None:
    program = {
        "steps": [
            {"name": "S1", "program": "SORT", "dd_statements": [{}, {}], "line": 3},
            {"name": "S2", "procedure": "CATLG", "dd_statements": [], "line": 9},
            {"name": "S3", "dd_statements": [], "line": 12},
        ]
    }
    assert step_rows(program) == [
        {"step": "S1", "runs": "SORT", "DD statements": 2, "line": 3},
        {"step": "S2", "runs": "PROC CATLG", "DD statements": 0, "line": 9},
        {"step": "S3", "runs": "—", "DD statements": 0, "line": 12},
    ]
    assert step_rows({}) == []


def test_diagnostic_rows_keep_parser_order() -> None:
    rows = diagnostic_rows(
        [
            {"severity": "WARNING", "code": "B", "line": 9, "message": "second"},
            {"severity": "ERROR", "code": "A", "line": 2, "message": "first"},
        ]
    )
    assert [r["code"] for r in rows] == ["B", "A"]


# ------------------------------------------------------------------- report


def test_report_markdown_contains_only_report_facts() -> None:
    md = report_markdown(REPORT)
    assert md.startswith("# Modernization assessment: MAIN.cbl")
    assert "Overall status: **INCONCLUSIVE**" in md
    assert "Analysis coverage: 50%" in md
    assert "**Shared WS-STATUS** (HIGH): Written twice." in md
    assert "PHASED_MIGRATION: Large." in md
    assert "- Tests: **INCONCLUSIVE**. not run" in md
    assert "- Tests: not run" in md


def test_report_markdown_marks_missing_data_unavailable() -> None:
    md = report_markdown(
        {
            "filename": "X.cbl",
            "overall_status": "NOT_AVAILABLE",
            "paragraphs": [],
            "business_rules": None,
            "dependencies": None,
            "risks": None,
            "validation_stages": [],
            "unresolved_issues": [],
        }
    )
    assert "Business rules: unavailable" in md
    assert "Analysis coverage: unavailable" in md
    assert "Not available." in md
    assert "Not run." in md


# ------------------------------------------------------------ app behaviour

INVENTORY = {
    "workspace_id": "ws-1",
    "files": [
        {
            "filename": "MAIN.cbl",
            "extension": ".cbl",
            "file_type": "COBOL",
            "size_bytes": 2048,
        },
        {
            "filename": "RUN.jcl",
            "extension": ".jcl",
            "file_type": "JCL",
            "size_bytes": 100,
        },
    ],
    "total_files": 2,
}


@pytest.fixture(autouse=True)
def _backend(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(self: BackendClient, *args: Any, **kwargs: Any) -> Any:
        raise BackendAPIError("Backend unavailable in tests.", 503)

    # anything a test does not stub fails safely, never reaching a real server
    monkeypatch.setattr(BackendClient, "_request", unreachable)
    monkeypatch.setattr(BackendClient, "_request_text", unreachable)
    monkeypatch.setattr(BackendClient, "get_inventory", lambda self, ws: INVENTORY)
    monkeypatch.setattr(
        BackendClient, "get_modernization_report", lambda self, ws, f: REPORT
    )
    monkeypatch.setattr(
        BackendClient,
        "analyze_modernization",
        lambda self, ws, f: {"flow": {"nodes": [], "edges": []}},
    )
    monkeypatch.setattr(BackendClient, "index_for_chat", lambda self, ws, f: {})
    monkeypatch.setattr(
        BackendClient,
        "get_summary",
        lambda self, ws: {"total_files": 2, "total_size_bytes": 2148, "by_type": []},
    )
    monkeypatch.setattr(BackendClient, "get_health", lambda self: {"status": "healthy"})


def _open(view_key: str | None = None) -> AppTest:
    at = AppTest.from_file(APP_PATH)
    at.default_timeout = 20
    at.run()
    at.button(key="landing_enter_platform").click().run()
    at.button(key="entry_guest").click().run()
    at.text_input(key="manual_ws_input").set_value("ws-1").run()
    at.button(key="load_workspace_button").click().run()
    if view_key:
        at.button(key=view_key).click().run()
    return at


def _text(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_overview_is_the_default_and_shows_the_honest_headline() -> None:
    at = _open()
    assert not at.exception
    assert at.session_state["active_view"] == "Overview"
    text = _text(at)
    assert "Not yet verified" in text
    assert "ready for modernization" not in text.lower()


def test_every_nav_view_opens_without_error() -> None:
    from app.frontend.shell import NAV_KEYS

    at = _open()
    for view, key in NAV_KEYS.items():
        at.button(key=key).click().run()
        assert not at.exception, view
        assert at.session_state["active_view"] == view


def test_portfolio_lists_the_workspace_without_needing_analysis() -> None:
    at = _open("nav_portfolio")
    assert not at.exception
    text = _text(at)
    assert "Portfolio" in text
    assert "2.1 KB" in text


def test_jcl_view_says_so_for_a_cobol_file() -> None:
    at = _open("nav_jcl")
    assert not at.exception
    assert "This is not a JCL file" in _text(at)


def test_jcl_view_renders_a_parsed_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        BackendClient,
        "analyze_jcl",
        lambda self, ws, f: {
            "success": True,
            "program": {
                "job": {"name": "NIGHTLY", "parameters": [], "line": 1},
                "steps": [
                    {"name": "S1", "program": "SORT", "dd_statements": [], "line": 2}
                ],
                "unsupported": [],
            },
            "diagnostics": [],
            "error": None,
        },
    )
    at = _open()
    at.selectbox(key="file_select").set_value("RUN.jcl").run()
    at.button(key="nav_jcl").click().run()
    assert not at.exception
    assert "NIGHTLY" in _text(at)


def test_chat_opens_with_suggestions_and_no_fake_messages() -> None:
    at = _open("nav_chat")
    assert not at.exception
    assert len(at.chat_message) == 0
    assert "What would you like to know about" in _text(at)
    labels = [b.label for b in at.button if str(b.key).startswith("suggest_")]
    assert len(labels) == 4


def test_a_suggestion_asks_that_exact_question(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def fake_chat(
        self: BackendClient, workspace_id: str, query: str, **kwargs: Any
    ) -> Dict[str, Any]:
        asked.append(query)
        return {"query": query, "answer": "An answer.", "context": [], "error": None}

    monkeypatch.setattr(BackendClient, "send_chat_message", fake_chat)
    at = _open("nav_chat")
    at.button(key="suggest_1").click().run()
    assert not at.exception
    assert asked == ["List the business rules in this program"]
    assert any(
        "An answer." in m.markdown[0].value for m in at.chat_message if m.markdown
    )


def test_new_chat_clears_the_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        BackendClient,
        "send_chat_message",
        lambda self, workspace_id, query, **kw: {
            "answer": "A.",
            "context": [],
            "error": None,
        },
    )
    at = _open("nav_chat")
    at.chat_input(key="chat_input").set_value("hello").run()
    assert at.session_state["messages"]
    at.button(key="new_chat").click().run()
    assert at.session_state["messages"] == []
    assert not at.exception


def test_a_chat_error_is_a_labelled_status_not_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        BackendClient,
        "send_chat_message",
        lambda self, workspace_id, query, **kw: {
            "answer": "",
            "context": [],
            "error": "No AI provider is configured.",
            "error_code": "LLM_PROVIDER_NOT_CONFIGURED",
        },
    )
    at = _open("nav_chat")
    at.chat_input(key="chat_input").set_value("hello").run()
    assert not at.exception
    assert "No AI provider is configured." in _text(at)
    assert all(m["role"] == "user" for m in at.session_state["messages"])


def test_logout_returns_to_the_entry_screen() -> None:
    at = _open()
    at.button(key="logout_button").click().run()
    assert at.session_state["stage"] == "entry"
