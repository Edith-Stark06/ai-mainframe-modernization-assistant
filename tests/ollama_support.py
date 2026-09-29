"""
Shared helpers for tests that need a real, running Ollama server.

Purpose:
    Tests that exercise the real Ollama provider against a real model
    are only meaningful where a server (and, for generation, a pulled
    model) actually exists -- a developer machine with Ollama running.
    They cannot run on a stock CI runner. Marking them with these
    markers makes them *skip with a stated reason* there, rather than
    fail on connection-refused, while still running for real wherever
    Ollama is available. The error-path tests that need no server are
    deliberately not marked and always run.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

OLLAMA_TEST_HOST = os.environ.get("OLLAMA_TEST_HOST", "http://localhost:11434")
OLLAMA_TEST_MODEL = os.environ.get("OLLAMA_TEST_MODEL", "qwen2.5:0.5b")


def _fetch_tags() -> list[str] | None:
    """Return the names of locally available models, or None if no
    Ollama server answers at OLLAMA_TEST_HOST."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_TEST_HOST}/api/tags", timeout=3) as resp:
            payload = json.load(resp)
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return None
    return [m.get("name", "") for m in payload.get("models", [])]


_TAGS = _fetch_tags()

#: A real Ollama server is reachable.
requires_ollama_server = pytest.mark.skipif(
    _TAGS is None,
    reason=f"no Ollama server reachable at {OLLAMA_TEST_HOST}",
)

#: A real Ollama server is reachable AND has OLLAMA_TEST_MODEL pulled.
requires_ollama_model = pytest.mark.skipif(
    _TAGS is None or OLLAMA_TEST_MODEL not in _TAGS,
    reason=(
        f"Ollama model '{OLLAMA_TEST_MODEL}' not available at "
        f"{OLLAMA_TEST_HOST} (run `ollama pull {OLLAMA_TEST_MODEL}`)"
    ),
)
