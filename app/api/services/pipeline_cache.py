"""
Bounded, thread-safe, content-addressed cache for the modernization
pipeline result of one (workspace, filename, source content) triple.

Why this exists: Architecture, COBOL<->Java, Validation Center, and
Report are four independent HTTP requests -- there is no Python object
shared between them without a server-side cache, so without this layer
each screen silently reran the entire Phase 1-11 pipeline (parsing,
architecture derivation, Java generation, compilation, behavioral
validation) on every request, even across screens for the exact same
already-analyzed file.

Design (see the PR description for the full rationale):
    * The cache key is ``(workspace_id, filename, source_sha256)`` --
      workspace-scoped, so a cached entry for one workspace can never
      be served for a different workspace_id, and content-addressed,
      so editing the source file changes its hash, which changes the
      key, which is a guaranteed cache miss. A changed file can never
      return a stale result, and no separate invalidation step exists
      to forget to call.
    * Process-wide, not per-request or per-session: a per-request cache
      cannot satisfy "all four endpoints consume the same result",
      since each endpoint IS a separate request (and Streamlit's own
      session lives in a different process entirely). A process-wide
      cache is the only mechanism that actually achieves that.
    * Bounded (LRU, default 64 entries) so a long-running server cannot
      accumulate unbounded memory across many workspaces/files/edits --
      a stale entry for an old version of a file is simply never looked
      up again (its key no longer matches) and ages out under eviction
      like any other entry.
    * Thread-safe with per-key locking: concurrent requests for
      DIFFERENT keys never block each other; concurrent requests for
      the SAME not-yet-cached key block on each other so the expensive
      pipeline runs at most once, not once per concurrent caller.
    * Holds only immutable, self-contained pydantic/dataclass results
      (:class:`AnalysisBundle`, :class:`ModernizationBundle`) -- nothing
      here references a request, a session, or any other workspace's
      state, so there is no path by which one workspace's request can
      observe or mutate another workspace's cached result.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Callable, Tuple

from app.dataset.analysis_bundle import AnalysisBundle
from app.dataset.modernization_bundle import ModernizationBundle

__all__ = ["CacheKey", "CacheValue", "PipelineCache", "get_pipeline_cache"]

#: (workspace_id, filename, source_sha256) -- see module docstring.
CacheKey = Tuple[str, str, str]
CacheValue = Tuple[AnalysisBundle, ModernizationBundle]

_DEFAULT_MAX_ENTRIES = 64


class PipelineCache:
    """A bounded LRU cache keyed by ``CacheKey``, building each value at
    most once even under concurrent requests for the same key."""

    def __init__(self, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._store: "OrderedDict[CacheKey, CacheValue]" = OrderedDict()
        self._store_lock = threading.Lock()
        self._key_locks: dict[CacheKey, threading.Lock] = {}
        self._key_locks_lock = threading.Lock()

    def get_or_build(
        self, key: CacheKey, builder: Callable[[], CacheValue]
    ) -> CacheValue:
        hit = self._peek(key)
        if hit is not None:
            return hit

        key_lock = self._lock_for(key)
        try:
            with key_lock:
                # a concurrent caller may have finished building this
                # exact key while we were waiting for the lock -- check
                # again before doing the work a second time.
                hit = self._peek(key)
                if hit is not None:
                    return hit

                value = builder()

                with self._store_lock:
                    self._store[key] = value
                    self._store.move_to_end(key)
                    while len(self._store) > self._max_entries:
                        self._store.popitem(last=False)

                return value
        finally:
            # Always drop the per-key lock, including when builder()
            # raised: a failed build must never be cached (a transient
            # error should not stick around forever), and the lock
            # entry must not leak either -- otherwise a key that
            # repeatedly fails to build would grow _key_locks without
            # bound. Safe once we leave the `with key_lock` block: any
            # new caller for this key either hits the fast _peek() path
            # (on success) or creates a fresh lock and retries (on
            # failure).
            with self._key_locks_lock:
                self._key_locks.pop(key, None)

    def _lock_for(self, key: CacheKey) -> threading.Lock:
        with self._key_locks_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def _peek(self, key: CacheKey) -> CacheValue | None:
        with self._store_lock:
            value = self._store.get(key)
            if value is not None:
                self._store.move_to_end(key)
            return value

    def __len__(self) -> int:
        with self._store_lock:
            return len(self._store)

    def __contains__(self, key: CacheKey) -> bool:
        with self._store_lock:
            return key in self._store

    def clear(self) -> None:
        """Test-only: reset the cache to an empty state."""
        with self._store_lock:
            self._store.clear()
        with self._key_locks_lock:
            self._key_locks.clear()


_singleton: PipelineCache | None = None
_singleton_lock = threading.Lock()


def get_pipeline_cache() -> PipelineCache:
    """FastAPI dependency: the process-wide pipeline cache singleton.

    A plain module-level singleton (not ``@lru_cache`` on a factory) so
    tests can reach the exact same instance FastAPI's dependency
    injection resolves, to assert on/clear it directly.
    """
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = PipelineCache()
    return _singleton
