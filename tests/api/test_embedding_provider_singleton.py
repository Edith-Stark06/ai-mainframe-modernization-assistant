"""
Tests that :func:`app.api.dependencies.rag.get_embedding_provider` loads
the embedding model exactly once even under concurrent first use.

Purpose:
    With the startup warm-up running in a background thread, a request
    can arrive while the model is still loading. A bare
    ``functools.lru_cache`` would let both threads construct their own
    copy (it protects the cache, not the computation), doubling memory
    and load time. The lock in get_embedding_provider must make
    concurrent callers share the single in-flight load.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import threading
import time

import pytest

from app.api.dependencies import rag


class _CountingProvider:
    constructed = 0

    def __init__(self) -> None:
        type(self).constructed += 1
        time.sleep(0.3)  # long enough that every thread overlaps the load


@pytest.fixture
def fresh_cache(monkeypatch: pytest.MonkeyPatch):
    _CountingProvider.constructed = 0
    rag._load_embedding_provider.cache_clear()
    monkeypatch.setattr(rag, "SentenceTransformerProvider", _CountingProvider)
    yield
    rag._load_embedding_provider.cache_clear()


def test_concurrent_first_use_constructs_exactly_once(fresh_cache) -> None:
    results: list[object] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        results.append(rag.get_embedding_provider())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert _CountingProvider.constructed == 1
    assert len(results) == 8
    assert all(r is results[0] for r in results)


def test_later_calls_reuse_the_cached_provider(fresh_cache) -> None:
    first = rag.get_embedding_provider()
    second = rag.get_embedding_provider()
    assert first is second
    assert _CountingProvider.constructed == 1
