"""Per-key single-flight cache guard.

Ensures a slow fetch for a given cache key only ever runs once at a time: if
a second call comes in for the same key while the first is still fetching, it
blocks on the same lock and then reads the cache the first call just wrote,
instead of kicking off a redundant fetch of its own.

Repos own their own cache storage (SQLite) — this only owns the concurrency
control around "check cache, and if it's a miss, fetch-and-cache", via two
caller-supplied functions. Locks are per-key (not global) so unrelated keys
(e.g. two different search queries) don't block each other.
"""
import threading


class SingleFlightCache:
    def __init__(self):
        self._locks = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, key):
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def get_or_fetch(self, key, get_cached, fetch_and_cache, force_refresh=False):
        """Returns (value, source) where source is "cache" or "live".

        get_cached() -> cached value or None (a miss)
        fetch_and_cache() -> fetches live, writes to cache, returns the value
        """
        if not force_refresh:
            cached = get_cached()
            if cached is not None:
                return cached, "cache"

        lock = self._lock_for(key)
        with lock:
            # Re-check: whoever held the lock before us may have just filled
            # the cache with what we were about to fetch ourselves.
            if not force_refresh:
                cached = get_cached()
                if cached is not None:
                    return cached, "cache"
            return fetch_and_cache(), "live"
