"""
API tests for the Validation Center endpoint.

The central rule under test: PASS only when genuinely verified, and
INCONCLUSIVE/NOT_AVAILABLE are never silently upgraded to PASS.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.ingestion.workspace import WorkspaceManager
from app.main import app

client = TestClient(app)

_IF_ELSE = Path("tests/golden/if_else.cbl").read_text(encoding="utf-8")
_ELIGIBILITY = Path("tests/fixtures/phase4/eligibility_rules.cbl").read_text(
    encoding="utf-8"
)


def _mock_workspace(monkeypatch, tmp_path) -> None:
    def mock_get(self, ws_id):
        from app.ingestion.models import WorkspaceRecord

        return WorkspaceRecord(workspace_id=ws_id, path=str(tmp_path))

    monkeypatch.setattr(WorkspaceManager, "get", mock_get)


def _stage(body, name):
    return next(s for s in body["stages"] if s["stage"] == name)


def test_validation_happy_path_reports_all_twelve_stages(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 200
    body = resp.json()
    stage_names = {s["stage"] for s in body["stages"]}
    assert stage_names == {
        "Parser",
        "Analysis",
        "Coverage",
        "Confidence",
        "Java Generation",
        "Compilation",
        "Tests",
        "COBOL Tests",
        "Behavioral Equivalence",
        "Risks",
        "Unsupported Syntax",
        "Self Repair",
    }
    for s in body["stages"]:
        assert s["status"] in {"PASS", "FAIL", "INCONCLUSIVE", "NOT_AVAILABLE"}


def test_validation_path_traversal_is_rejected(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "../../etc/passwd"},
    )
    assert resp.status_code == 403


def test_validation_missing_file_is_404(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "missing.cbl"},
    )
    assert resp.status_code == 404


def test_validation_is_deterministic(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")
    url = f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation"

    r1 = client.post(url, json={"filename": "if_else.cbl"})
    r2 = client.post(url, json={"filename": "if_else.cbl"})
    assert r1.json() == r2.json()


def test_validation_behavioral_equivalence_is_inconclusive_without_cobol_runtime(
    monkeypatch, tmp_path
):
    """Central honesty rule: no GnuCOBOL in this environment => behavioral
    equivalence MUST be INCONCLUSIVE, never a fabricated PASS."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    assert _stage(body, "Behavioral Equivalence")["status"] == "INCONCLUSIVE"
    assert _stage(body, "COBOL Tests")["status"] == "NOT_AVAILABLE"
    # and therefore the overall status can never claim readiness either
    assert body["overall_status"] != "PASS"


def test_validation_self_repair_is_not_available_without_a_provider(
    monkeypatch, tmp_path
):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    repair = _stage(body, "Self Repair")
    assert repair["status"] == "NOT_AVAILABLE"
    assert "provider" in repair["summary"].lower()


def test_validation_compilation_fail_state(monkeypatch, tmp_path):
    """A genuinely broken generated project must report FAIL, not PASS."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    from app.java_modernization.generation import generate_project as real_generate

    def break_it(bundle, architecture):
        project = real_generate(bundle, architecture)
        main = f"src/{project.main_class}.java"
        broken_files = dict(project.files)
        broken_files[main] = broken_files[main].replace(
            "System.out.println", "System.out.printnl"
        )
        return project.model_copy(update={"files": broken_files})

    monkeypatch.setattr("app.dataset.modernization_bundle.generate_project", break_it)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    assert _stage(body, "Compilation")["status"] == "FAIL"
    assert body["overall_status"] == "FAIL"


def test_validation_unresolved_analysis_never_becomes_a_downstream_pass(
    monkeypatch, tmp_path
):
    """When architecture cannot be derived, every downstream stage that
    depends on it must be NOT_AVAILABLE, never PASS."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    from app.java_modernization.errors import ArchitectureError

    def boom(bundle):
        raise ArchitectureError("no AST")

    monkeypatch.setattr("app.dataset.modernization_bundle.build_architecture", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    assert _stage(body, "Java Generation")["status"] == "NOT_AVAILABLE"
    assert _stage(body, "Compilation")["status"] == "NOT_AVAILABLE"
    assert _stage(body, "Tests")["status"] == "NOT_AVAILABLE"
    assert _stage(body, "Behavioral Equivalence")["status"] == "NOT_AVAILABLE"
    assert body["overall_status"] in {"FAIL", "INCONCLUSIVE"}
    assert body["overall_status"] != "PASS"


def test_validation_risks_are_inconclusive_not_hidden(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "if_else.cbl"},
    )
    body = resp.json()
    risks = _stage(body, "Risks")
    assert risks["status"] in {"PASS", "INCONCLUSIVE"}
    if risks["status"] == "INCONCLUSIVE":
        assert risks["details"]["risk_ids"]


def test_validation_unsupported_stubs_are_reported_honestly(monkeypatch, tmp_path):
    """eligibility_rules.cbl generates BE009 (unimplemented) stubs --
    behavioral equivalence must stay INCONCLUSIVE, never PASS."""
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "elig.cbl").write_text(_ELIGIBILITY, encoding="utf-8")

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "elig.cbl"},
    )
    body = resp.json()
    assert _stage(body, "Behavioral Equivalence")["status"] == "INCONCLUSIVE"
    assert body["overall_status"] != "PASS"


def test_validation_analysis_failure_hides_internal_errors(monkeypatch, tmp_path):
    _mock_workspace(monkeypatch, tmp_path)
    (tmp_path / "if_else.cbl").write_text(_IF_ELSE, encoding="utf-8")

    def boom(source_id, source, work_dir):
        raise ValueError("secret internal detail")

    monkeypatch.setattr("app.api.services.pipeline.build_analysis_bundle", boom)

    resp = client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/modernization/validation",
        json={"filename": "if_else.cbl"},
    )
    assert resp.status_code == 500
    assert "secret" not in resp.text
