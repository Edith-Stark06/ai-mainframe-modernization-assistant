"""#118 §7 — secret / data-hygiene scanner tests."""

from __future__ import annotations

from app.dataset.security import SecretScanConfig, SecretScanner, Severity


def _sev(findings, pattern):
    return [f for f in findings if f.pattern == pattern]


def test_detects_aws_key() -> None:
    findings = SecretScanner().scan(
        "       01 K PIC X(20) VALUE 'AKIA1234567890ABCDEF'."
    )
    hits = _sev(findings, "aws_access_key_id")
    assert hits and hits[0].severity is Severity.HIGH
    assert "AKIA" not in hits[0].preview or "***" in hits[0].preview


def test_detects_private_key_header() -> None:
    text = "some text\n-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n"
    assert SecretScanner().has_blocking(text)


def test_detects_api_key_assignment_and_db_uri() -> None:
    s = SecretScanner()
    assert s.has_blocking('api_key = "abcdefghijklmnop1234"')
    assert s.has_blocking("jdbc:postgresql://user:s3cr3t@db:5432/app")


def test_password_assignment_is_medium_not_blocking() -> None:
    findings = SecretScanner().scan("password: hunter2xyz")
    pw = _sev(findings, "password_assignment")
    assert pw and pw[0].severity is Severity.MEDIUM
    assert not SecretScanner().has_blocking("password: hunter2xyz")


def test_clean_cobol_has_no_findings() -> None:
    clean = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. CLEAN.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN.\n"
        "           MOVE 1 TO WS-A.\n"
        "           STOP RUN.\n"
    )
    assert SecretScanner().scan(clean) == []


def test_pii_scanning_is_opt_in() -> None:
    text = "contact admin@example.com for access"
    assert SecretScanner().scan(text) == []
    on = SecretScanner(SecretScanConfig(pii_enabled=True)).scan(text)
    assert any(f.pattern == "email_address" for f in on)


def test_ignore_patterns_and_extra_patterns() -> None:
    # a data item literally NAMED PASSWORD is not a leaked secret
    cfg = SecretScanConfig(ignore_patterns=frozenset({"password_assignment"}))
    assert SecretScanner(cfg).scan("       01 PASSWORD PIC X(8).") == []
    # caller-supplied extra pattern
    cfg2 = SecretScanConfig(
        extra_patterns=(("internal_id", r"INT-\d{6}", Severity.HIGH, "internal id"),)
    )
    assert SecretScanner(cfg2).has_blocking("ref INT-123456")


def test_findings_are_deterministically_ordered() -> None:
    text = "AKIA1111111111111111\napi_key='abcdefghijklmnop'\nAKIA2222222222222222"
    a = [f.to_dict() for f in SecretScanner().scan(text)]
    b = [f.to_dict() for f in SecretScanner().scan(text)]
    assert a == b
    assert [f["line"] for f in a] == sorted(f["line"] for f in a)
