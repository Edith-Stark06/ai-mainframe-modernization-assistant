"""
Tests for :mod:`app.frontend.client`.

Mocks are applied at the transport boundary (``httpx.Client.request``) so
that each :class:`~app.frontend.client.BackendClient` method is exercised
exactly as it would run against the real backend, without depending on a
live server.
"""

import sys
from unittest.mock import MagicMock

import httpx
import pytest

# Mock streamlit before importing app.frontend.client's package (app.frontend.__init__
# is empty, but keep the existing convention from prior test runs).
mock_st = MagicMock()
sys.modules.setdefault("streamlit", mock_st)

from app.frontend.client import BackendAPIError, BackendClient  # noqa: E402


def _json_response(status_code: int, payload: dict) -> httpx.Response:
    request = httpx.Request("GET", "http://test/x")
    return httpx.Response(status_code=status_code, json=payload, request=request)


def test_client_initialization():
    client = BackendClient(base_url="http://test")
    assert client.base_url == "http://test"


def test_upload_files_success(monkeypatch):
    captured = {}

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["files"] = kwargs.get("files")
        return _json_response(
            200,
            {"workspace_id": "ws-1", "files": [], "total_files": 1, "message": "ok"},
        )

    monkeypatch.setattr(httpx.Client, "request", fake_request)

    client = BackendClient()
    result = client.upload_files([("MAIN.cbl", b"IDENTIFICATION DIVISION.")])

    assert captured["method"] == "POST"
    assert captured["url"] == "/upload"
    assert captured["files"][0][0] == "files"
    assert captured["files"][0][1][0] == "MAIN.cbl"
    assert result["workspace_id"] == "ws-1"


def test_get_inventory_success(monkeypatch):
    captured = {}

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _json_response(
            200,
            {
                "workspace_id": "ws-1",
                "files": [{"filename": "MAIN.cbl"}],
                "total_files": 1,
                "scanned_at": "2026-01-01T00:00:00Z",
            },
        )

    monkeypatch.setattr(httpx.Client, "request", fake_request)

    client = BackendClient()
    result = client.get_inventory("ws-1")

    assert captured["method"] == "GET"
    assert captured["url"] == "/workspaces/ws-1/inventory"
    assert result["files"][0]["filename"] == "MAIN.cbl"


def test_analyze_modernization_success(monkeypatch):
    captured = {}

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _json_response(
            200,
            {
                "flow": {
                    "id": "f1",
                    "name": "flow",
                    "nodes": [],
                    "edges": [],
                    "metadata": {},
                },
                "score": {
                    "complexity_score": 0.5,
                    "coupling_score": 0.2,
                    "overall_readiness": 0.7,
                    "metadata": {},
                },
                "recommendations": [],
            },
        )

    monkeypatch.setattr(httpx.Client, "request", fake_request)

    client = BackendClient()
    result = client.analyze_modernization("ws-1", "MAIN.cbl")

    assert captured["method"] == "POST"
    assert captured["url"] == "/workspaces/ws-1/modernization/pipeline"
    assert captured["json"] == {"filename": "MAIN.cbl"}
    assert result["score"]["overall_readiness"] == 0.7


def test_send_chat_message_uses_query_field(monkeypatch):
    captured = {}

    def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _json_response(
            200,
            {
                "query": "hi",
                "answer": "hello",
                "context": [],
                "error": None,
                "modernization_data": None,
            },
        )

    monkeypatch.setattr(httpx.Client, "request", fake_request)

    client = BackendClient()
    result = client.send_chat_message(
        workspace_id="ws-1",
        query="hi",
        filename="MAIN.cbl",
        include_modernization_context=True,
    )

    assert captured["url"] == "/chat/"
    assert captured["json"]["query"] == "hi"
    assert "message" not in captured["json"]
    assert captured["json"]["filename"] == "MAIN.cbl"
    assert captured["json"]["include_modernization_context"] is True
    assert result["answer"] == "hello"


def test_send_chat_message_omits_filename_when_absent(monkeypatch):
    captured = {}

    def fake_request(self, method, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _json_response(
            200,
            {
                "query": "hi",
                "answer": "hello",
                "context": [],
                "error": None,
                "modernization_data": None,
            },
        )

    monkeypatch.setattr(httpx.Client, "request", fake_request)

    client = BackendClient()
    client.send_chat_message(workspace_id="ws-1", query="hi")

    assert "filename" not in captured["json"]


@pytest.mark.parametrize(
    "status_code,expected_message",
    [
        (400, "The request was invalid. Please check your input and try again."),
        (403, "You do not have permission to perform this action."),
        (404, "The requested resource was not found."),
        (422, "The request could not be validated. Please check your input."),
        (500, "The server encountered an error. Please try again later."),
        (503, "The server encountered an error. Please try again later."),
    ],
)
def test_http_errors_map_to_safe_messages(monkeypatch, status_code, expected_message):
    def fake_request(self, method, url, **kwargs):
        request = httpx.Request(method, f"http://test{url}")
        return httpx.Response(
            status_code=status_code,
            json={"detail": "raw internal detail"},
            request=request,
        )

    monkeypatch.setattr(httpx.Client, "request", fake_request)

    client = BackendClient()
    with pytest.raises(BackendAPIError) as exc_info:
        client.get_inventory("ws-1")

    assert exc_info.value.message == expected_message
    assert exc_info.value.status_code == status_code
    # The raw backend detail must never leak into the safe message.
    assert "raw internal detail" not in exc_info.value.message


def test_network_error_maps_to_safe_message(monkeypatch):
    def fake_request(self, method, url, **kwargs):
        raise httpx.ConnectError("connection refused to 10.0.0.5")

    monkeypatch.setattr(httpx.Client, "request", fake_request)

    client = BackendClient()
    with pytest.raises(BackendAPIError) as exc_info:
        client.get_inventory("ws-1")

    assert exc_info.value.status_code is None
    assert "10.0.0.5" not in exc_info.value.message
    assert "connection" in exc_info.value.message.lower()
