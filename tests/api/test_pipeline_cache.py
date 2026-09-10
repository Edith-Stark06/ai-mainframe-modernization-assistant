"""
Unit tests for :class:`app.api.services.pipeline_cache.PipelineCache`.

Pure, fast, no FastAPI/TestClient involved -- these test the cache's
own contract (reuse, bounding, isolation-by-key, failure handling,
thread-safety) independently of the API routes that use it.
"""

from __future__ import annotations

import threading
import time

from app.api.services.pipeline_cache import PipelineCache, get_pipeline_cache


def test_get_or_build_calls_builder_once_for_the_same_key():
    cache = PipelineCache()
    calls = []

    def build():
        calls.append(1)
        return ("bundle", "mb")

    key = ("ws-1", "MAIN.cbl", "sha-a")
    first = cache.get_or_build(key, build)
    second = cache.get_or_build(key, build)

    assert first is second
    assert len(calls) == 1


def test_different_keys_never_share_an_entry():
    cache = PipelineCache()
    calls = []

    def build():
        calls.append(1)
        return object()

    cache.get_or_build(("ws-1", "MAIN.cbl", "sha-a"), build)
    cache.get_or_build(("ws-2", "MAIN.cbl", "sha-a"), build)  # different workspace
    cache.get_or_build(("ws-1", "OTHER.cbl", "sha-a"), build)  # different filename
    cache.get_or_build(("ws-1", "MAIN.cbl", "sha-b"), build)  # different content hash

    assert len(calls) == 4
    assert len(cache) == 4


def test_changed_content_hash_is_a_guaranteed_cache_miss():
    """The cache key embeds source_sha256 -- an edited file is never
    served a stale result, with no separate invalidation call needed."""
    cache = PipelineCache()
    calls = []

    def build():
        calls.append(1)
        return f"result-{len(calls)}"

    v1 = cache.get_or_build(("ws-1", "MAIN.cbl", "sha-before-edit"), build)
    v2 = cache.get_or_build(("ws-1", "MAIN.cbl", "sha-after-edit"), build)

    assert v1 != v2
    assert len(calls) == 2


def test_failed_build_is_never_cached():
    cache = PipelineCache()
    calls = []
    key = ("ws-1", "MAIN.cbl", "sha-a")

    def failing_build():
        calls.append(1)
        raise ValueError("boom")

    for _ in range(3):
        try:
            cache.get_or_build(key, failing_build)
        except ValueError:
            pass

    assert len(calls) == 3  # every call retried -- nothing was cached
    assert len(cache) == 0
    assert key not in cache


def test_failed_build_does_not_leak_a_per_key_lock():
    cache = PipelineCache()
    key = ("ws-1", "MAIN.cbl", "sha-a")

    def failing_build():
        raise ValueError("boom")

    for _ in range(5):
        try:
            cache.get_or_build(key, failing_build)
        except ValueError:
            pass

    assert len(cache._key_locks) == 0  # no unbounded growth on repeated failure


def test_lru_eviction_bounds_memory():
    cache = PipelineCache(max_entries=3)
    for i in range(5):
        cache.get_or_build((f"ws-{i}", "MAIN.cbl", "sha"), lambda i=i: i)

    assert len(cache) == 3
    # the earliest entries were evicted
    assert ("ws-0", "MAIN.cbl", "sha") not in cache
    assert ("ws-1", "MAIN.cbl", "sha") not in cache
    assert ("ws-4", "MAIN.cbl", "sha") in cache


def test_accessing_an_entry_marks_it_most_recently_used():
    cache = PipelineCache(max_entries=2)
    cache.get_or_build(("ws-a", "f", "s"), lambda: "a")
    cache.get_or_build(("ws-b", "f", "s"), lambda: "b")
    cache.get_or_build(("ws-a", "f", "s"), lambda: "a-rebuilt")  # touch "a" again
    cache.get_or_build(("ws-c", "f", "s"), lambda: "c")  # evicts the LRU entry

    assert ("ws-a", "f", "s") in cache  # recently touched -- survives
    assert ("ws-b", "f", "s") not in cache  # least recently used -- evicted
    assert ("ws-c", "f", "s") in cache


def test_concurrent_calls_for_the_same_key_build_exactly_once():
    cache = PipelineCache()
    calls = []
    call_lock = threading.Lock()

    def slow_build():
        with call_lock:
            calls.append(1)
        time.sleep(0.05)
        return "built"

    key = ("ws-1", "MAIN.cbl", "sha-a")
    results = []
    results_lock = threading.Lock()

    def worker():
        value = cache.get_or_build(key, slow_build)
        with results_lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(calls) == 1
    assert results == ["built"] * 8


def test_concurrent_calls_for_different_keys_do_not_block_each_other():
    cache = PipelineCache()
    started = threading.Event()

    def build_a():
        started.set()
        time.sleep(0.2)
        return "a"

    def build_b():
        # if this blocked on build_a's lock, it would not run until
        # build_a finishes sleeping -- assert it runs concurrently instead
        assert started.wait(timeout=1.0)
        return "b"

    result_b = []

    t = threading.Thread(target=lambda: cache.get_or_build(("ws-a", "f", "s"), build_a))
    t.start()
    started.wait(timeout=1.0)
    result_b.append(cache.get_or_build(("ws-b", "f", "s"), build_b))
    t.join(timeout=5)

    assert result_b == ["b"]


def test_get_pipeline_cache_returns_the_same_singleton():
    a = get_pipeline_cache()
    b = get_pipeline_cache()
    assert a is b


def test_clear_empties_the_cache():
    cache = PipelineCache()
    cache.get_or_build(("ws-1", "f", "s"), lambda: "x")
    assert len(cache) == 1

    cache.clear()

    assert len(cache) == 0
