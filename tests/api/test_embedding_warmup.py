"""
Tests for the opt-in embedding warm-up in :mod:`app.main`'s lifespan.

Purpose:
    The real embedding model takes about a minute to load in a fresh
    container -- longer than the Streamlit client's 30s timeout -- so
    the first chat request after every start would fail in the UI.
    WARM_EMBEDDINGS loads it in a background thread at startup
    instead. These tests verify it is off by default (tests and dev
    runs must not each pay a real model load), that enabling it does
    not block startup, and that a failing warm-up never takes the API
    down.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import rag
from app.core import config as cfg_mod
from app.main import app


def test_warmup_is_off_by_default() -> None:
    assert cfg_mod.Settings().warm_embeddings is False


def test_default_startup_does_not_load_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg_mod.settings, "warm_embeddings", False)
    calls: list[int] = []
    monkeypatch.setattr(rag, "get_embedding_provider", lambda: calls.append(1))

    with TestClient(app):
        pass

    assert calls == []


def test_enabled_startup_loads_the_provider_in_the_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg_mod.settings, "warm_embeddings", True)
    loaded = threading.Event()
    release = threading.Event()
    seen_thread: list[str] = []

    def slow_load() -> None:
        seen_thread.append(threading.current_thread().name)
        loaded.set()
        release.wait(timeout=10)

    monkeypatch.setattr(rag, "get_embedding_provider", slow_load)

    try:
        # Startup must complete and the API must answer while the
        # "model load" is still blocked -- that is the whole point.
        with TestClient(app) as client:
            assert loaded.wait(timeout=10), "warm-up thread never started"
            assert client.get("/api/v1/health").status_code == 200
            assert not release.is_set()
    finally:
        release.set()

    assert seen_thread == ["embedding-warmup"]


def test_failing_warmup_does_not_break_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg_mod.settings, "warm_embeddings", True)
    attempted = threading.Event()

    def boom() -> None:
        attempted.set()
        raise RuntimeError("model missing")

    monkeypatch.setattr(rag, "get_embedding_provider", boom)

    with TestClient(app) as client:
        assert attempted.wait(timeout=10)
        assert client.get("/api/v1/health").status_code == 200
