"""
Backend API client for the Streamlit frontend.

Purpose:
    Provide a single, typed boundary between the Streamlit UI and the
    FastAPI backend. All HTTP calls to the Modernization Intelligence
    Pipeline (Tasks 080-084) and the Chat/RAG API are made through this
    module so that transport concerns stay out of the presentation layer.

Responsibilities:
    - Upload source files to create a workspace
      (``POST /api/v1/upload``).
    - Fetch a workspace's file inventory
      (``GET /api/v1/workspaces/{workspace_id}/inventory``).
    - Trigger the modernization pipeline for a single file
      (``POST /api/v1/workspaces/{workspace_id}/modernization/pipeline``).
    - Send a modernization-aware chat query
      (``POST /api/v1/chat/``).
    - Translate every backend failure (HTTP error status or network
      failure) into a :class:`BackendAPIError` carrying only a safe,
      user-facing message. Internal exception text, stack traces, and
      filesystem paths returned by the backend are never surfaced to
      the UI layer.

Note:
    There is no backend endpoint to list all existing workspaces
    (``WorkspaceManager`` only supports ``create`` and ``get``), so this
    client intentionally does not expose a "list workspaces" method.
    Callers must either upload files to create a new workspace or supply
    a previously known ``workspace_id``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

_SAFE_MESSAGES: Dict[int, str] = {
    400: "The request was invalid. Please check your input and try again.",
    403: "You do not have permission to perform this action.",
    404: "The requested resource was not found.",
    422: "The request could not be validated. Please check your input.",
}
_SAFE_SERVER_ERROR = "The server encountered an error. Please try again later."
_SAFE_NETWORK_ERROR = (
    "Unable to reach the backend service. Please check your connection and try again."
)


def _safe_message_for_status(status_code: int) -> str:
    """Map an HTTP status code to a safe, user-facing message."""
    if status_code in _SAFE_MESSAGES:
        return _SAFE_MESSAGES[status_code]
    if 400 <= status_code < 500:
        return (
            "The request could not be completed. Please check your input and try again."
        )
    return _SAFE_SERVER_ERROR


class BackendAPIError(Exception):
    """
    Safe, user-facing error raised for any backend API failure.

    Attributes:
        message:     Safe message suitable for direct display to the user.
        status_code: HTTP status code, or ``None`` for a network failure.
    """

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class BackendClient:
    """Thin, typed HTTP client for the Modernization Intelligence backend API."""

    def __init__(self, base_url: str = API_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def _request(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            response = self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error("Backend API error: {} {} -> HTTP {}", method, url, status)
            raise BackendAPIError(_safe_message_for_status(status), status) from e
        except httpx.HTTPError as e:
            logger.error("Backend network error: {} {} -> {}", method, url, e)
            raise BackendAPIError(_SAFE_NETWORK_ERROR) from e

    def upload_files(self, files: List[Tuple[str, bytes]]) -> Dict[str, Any]:
        """
        Upload one or more source files, creating a new workspace.

        Args:
            files: List of ``(filename, content_bytes)`` tuples.

        Returns:
            The decoded ``UploadResponse`` JSON body, including the new
            ``workspace_id``.
        """
        multipart = [
            ("files", (name, content, "application/octet-stream"))
            for name, content in files
        ]
        return self._request("POST", "/upload", files=multipart)

    def get_inventory(self, workspace_id: str) -> Dict[str, Any]:
        """Fetch the file inventory for an existing workspace."""
        return self._request("GET", f"/workspaces/{workspace_id}/inventory")

    def analyze_modernization(self, workspace_id: str, filename: str) -> Dict[str, Any]:
        """Trigger the modernization pipeline (flow, score, recommendations)."""
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/modernization/pipeline",
            json={"filename": filename},
        )

    def send_chat_message(
        self,
        workspace_id: str,
        query: str,
        filename: Optional[str] = None,
        include_modernization_context: bool = False,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Send a chat query, optionally enriched with modernization context."""
        payload: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "query": query,
            "top_k": top_k,
            "include_modernization_context": include_modernization_context,
        }
        if filename:
            payload["filename"] = filename
        return self._request("POST", "/chat/", json=payload)
