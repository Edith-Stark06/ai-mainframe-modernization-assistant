"""
Upload API Endpoint Tests.

Purpose:
    Integration tests for ``POST /api/v1/upload`` exercising the full
    request/response cycle through the FastAPI test client.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a module-scoped test client."""
    with TestClient(app) as tc:
        yield tc  # type: ignore[misc]


_COBOL = b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TEST.\n"
_JCL = b"//MYJOB   JOB (ACCT),'TEST',CLASS=A\n"


def _make_zip(files: dict[str, bytes]) -> bytes:
    """Build an in-memory ZIP archive from *files* mapping name → content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Nominal upload tests
# ---------------------------------------------------------------------------


class TestUploadEndpointNominal:
    """Tests for successful upload scenarios."""

    def test_single_cobol_upload_returns_200(self, client: TestClient) -> None:
        """Uploading a single COBOL file must return HTTP 200."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("payroll.cbl", _COBOL, "text/plain"))],
        )
        assert response.status_code == 200

    def test_response_success_is_true(self, client: TestClient) -> None:
        """Success field must be True on nominal upload."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("prog.cbl", _COBOL, "text/plain"))],
        )
        assert response.json()["success"] is True

    def test_response_contains_workspace_id(self, client: TestClient) -> None:
        """Response must contain a non-empty workspace_id."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("prog.cbl", _COBOL, "text/plain"))],
        )
        body = response.json()
        assert "workspace_id" in body
        assert body["workspace_id"]

    def test_response_total_files_matches(self, client: TestClient) -> None:
        """total_files must equal the number of uploaded files."""
        response = client.post(
            "/api/v1/upload",
            files=[
                ("files", ("a.cbl", _COBOL, "text/plain")),
                ("files", ("b.jcl", _JCL, "text/plain")),
            ],
        )
        body = response.json()
        assert body["total_files"] == 2

    def test_response_files_list_length(self, client: TestClient) -> None:
        """files list in response must have one entry per uploaded file."""
        response = client.post(
            "/api/v1/upload",
            files=[
                ("files", ("x.cbl", _COBOL, "text/plain")),
                ("files", ("y.jcl", _JCL, "text/plain")),
            ],
        )
        body = response.json()
        assert len(body["files"]) == 2

    def test_file_metadata_contains_required_keys(self, client: TestClient) -> None:
        """Each file metadata entry must carry all required fields."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("test.cbl", _COBOL, "text/plain"))],
        )
        file_meta = response.json()["files"][0]
        required = {
            "filename",
            "extension",
            "size_bytes",
            "sha256",
            "encoding",
            "workspace_id",
            "created_at",
        }
        assert required.issubset(set(file_meta.keys()))

    def test_file_metadata_filename_correct(self, client: TestClient) -> None:
        """Filename in response metadata must match the uploaded filename."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("mainprog.cbl", _COBOL, "text/plain"))],
        )
        assert response.json()["files"][0]["filename"] == "mainprog.cbl"

    def test_file_metadata_extension_correct(self, client: TestClient) -> None:
        """Extension in response metadata must be '.cbl'."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("prog.cbl", _COBOL, "text/plain"))],
        )
        assert response.json()["files"][0]["extension"] == ".cbl"

    def test_file_metadata_size_bytes_correct(self, client: TestClient) -> None:
        """size_bytes must equal the uploaded content length."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("prog.cbl", _COBOL, "text/plain"))],
        )
        assert response.json()["files"][0]["size_bytes"] == len(_COBOL)

    def test_file_metadata_sha256_is_64_chars(self, client: TestClient) -> None:
        """SHA-256 field must be a 64-character hex string."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("prog.cbl", _COBOL, "text/plain"))],
        )
        sha = response.json()["files"][0]["sha256"]
        assert len(sha) == 64

    def test_response_message_present(self, client: TestClient) -> None:
        """Response must include a non-empty message field."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("prog.cbl", _COBOL, "text/plain"))],
        )
        assert response.json()["message"]

    def test_jcl_file_upload(self, client: TestClient) -> None:
        """JCL files must be accepted and ingested."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("batch.jcl", _JCL, "text/plain"))],
        )
        assert response.status_code == 200

    def test_txt_file_upload(self, client: TestClient) -> None:
        """Plain text files must be accepted."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("readme.txt", b"notes", "text/plain"))],
        )
        assert response.status_code == 200

    def test_workspace_id_is_uuid4(self, client: TestClient) -> None:
        """workspace_id in the response must be a valid UUID4."""
        import uuid

        response = client.post(
            "/api/v1/upload",
            files=[("files", ("prog.cbl", _COBOL, "text/plain"))],
        )
        ws_id = response.json()["workspace_id"]
        parsed = uuid.UUID(ws_id, version=4)
        assert str(parsed) == ws_id


# ---------------------------------------------------------------------------
# ZIP upload tests
# ---------------------------------------------------------------------------


class TestUploadZipFile:
    """Tests for ZIP archive uploads."""

    def test_zip_upload_accepted(self, client: TestClient) -> None:
        """A ZIP archive must be accepted (HTTP 200)."""
        zip_bytes = _make_zip({"payroll.cbl": _COBOL, "batch.jcl": _JCL})
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("archive.zip", zip_bytes, "application/zip"))],
        )
        assert response.status_code == 200

    def test_zip_members_are_expanded(self, client: TestClient) -> None:
        """total_files must reflect the expanded ZIP members."""
        zip_bytes = _make_zip({"a.cbl": _COBOL, "b.jcl": _JCL})
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("batch.zip", zip_bytes, "application/zip"))],
        )
        assert response.json()["total_files"] == 2

    def test_zip_with_unsupported_member_skips_it(self, client: TestClient) -> None:
        """Members with unsupported extensions must be silently skipped."""
        zip_bytes = _make_zip({"good.cbl": _COBOL, "bad.docx": b"word content"})
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("mixed.zip", zip_bytes, "application/zip"))],
        )
        body = response.json()
        assert response.status_code == 200
        # Only the .cbl should have been ingested
        assert body["total_files"] == 1


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------


class TestUploadEndpointValidationErrors:
    """Tests for upload requests that should fail validation."""

    def test_unsupported_extension_returns_422(self, client: TestClient) -> None:
        """Uploading a file with an unsupported extension must return 422."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("report.docx", b"content", "text/plain"))],
        )
        assert response.status_code == 422

    def test_empty_file_returns_422(self, client: TestClient) -> None:
        """Uploading an empty file must return 422."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("empty.cbl", b"", "text/plain"))],
        )
        assert response.status_code == 422

    def test_duplicate_filenames_returns_422(self, client: TestClient) -> None:
        """Uploading two files with the same name must return 422."""
        response = client.post(
            "/api/v1/upload",
            files=[
                ("files", ("same.cbl", _COBOL, "text/plain")),
                ("files", ("same.cbl", _COBOL, "text/plain")),
            ],
        )
        assert response.status_code == 422

    def test_error_response_has_canonical_structure(self, client: TestClient) -> None:
        """Validation error response must match the canonical error envelope."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("bad.docx", b"x", "text/plain"))],
        )
        body = response.json()
        assert body["success"] is False
        assert "error" in body
        assert "request_id" in body
        assert "timestamp" in body

    def test_error_code_is_validation_error(self, client: TestClient) -> None:
        """Validation error response must carry the VALIDATION_ERROR code."""
        response = client.post(
            "/api/v1/upload",
            files=[("files", ("bad.docx", b"x", "text/plain"))],
        )
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
