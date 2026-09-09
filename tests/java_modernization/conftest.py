"""Phase 9 fixtures — deterministic, no live LLM."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.dataset.analysis_bundle import build_analysis_bundle

ELIG = Path("tests/fixtures/phase4/eligibility_rules.cbl")
IF_ELSE = Path("tests/golden/if_else.cbl")
CALL = Path("tests/golden/call.cbl")
COMBINED = Path("tests/golden/combined_program.cbl")


def _bundle(sid: str, path: Path):
    return build_analysis_bundle(
        sid, path.read_text(encoding="utf-8"), tempfile.mkdtemp()
    )


@pytest.fixture(scope="session")
def elig_bundle():
    return _bundle("ELIGIBILITY", ELIG)


@pytest.fixture(scope="session")
def if_else_bundle():
    return _bundle("IFELSE", IF_ELSE)


@pytest.fixture(scope="session")
def call_bundle():
    return _bundle("CALLTEST", CALL)


@pytest.fixture(scope="session")
def combined_bundle():
    return _bundle("COMBINED", COMBINED)
