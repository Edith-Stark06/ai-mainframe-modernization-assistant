"""
Shared fixtures for workspace intelligence tests.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Application client
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a module-scoped test client for the application."""
    with TestClient(app) as tc:
        yield tc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Workspace directory helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace_dir(tmp_path: Path) -> Path:
    """Return an empty temporary workspace directory."""
    return tmp_path


@pytest.fixture()
def populated_workspace(tmp_path: Path) -> Path:
    """
    Return a workspace directory containing representative mainframe files.

    Structure::

        <tmp>/
            payroll.cbl
            copybook.cpy
            batch.jcl
            readme.txt
            subdir/
                report.cbl
    """
    (tmp_path / "payroll.cbl").write_bytes(
        b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. PAYROLL.\n"
    )
    (tmp_path / "copybook.cpy").write_bytes(
        b"       01 WS-RECORD.\n          05 WS-NAME PIC X(30).\n"
    )
    (tmp_path / "batch.jcl").write_bytes(
        b"//MYJOB   JOB (ACCT),'PAYROLL',CLASS=A\n//STEP1 EXEC PGM=IEFBR14\n"
    )
    (tmp_path / "readme.txt").write_bytes(
        b"This workspace contains payroll programs.\n"
    )
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "report.cbl").write_bytes(
        b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. REPORT.\n"
    )
    return tmp_path


@pytest.fixture()
def workspace_with_zip(tmp_path: Path) -> Path:
    """Return a workspace directory containing a ZIP archive with COBOL and JCL members."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "archived.cbl",
            "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. ARCHIVE.\n",
        )
        zf.writestr(
            "archived.jcl",
            "//ARCHJOB JOB (ACCT),'ARCHIVE',CLASS=A\n",
        )
    (tmp_path / "batch.zip").write_bytes(buf.getvalue())
    return tmp_path
