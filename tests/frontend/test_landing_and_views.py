"""
Phase 12 -- behavioral tests for the landing/entry gate, the AI Core
diagram wired into the workspace, and the new Business Rules /
Dependencies / honest-stub views.

Uses the same :class:`streamlit.testing.v1.AppTest` pattern as
``test_app.py`` -- the real script, mocked only at the
:class:`~app.frontend.client.BackendClient` boundary.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.frontend.client import BackendClient

APP_PATH = str(Path(__file__).parent.parent.parent / "app" / "frontend" / "app.py")

INVENTORY_ONE_FILE = {
    "workspace_id": "ws-1",
    "files": [{"filename": "MAIN.cbl", "extension": ".cbl", "file_type": "COBOL"}],
    "total_files": 1,
}

INTELLIGENCE_RESULT = {
    "business_rules": [
        {
            "rule_id": "BR-001",
            "category": "ELIGIBILITY",
            "description": "Customer must be 18 or older",
            "condition": "WS-AGE >= 18",
            "actions": [
                {
                    "kind": "MOVE",
                    "target": "WS-RESULT",
                    "sources": [],
                    "literals": ["APPROVED"],
                    "raw": "MOVE 'APPROVED' TO WS-RESULT",
                    "source_location": None,
                }
            ],
            "variables": {
                "reads": ["WS-AGE"],
                "writes": ["WS-RESULT"],
                "conditions": [],
            },
            "dependencies": [],
            "source_locations": [
                {
                    "type": "Position",
                    "line": 19,
                    "column": 1,
                    "offset": 0,
                    "filename": "MAIN.cbl",
                }
            ],
            "paragraph": "CHECK-ELIGIBILITY",
            "section": None,
            "confidence": 0.95,
            "evidence": ["WS-AGE >= 18 at line 19"],
        }
    ],
    "risks": [
        {
            "risk_id": "RISK-001",
            "category": "COMPLEXITY",
            "severity": "MEDIUM",
            "title": "Deeply nested conditionals",
            "explanation": "CHECK-ELIGIBILITY has 4 levels of nested IF.",
            "evidence": [],
            "source_locations": [],
            "affected_components": ["CHECK-ELIGIBILITY"],
            "confidence": 0.8,
            "recommended_mitigation": "Extract nested conditions into named predicates.",
            "occurrence_count": 1,
        }
    ],
    "strategies": [
        {
            "recommendation_id": "STRAT-001",
            "strategy": "REWRITE",
            "is_primary": True,
            "rationale": "Business logic is well-isolated and testable.",
            "evidence": [],
            "referenced_risk_ids": ["RISK-001"],
            "prerequisites": [],
            "confidence": 0.7,
        }
    ],
}

ANALYSIS_RESULT = {
    "success": True,
    "status": "SUCCESS",
    "analysis_id": "an-1",
    "workspace_id": "ws-1",
    "filename": "MAIN.cbl",
    "source_metadata": {"extension": ".cbl", "size_bytes": 10, "sha256": "abc"},
    "java_source": "public class Main {}",
    "ast": None,
    "ir": None,
    "diagnostics": [],
    "syntax_diagnostics": [],
    "syntax_diagnostics_summary": [],
    "coverage": None,
    "coverage_report": None,
    "dependencies": [
        {"type": "CALL", "target": "SUBRTN", "source_location": None},
        {"type": "VARIABLE_READ", "target": "WS-AGE", "source_location": None},
    ],
    "dependency_summary": None,
    "dependency_graph": {
        "nodes": [{"identifier": "MAIN"}, {"identifier": "SUBRTN"}],
        "edges": [
            {
                "source": "MAIN",
                "target": "SUBRTN",
                "dependency_type": "CALL",
                "source_location": None,
            }
        ],
    },
    "business_rules": [],
    "error": None,
    "ai_analysis": None,
}


def _make_app() -> AppTest:
    at = AppTest.from_file(APP_PATH)
    at.default_timeout = 20
    at.run()
    return at


def _enter_workspace(at: AppTest, *, name: str | None = None) -> AppTest:
    at.button(key="landing_enter_platform").click().run()
    if name:
        at.text_input(key="entry_name").set_value(name)
        at.button(key="entry_sign_in").click().run()
    else:
        at.button(key="entry_guest").click().run()
    return at


def _visible_text(at: AppTest) -> str:
    """Joined markdown content, excluding pure `<style>` blocks -- so
    assertions about rendered wording are never tripped up by CSS class
    names (e.g. `.mf-status--pass`, `.mf-core-verified`) that happen to
    contain the same substrings."""
    return " ".join(
        m.value for m in at.markdown if not m.value.strip().startswith("<style>")
    )


def _load_and_select(at: AppTest, filename: str = "MAIN.cbl") -> AppTest:
    at.text_input(key="manual_ws_input").set_value("ws-1")
    at.button(key="load_workspace_button").click().run()
    at.selectbox(key="file_select").set_value(filename).run()
    return at


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------


def test_landing_renders_first_with_enter_platform_cta():
    at = _make_app()

    assert not at.exception
    assert at.button(key="landing_enter_platform") is not None
    # workspace-only widgets must not exist yet -- the gate is real
    assert not any(b.key == "load_workspace_button" for b in at.button)


def test_enter_platform_navigates_to_entry_screen():
    at = _make_app()
    at.button(key="landing_enter_platform").click().run()

    assert not at.exception
    assert at.button(key="entry_guest") is not None
    assert at.session_state["stage"] == "entry"


def test_login_link_also_navigates_to_entry_screen():
    at = _make_app()
    at.button(key="landing_login_link").click().run()

    assert not at.exception
    assert at.session_state["stage"] == "entry"


def test_watch_intro_marks_intro_seen_without_leaving_landing():
    at = _make_app()
    assert at.session_state["intro_seen"] is False

    at.button(key="landing_watch_intro").click().run()

    assert at.session_state["stage"] == "landing"
    assert at.session_state["intro_seen"] is True


def test_entry_screen_never_claims_real_authentication():
    at = _make_app()
    at.button(key="landing_enter_platform").click().run()

    full_text = _visible_text(at)
    assert "no account is created" in full_text
    assert "no credentials are verified" in full_text


def test_guest_entry_reaches_workspace_and_greets_guest():
    at = _make_app()
    _enter_workspace(at)

    assert not at.exception
    assert at.session_state["stage"] == "workspace"
    assert at.session_state["engineer_name"] == "Guest"
    assert any("Guest" in c.value for c in at.caption)


def test_named_sign_in_personalizes_the_greeting():
    at = _make_app()
    _enter_workspace(at, name="Alex")

    assert at.session_state["engineer_name"] == "Alex"
    assert any("Alex" in c.value for c in at.caption)


# ---------------------------------------------------------------------------
# AI Core diagram + subsystem navigation, inside the workspace
# ---------------------------------------------------------------------------


def test_idle_ai_core_state_before_any_workspace_selected():
    at = _make_app()
    _enter_workspace(at)

    assert "AWAITING ANALYSIS" in _visible_text(at)


def test_subsystem_button_switches_the_active_view(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_ONE_FILE
    )

    at = _make_app()
    _enter_workspace(at)
    _load_and_select(at)

    assert at.radio(key="active_view").value == "Overview"
    at.button(key="subsystem_data").click().run()
    assert at.radio(key="active_view").value == "Dependencies"


# ---------------------------------------------------------------------------
# Business Rules (#134) -- real data from the previously-unused
# /modernization/intelligence endpoint
# ---------------------------------------------------------------------------


def test_business_rules_view_renders_real_rule_data(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_ONE_FILE
    )
    monkeypatch.setattr(
        BackendClient,
        "get_modernization_intelligence",
        lambda self, ws_id, filename: INTELLIGENCE_RESULT,
    )

    at = _make_app()
    _enter_workspace(at)
    _load_and_select(at)
    at.radio(key="active_view").set_value("Business Rules").run()

    assert not at.exception
    full_text = _visible_text(at)
    assert "BR-001" in full_text
    assert "Customer must be 18 or older" in full_text


def test_business_rules_view_empty_state_without_fabricating(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_ONE_FILE
    )
    monkeypatch.setattr(
        BackendClient,
        "get_modernization_intelligence",
        lambda self, ws_id, filename: {
            "business_rules": [],
            "risks": [],
            "strategies": [],
        },
    )

    at = _make_app()
    _enter_workspace(at)
    _load_and_select(at)
    at.radio(key="active_view").set_value("Business Rules").run()

    assert not at.exception
    assert any("No business rules" in i.value for i in at.info)


# ---------------------------------------------------------------------------
# Dependencies (#135) -- real data from the previously-unused /analyze endpoint
# ---------------------------------------------------------------------------


def test_dependencies_view_renders_real_graph_and_flat_list(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_ONE_FILE
    )
    monkeypatch.setattr(
        BackendClient, "get_analysis", lambda self, ws_id, filename: ANALYSIS_RESULT
    )

    at = _make_app()
    _enter_workspace(at)
    _load_and_select(at)
    at.radio(key="active_view").set_value("Dependencies").run()

    assert not at.exception
    assert any("SUBRTN" in c.value or "resolved" in c.value for c in at.caption)
    rows = at.dataframe[0].value
    assert "CALL" in list(rows["Type"])
    assert "VARIABLE_READ" in list(rows["Type"])


def test_dependencies_filter_by_type(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_ONE_FILE
    )
    monkeypatch.setattr(
        BackendClient, "get_analysis", lambda self, ws_id, filename: ANALYSIS_RESULT
    )

    at = _make_app()
    _enter_workspace(at)
    _load_and_select(at)
    at.radio(key="active_view").set_value("Dependencies").run()
    at.selectbox(key="dep_filter").set_value("Variable Reads").run()

    rows = at.dataframe[0].value
    assert list(rows["Type"]) == ["VARIABLE_READ"]


# ---------------------------------------------------------------------------
# Honest "not yet available" stubs -- never fabricated data, never a fake
# success/readiness claim
# ---------------------------------------------------------------------------


def test_architecture_view_is_an_honest_stub_not_fabricated(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_ONE_FILE
    )

    at = _make_app()
    _enter_workspace(at)
    _load_and_select(at)
    at.radio(key="active_view").set_value("Architecture").run()

    assert not at.exception
    full_text = _visible_text(at).upper()
    assert "NOT AVAILABLE" in full_text
    assert "READY FOR MODERNIZATION" not in full_text
    assert "VERIFIED" not in full_text


def test_validation_center_stub_never_claims_readiness(monkeypatch):
    monkeypatch.setattr(
        BackendClient, "get_inventory", lambda self, ws_id: INVENTORY_ONE_FILE
    )

    at = _make_app()
    _enter_workspace(at)
    _load_and_select(at)
    at.radio(key="active_view").set_value("Validation Center").run()

    assert not at.exception
    full_text = _visible_text(at).upper()
    assert "NOT AVAILABLE" in full_text
    assert "READY FOR MODERNIZATION" not in full_text
    # no fake green "PASS" status pill anywhere on this view -- the word
    # "PASS" may still appear in explanatory prose (e.g. "a PASS/FAIL/
    # INCONCLUSIVE verdict cannot be shown yet"), which is honest, not a claim.
    assert 'mf-status--pass"' not in "".join(m.value for m in at.markdown)
