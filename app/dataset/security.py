"""
Dataset security / data-hygiene scanning (#118 §7).

A COBOL file being syntactically valid does not make it safe to put in a
dataset. This module scans example source (and any free-text answer) for
credentials, keys, tokens, connection secrets, private keys, and — when
enabled — obvious PII.

The scanner is configurable (:class:`SecretScanConfig`) and produces
*actionable* findings: pattern name, line, a redacted preview, and a
severity. The dataset validator rejects any ``HIGH`` finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "Severity",
    "SecretFinding",
    "SecretScanConfig",
    "SecretScanner",
]


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class SecretFinding:
    pattern: str
    severity: Severity
    line: int
    preview: str  # already redacted
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "pattern": self.pattern,
            "severity": self.severity.value,
            "line": self.line,
            "preview": self.preview,
            "detail": self.detail,
        }


# (name, compiled regex, severity, human detail)
_DEFAULT_PATTERNS: tuple[tuple[str, re.Pattern[str], Severity, str], ...] = (
    (
        "aws_access_key_id",
        re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
        Severity.HIGH,
        "AWS access key id",
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
        Severity.HIGH,
        "PEM/OpenSSH private key header",
    ),
    (
        "bearer_token",
        re.compile(r"\b[Bb]earer\s+[A-Za-z0-9\-._~+/]{20,}=*"),
        Severity.HIGH,
        "HTTP bearer token",
    ),
    (
        "generic_api_key",
        re.compile(
            r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret)"
            r"\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"
        ),
        Severity.HIGH,
        "assignment to an api-key / secret-key / token identifier",
    ),
    (
        "password_assignment",
        re.compile(
            r"(?i)\b(pass(word)?|pwd|passwd)\b\s*[:=]\s*['\"]?[^\s'\"]{4,}['\"]?"
        ),
        Severity.MEDIUM,
        "assignment to a password identifier",
    ),
    (
        "db_connection_uri_with_credentials",
        re.compile(
            r"\b(?:jdbc:[a-z0-9]+://|mongodb(?:\+srv)?://|postgres(?:ql)?://|mysql://)"
            r"[^\s:@/]+:[^\s:@/]+@"
        ),
        Severity.HIGH,
        "database connection URI embedding a username:password",
    ),
    (
        "slack_token",
        re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
        Severity.HIGH,
        "Slack token",
    ),
    (
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
        Severity.HIGH,
        "GitHub token",
    ),
)

# Only used when config.pii_enabled is True.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], Severity, str], ...] = (
    (
        "email_address",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        Severity.MEDIUM,
        "email address",
    ),
    (
        "us_ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        Severity.HIGH,
        "US SSN-shaped number",
    ),
)


@dataclass(frozen=True)
class SecretScanConfig:
    """Configuration for :class:`SecretScanner`."""

    pii_enabled: bool = False
    #: extra ``(name, regex, severity, detail)`` tuples supplied by the caller
    extra_patterns: tuple[tuple[str, str, Severity, str], ...] = field(
        default_factory=tuple
    )
    #: pattern names to skip (e.g. a fixture deliberately containing
    #: ``PASSWORD PIC X(8)`` as a data-item name, not a value)
    ignore_patterns: frozenset[str] = frozenset()


def _redact(match_text: str) -> str:
    if len(match_text) <= 8:
        return match_text[0] + "***"
    return match_text[:4] + "***" + match_text[-2:]


class SecretScanner:
    """Scan text for secrets / credentials / PII. Stateless."""

    def __init__(self, config: SecretScanConfig | None = None) -> None:
        self.config = config or SecretScanConfig()
        self._patterns: list[tuple[str, re.Pattern[str], Severity, str]] = [
            p for p in _DEFAULT_PATTERNS if p[0] not in self.config.ignore_patterns
        ]
        if self.config.pii_enabled:
            self._patterns += [
                p for p in _PII_PATTERNS if p[0] not in self.config.ignore_patterns
            ]
        for name, pat, sev, detail in self.config.extra_patterns:
            self._patterns.append((name, re.compile(pat), sev, detail))

    def scan(self, text: str) -> list[SecretFinding]:
        """Return every finding, ordered by (line, pattern)."""
        findings: list[SecretFinding] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, pat, sev, detail in self._patterns:
                for m in pat.finditer(line):
                    findings.append(
                        SecretFinding(
                            pattern=name,
                            severity=sev,
                            line=lineno,
                            preview=_redact(m.group(0)),
                            detail=detail,
                        )
                    )
        findings.sort(key=lambda f: (f.line, f.pattern))
        return findings

    def has_blocking(self, text: str) -> bool:
        return any(f.severity is Severity.HIGH for f in self.scan(text))
