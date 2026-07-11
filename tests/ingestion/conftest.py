"""
Shared fixtures for ingestion tests.

Purpose:
    Provide reusable pytest fixtures covering workspace management,
    sample file bytes, and a pre-configured test client for the upload
    endpoint integration tests.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest
from fastapi.testclient import TestClient

from app.ingestion.workspace import WorkspaceManager
from app.main import app

# ---------------------------------------------------------------------------
# Application client fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Return a module-scoped synchronous test client for the application.

    Returns:
        A :class:`fastapi.testclient.TestClient` wrapping the application.
    """
    with TestClient(app) as test_client:
        yield test_client  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Workspace fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace_manager(tmp_path, monkeypatch) -> WorkspaceManager:
    """
    Return a :class:`WorkspaceManager` scoped to a temporary directory.

    The ``settings.workspace_dir`` is monkey-patched so tests never touch
    the real ``workspace/`` directory.

    Args:
        tmp_path:   pytest built-in temporary directory fixture.
        monkeypatch: pytest built-in monkeypatch fixture.

    Returns:
        A :class:`WorkspaceManager` rooted at *tmp_path*.
    """
    import app.ingestion.workspace as ws_module
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "workspace_dir", str(tmp_path))
    monkeypatch.setattr(ws_module, "WorkspaceManager", lambda: _make_manager(tmp_path))
    return _make_manager(tmp_path)


def _make_manager(root) -> WorkspaceManager:
    """Instantiate a :class:`WorkspaceManager` with *root* as its workspace dir."""
    mgr = WorkspaceManager.__new__(WorkspaceManager)
    from pathlib import Path

    mgr._root = Path(root)  # type: ignore[attr-defined]
    mgr._root.mkdir(parents=True, exist_ok=True)
    return mgr


# ---------------------------------------------------------------------------
# Sample file content fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cobol_content() -> bytes:
    """Return minimal syntactically valid-looking COBOL bytes."""
    return (
        b"       IDENTIFICATION DIVISION.\n"
        b"       PROGRAM-ID. PAYROLL.\n"
        b"       DATA DIVISION.\n"
        b"       PROCEDURE DIVISION.\n"
        b"           STOP RUN.\n"
    )


@pytest.fixture()
def jcl_content() -> bytes:
    """Return minimal JCL bytes."""
    return (
        b"//MYJOB   JOB (ACCT),'PAYROLL',CLASS=A\n"
        b"//STEP1   EXEC PGM=IEFBR14\n"
        b"//SYSOUT  DD SYSOUT=*\n"
    )


@pytest.fixture()
def utf16_content() -> bytes:
    """Return UTF-16 LE BOM-prefixed bytes."""
    return b"\xff\xfe" + "Hello COBOL".encode("utf-16-le")


@pytest.fixture()
def ebcdic_content() -> bytes:
    """
    Return bytes that trigger the EBCDIC heuristic.

    EBCDIC uses values >= 0x40 for printable characters and many
    values below 0x40 for control codes.  This sample has a high
    proportion of high bytes and no ASCII printable pattern.
    """
    # Simulate EBCDIC: mostly bytes in 0x40–0xFF range, no 0x0A/0x0D
    return bytes([0xC9, 0xC4, 0xC5, 0xD5, 0x40, 0xD9, 0xC9, 0xE5] * 100)
