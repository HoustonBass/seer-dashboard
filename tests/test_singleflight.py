"""SingleFlightCache is pure concurrency-control logic (no network/DB), so
these run fast with no mocking. This is the mechanism that makes
"only fetch once, concurrent callers wait for the cache" true across every
repo — see app/repos/seerr_repo.py and library_repo.py for real usage."""
import threading
import time

from app.lib.singleflight import SingleFlightCache


def test_concurrent_callers_for_same_key_only_fetch_once():
    cache = SingleFlightCache()
    store = {}
    fetch_count = {"n": 0}

    def get_cached():
        return store.get("k")

    def fetch_and_cache():
        fetch_count["n"] += 1
        time.sleep(0.2)  # wide enough for other threads to queue up behind the lock
        store["k"] = "value"
        return "value"

    results = []
    results_lock = threading.Lock()

    def worker():
        result = cache.get_or_fetch("k", get_cached, fetch_and_cache)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fetch_count["n"] == 1
    assert all(value == "value" for value, _ in results)
    sources = [source for _, source in results]
    assert sources.count("live") == 1
    assert sources.count("cache") == 9


def test_cache_hit_skips_fetch_entirely():
    cache = SingleFlightCache()
    calls = {"n": 0}

    def get_cached():
        return "already-cached"

    def fetch_and_cache():
        calls["n"] += 1
        return "should-not-happen"

    value, source = cache.get_or_fetch("k", get_cached, fetch_and_cache)

    assert value == "already-cached"
    assert source == "cache"
    assert calls["n"] == 0


def test_force_refresh_bypasses_cache_even_on_a_hit():
    cache = SingleFlightCache()

    def get_cached():
        return "stale"

    def fetch_and_cache():
        return "fresh"

    value, source = cache.get_or_fetch("k", get_cached, fetch_and_cache, force_refresh=True)

    assert value == "fresh"
    assert source == "live"


def test_different_keys_do_not_block_each_other():
    cache = SingleFlightCache()
    started = threading.Event()
    proceed = threading.Event()

    def slow_fetch():
        started.set()
        assert proceed.wait(timeout=2), "test setup failed: was not released in time"
        return "a"

    t = threading.Thread(target=lambda: cache.get_or_fetch("key-a", lambda: None, slow_fetch))
    t.start()
    assert started.wait(timeout=2), "key-a fetch never started"

    # key-b must not be blocked by key-a's still-in-flight fetch.
    value, source = cache.get_or_fetch("key-b", lambda: None, lambda: "b")
    assert (value, source) == ("b", "live")

    proceed.set()
    t.join(timeout=2)
