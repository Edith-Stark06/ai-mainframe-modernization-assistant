"""#127 — compilation, structured diagnostics, source mapping, security, limits."""

from __future__ import annotations

import pytest

from app.java_modernization.architecture import build_architecture
from app.java_modernization.compilation import (
    DiagnosticSeverity,
    JavaCompiler,
    javac_available,
)
from app.java_modernization.errors import CompilationSetupError
from app.java_modernization.generation import generate_project

pytestmark = pytest.mark.skipif(not javac_available(), reason="javac not on PATH")


def _project(bundle):
    return generate_project(bundle, build_architecture(bundle))


def test_valid_project_compiles(elig_bundle, tmp_path):
    r = JavaCompiler(tmp_path).compile(_project(elig_bundle))
    assert r.success
    assert r.errors == ()
    assert r.command[0] == "javac"
    assert "javac" in r.jdk_version
    assert r.file_records
    assert r.duration_s >= 0.0


def test_syntax_error_is_a_structured_diagnostic_not_an_exception(
    elig_bundle, tmp_path
):
    p = _project(elig_bundle)
    broken = p.model_copy(
        update={
            "files": {
                **p.files,
                f"src/{p.main_class}.java": p.files[f"src/{p.main_class}.java"].replace(
                    "checkEligibility();", "checkEligibility()"
                ),
            }
        }
    )
    r = JavaCompiler(tmp_path).compile(broken)
    assert not r.success
    assert r.errors
    d = r.errors[0]
    assert d.severity is DiagnosticSeverity.ERROR
    assert d.file and d.file.endswith(".java")
    assert d.line and d.line >= 1
    assert d.message


def test_diagnostic_maps_back_to_cobol(elig_bundle, tmp_path):
    p = _project(elig_bundle)
    # break inside a rule-bearing method
    src = p.files[f"src/{p.main_class}.java"]
    broken = src.replace(
        "private void checkEligibility() {",
        "private void checkEligibility() {\n        int x = ;",
    )
    r = JavaCompiler(tmp_path).compile(
        p.model_copy(update={"files": {**p.files, f"src/{p.main_class}.java": broken}})
    )
    assert not r.success
    mapped = [d for d in r.errors if d.cobol_source_mapping is not None]
    assert mapped
    m = mapped[0].cobol_source_mapping
    assert m.source_id == "ELIGIBILITY"
    assert m.paragraph == "CHECK-ELIGIBILITY"
    assert "BR-001" in mapped[0].business_rule_ids


def test_warnings_are_not_failures(if_else_bundle, tmp_path):
    p = generate_project(if_else_bundle, build_architecture(if_else_bundle))
    # add a deprecation-ish unused import? simplest: a redundant cast warning
    src = p.files[f"src/{p.main_class}.java"]
    warned = src.replace(
        "public void run() {", "public void run() {\n        long z = (long)(long) 1L;"
    )
    r = JavaCompiler(tmp_path, javac="javac").compile(
        p.model_copy(update={"files": {**p.files, f"src/{p.main_class}.java": warned}})
    )
    # redundant cast is not an error; compilation should still succeed
    assert r.success or all(
        d.severity is not DiagnosticSeverity.ERROR for d in r.diagnostics
    )


def test_path_traversal_is_rejected(elig_bundle, tmp_path):
    p = _project(elig_bundle)
    for bad in ("../evil.java", "/etc/passwd.java", "src/../../x.java"):
        with pytest.raises(CompilationSetupError):
            JavaCompiler(tmp_path).compile(
                p.model_copy(update={"files": {**p.files, bad: "class X {}"}})
            )


def test_timeout_returns_a_structured_diagnostic(elig_bundle, tmp_path, monkeypatch):
    import subprocess

    p = _project(elig_bundle)
    real = subprocess.run

    def slow(cmd, *a, **kw):  # noqa: ANN001
        if cmd and str(cmd[0]).endswith("javac") and "-version" not in cmd:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))
        return real(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "run", slow)
    r = JavaCompiler(tmp_path, timeout_s=0.5).compile(p)
    assert r.timed_out
    assert not r.success
    assert any(d.error_code == "P9-TIMEOUT" for d in r.errors)


def test_file_records_are_reproducible(elig_bundle, tmp_path):
    p = _project(elig_bundle)
    a = JavaCompiler(tmp_path / "a").compile(p)
    b = JavaCompiler(tmp_path / "b").compile(p)
    assert {f.path: f.sha256 for f in a.file_records} == {
        f.path: f.sha256 for f in b.file_records
    }
