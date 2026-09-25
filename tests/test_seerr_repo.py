"""SeerrRepo tests, mocking app.repos.seerr_repo.http.get so these run with
no network access and no real SEERR_BASE_URL/SEERR_API_KEY. The concurrency
test here is a regression test for a real bug caught during development:
sqlite3.Connection is NOT safe for concurrent use from multiple threads even
with check_same_thread=False — see the _db_lock in SeerrRepo.
"""
import threading
from unittest.mock import patch

import pytest

from app.repos.seerr_repo import SeerrRepo

REQUEST_PAGE = {
    "pageInfo": {"results": 2, "pages": 1, "page": 1, "pageSize": 50},
    "results": [
        {
            "id": 1,
            "status": 2,
            "type": "movie",
            "media": {"tmdbId": 100, "status": 3},
            "requestedBy": {"displayName": "Alice"},
        },
        {
            "id": 2,
            "status": 1,
            "type": "tv",
            "media": {"tmdbId": 200, "status": 2},
            "requestedBy": {"displayName": "Bob"},
            "seasons": [{"seasonNumber": 1, "status": 2}, {"seasonNumber": 2, "status": 2}],
        },
    ],
}


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def fake_get(url, headers=None, params=None, timeout=None):
    if url.endswith("/api/v1/request"):
        return FakeResponse(REQUEST_PAGE)
    if url.endswith("/api/v1/movie/100"):
        return FakeResponse({"title": "Movie A"})
    if url.endswith("/api/v1/tv/200"):
        return FakeResponse({"name": "Show B"})
    raise AssertionError(f"unexpected URL in test: {url}")


@pytest.fixture
def repo(tmp_path):
    return SeerrRepo(base_url="https://seerr.example", api_key="test-key", db_path=tmp_path / "seerr.db")


def test_list_requests_resolves_titles_and_shapes_rows(repo):
    with patch("app.repos.seerr_repo.http.get", side_effect=fake_get):
        rows, source = repo.list_requests("all")

    assert source == "live"
    assert rows == [
        {
            "id": 1, "type": "movie", "tmdb_id": 100, "title": "Movie A",
            "request_status": 2, "media_status": 3, "requested_by": "Alice", "seasons": [],
        },
        {
            "id": 2, "type": "tv", "tmdb_id": 200, "title": "Show B",
            "request_status": 1, "media_status": 2, "requested_by": "Bob", "seasons": [1, 2],
        },
    ]


def test_second_call_within_ttl_hits_cache_without_more_http_calls(repo):
    call_count = {"n": 0}

    def counting_get(*args, **kwargs):
        call_count["n"] += 1
        return fake_get(*args, **kwargs)

    with patch("app.repos.seerr_repo.http.get", side_effect=counting_get):
        repo.list_requests("all")
        calls_after_first = call_count["n"]
        rows, source = repo.list_requests("all")

    assert source == "cache"
    assert call_count["n"] == calls_after_first  # no additional HTTP calls
    assert len(rows) == 2


def test_expired_ttl_refetches(repo):
    with patch("app.repos.seerr_repo.http.get", side_effect=fake_get):
        repo.list_requests("all", ttl=0)  # immediately stale
        rows, source = repo.list_requests("all", ttl=0)

    assert source == "live"


def test_force_refresh_bypasses_cache(repo):
    with patch("app.repos.seerr_repo.http.get", side_effect=fake_get):
        repo.list_requests("all")
        rows, source = repo.list_requests("all", force_refresh=True)

    assert source == "live"


def test_different_filters_cache_independently(repo):
    with patch("app.repos.seerr_repo.http.get", side_effect=fake_get):
        _, source_a = repo.list_requests("all")
        _, source_b = repo.list_requests("approved")

    assert source_a == "live"
    assert source_b == "live"  # different cache key, not a hit off "all"'s entry


def test_create_request_for_movie_omits_seasons(repo):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"id": 42, "media": {"status": 2}})

    with patch("app.repos.seerr_repo.http.post", side_effect=fake_post):
        result = repo.create_request("movie", 438631)

    assert captured["url"].endswith("/api/v1/request")
    assert captured["json"] == {"mediaType": "movie", "mediaId": 438631}
    assert result == {"id": 42, "media_status": 2}


def test_create_request_for_tv_defaults_seasons_to_all(repo):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse({"id": 43, "media": {"status": 2}})

    with patch("app.repos.seerr_repo.http.post", side_effect=fake_post):
        repo.create_request("tv", 4056)

    assert captured["json"] == {"mediaType": "tv", "mediaId": 4056, "seasons": "all"}


def test_create_request_for_tv_passes_explicit_seasons_through(repo):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse({"id": 44, "media": {"status": 2}})

    with patch("app.repos.seerr_repo.http.post", side_effect=fake_post):
        repo.create_request("tv", 4056, seasons=[1, 2])

    assert captured["json"] == {"mediaType": "tv", "mediaId": 4056, "seasons": [1, 2]}


def test_concurrent_calls_for_same_filter_are_thread_safe_and_single_flight(repo, monkeypatch):
    # Forces the live path to take long enough that 5 threads reliably race —
    # without this, the bug (and the fix) would be flaky to observe.
    monkeypatch.setenv("SEERR_TEST_FETCH_DELAY_SECONDS", "0.3")

    results = []
    results_lock = threading.Lock()
    errors = []

    def worker():
        try:
            result = repo.list_requests("all")
            with results_lock:
                results.append(result)
        except Exception as e:  # noqa: BLE001 - want to see any thread-safety exception
            errors.append(e)

    with patch("app.repos.seerr_repo.http.get", side_effect=fake_get):
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert errors == []  # regression check: used to raise sqlite3.InterfaceError
    sources = [source for _, source in results]
    assert sources.count("live") == 1
    assert sources.count("cache") == 4
    assert all(len(rows) == 2 for rows, _ in results)
