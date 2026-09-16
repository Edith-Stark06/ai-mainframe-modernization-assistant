"""Phase 10 fixtures — deterministic, no live LLM, no COBOL runtime required."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.dataset.analysis_bundle import build_analysis_bundle
from app.java_modernization.architecture import build_architecture
from app.java_modernization.generation import generate_project

ELIG = Path("tests/fixtures/phase4/eligibility_rules.cbl")
IF_ELSE = Path("tests/golden/if_else.cbl")
CALL = Path("tests/golden/call.cbl")
COMBINED = Path("tests/golden/combined_program.cbl")
STATUS = Path("data/sources/phase6/status_machine.cbl")


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


@pytest.fixture(scope="session")
def status_bundle():
    return _bundle("STATUSMACH", STATUS)


@pytest.fixture(scope="session")
def if_else_architecture(if_else_bundle):
    return build_architecture(if_else_bundle)


@pytest.fixture(scope="session")
def if_else_project(if_else_bundle, if_else_architecture):
    return generate_project(if_else_bundle, if_else_architecture)


@pytest.fixture(scope="session")
def combined_architecture(combined_bundle):
    return build_architecture(combined_bundle)


@pytest.fixture(scope="session")
def combined_project(combined_bundle, combined_architecture):
    return generate_project(combined_bundle, combined_architecture)


@pytest.fixture(scope="session")
def elig_architecture(elig_bundle):
    return build_architecture(elig_bundle)


@pytest.fixture(scope="session")
def elig_project(elig_bundle, elig_architecture):
    return generate_project(elig_bundle, elig_architecture)
