"""LibraryRepo tests, mocking authenticate() and app.repos.library_repo.http.get
so these run with no network access and no real library credentials.
"""
import sqlite3
import threading
from unittest.mock import patch

import pytest

from app.repos.library_repo import LibraryRepo

# Mirrors the real ambiguity documented in scripts/discovery/search.md:
# searching "terminator" should rank "The Terminator" (exact full-title
# match) above "Terminator: Dark Fate" (only the bare title matches).
SEARCH_RESPONSE = {
    "catalogSearch": {"results": [{"representative": "B1"}, {"representative": "B2"}]},
    "entities": {
        "bibs": {
            "B1": {
                "id": "B1",
                "briefInfo": {
                    "title": "The Terminator",
                    "subtitle": "",
                    "format": "DVD",
                    "publicationDate": "2004",
                    "callNumber": "DVD 1",
                    "authors": [],
                    "jacket": {
                        "type": "SYNDETICS",
                        "small": "https://secure.syndetics.com/index.aspx?isbn=X/SC.GIF",
                        "medium": "https://secure.syndetics.com/index.aspx?isbn=X/MC.GIF",
                        "large": "https://secure.syndetics.com/index.aspx?isbn=X/LC.JPG",
                    },
                },
                "availability": {"status": "AVAILABLE", "availableCopies": 2, "totalCopies": 3},
            },
            "B2": {
                "id": "B2",
                "briefInfo": {
                    "title": "Terminator",
                    "subtitle": "Dark Fate",
                    "format": "DVD",
                    "publicationDate": "2019",
                    "callNumber": "DVD 2",
                    "authors": [],
                },
                "availability": {"status": "AVAILABLE", "availableCopies": 9, "totalCopies": 9},
            },
        }
    },
}


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


@pytest.fixture
def repo(tmp_path):
    return LibraryRepo(
        base_url="https://library.example",
        username="user",
        password="pw",
        agency="testagency",
        gateway_url="https://gateway.example",
        db_path=tmp_path / "library.db",
    )


def test_migrates_pre_existing_db_missing_jacket_url_column(tmp_path):
    db_path = tmp_path / "old_schema.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE bibs (
            bib_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            subtitle TEXT,
            format TEXT,
            availability_status TEXT,
            available_copies INTEGER,
            total_copies INTEGER,
            publication_date TEXT,
            call_number TEXT,
            authors TEXT,
            match_score INTEGER,
            fetched_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    # Should not raise — the missing column gets added, not crash on open.
    repo = LibraryRepo(
        base_url="https://library.example", username="u", password="p", db_path=db_path,
    )
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        records, _ = repo.search("terminator", "DVD")

    assert records[0]["jacket_url"] is not None
    assert records[0]["record_url"] is not None


def test_search_builds_public_record_url_from_base_url_and_bib_id(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        records, _ = repo.search("terminator", "DVD")

    by_id = {r["bib_id"]: r for r in records}
    assert by_id["B1"]["record_url"] == "https://library.example/v2/record/B1"
    assert by_id["B2"]["record_url"] == "https://library.example/v2/record/B2"


def test_search_ranks_exact_title_match_above_bare_title_match(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        records, source = repo.search("terminator", "DVD")

    assert source == "live"
    assert [r["bib_id"] for r in records] == ["B1", "B2"]
    assert records[0]["match_score"] == 2  # "The Terminator" == normalize("terminator")
    assert records[1]["match_score"] == 1  # bare title "Terminator" also matches, but has a subtitle


def test_search_extracts_jacket_url_and_handles_missing_jacket(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        records, _ = repo.search("terminator", "DVD")

    by_id = {r["bib_id"]: r for r in records}
    assert by_id["B1"]["jacket_url"] == "https://secure.syndetics.com/index.aspx?isbn=X/MC.GIF"  # "medium" preferred
    assert by_id["B2"]["jacket_url"] is None  # no jacket in the fixture at all


def test_jacket_url_survives_a_cache_round_trip(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        repo.search("terminator", "DVD")
        cached_records, source = repo.search("terminator", "DVD")

    assert source == "cache"
    by_id = {r["bib_id"]: r for r in cached_records}
    assert by_id["B1"]["jacket_url"] == "https://secure.syndetics.com/index.aspx?isbn=X/MC.GIF"


def test_search_caches_second_call_without_more_http_calls(repo):
    call_count = {"n": 0}

    def counting_get(*args, **kwargs):
        call_count["n"] += 1
        return FakeResponse(SEARCH_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", side_effect=counting_get):
        repo.search("terminator", "DVD")
        calls_after_first = call_count["n"]
        records, source = repo.search("terminator", "DVD")

    assert source == "cache"
    assert call_count["n"] == calls_after_first


def test_force_refresh_bypasses_cache(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        repo.search("terminator", "DVD")
        _, source = repo.search("terminator", "DVD", force_refresh=True)

    assert source == "live"


def test_concurrent_search_is_thread_safe_and_single_flight(repo, monkeypatch):
    monkeypatch.setenv("LIBRARY_TEST_FETCH_DELAY_SECONDS", "0.3")

    results = []
    results_lock = threading.Lock()
    errors = []

    def worker():
        try:
            result = repo.search("terminator", "DVD")
            with results_lock:
                results.append(result)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert errors == []
    sources = [source for _, source in results]
    assert sources.count("live") == 1
    assert sources.count("cache") == 4


def test_auth_is_reused_across_distinct_searches_within_ttl(repo):
    auth_calls = {"n": 0}

    def counting_authenticate():
        auth_calls["n"] += 1
        return "token", "session"

    with patch.object(repo, "authenticate", side_effect=counting_authenticate), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        repo.search("terminator", "DVD")       # cache miss #1 -> authenticate
        repo.search("dune", "DVD")             # different cache key, still a cache miss...
        repo.search("terminator", "DVD")       # ...but this is a search cache hit, no auth either way

    # Two distinct searches were live-fetched, but only one login happened.
    assert auth_calls["n"] == 1


def test_expired_auth_cache_triggers_a_fresh_login(repo, monkeypatch):
    auth_calls = {"n": 0}

    def counting_authenticate():
        auth_calls["n"] += 1
        return "token", "session"

    with patch.object(repo, "authenticate", side_effect=counting_authenticate), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        repo.search("terminator", "DVD")
        # Force the cached auth to look expired without waiting AUTH_TTL_SECONDS for real.
        access_token, session_id, _ = repo._auth_cache
        repo._auth_cache = (access_token, session_id, 0)
        repo.search("dune", "DVD")

    assert auth_calls["n"] == 2


def test_401_from_search_triggers_one_re_login_and_retry(repo):
    auth_calls = {"n": 0}

    def counting_authenticate():
        auth_calls["n"] += 1
        return f"token-{auth_calls['n']}", "session"

    responses = iter([
        FakeResponse({}, status_code=401),          # cached (stale) token rejected
        FakeResponse(SEARCH_RESPONSE, status_code=200),  # retry with fresh token succeeds
    ])

    with patch.object(repo, "authenticate", side_effect=counting_authenticate), \
         patch("app.repos.library_repo.http.get", side_effect=lambda *a, **k: next(responses)):
        records, source = repo.search("terminator", "DVD")

    assert auth_calls["n"] == 2  # initial login + one forced re-login after the 401
    assert source == "live"
    assert len(records) == 2


def test_authenticate_scrapes_csrf_token_and_reads_session_cookies(tmp_path):
    class FakeGetResponse:
        text = '<input name="authenticity_token" type="hidden" value="csrf-abc" />'

    class FakePostResponse:
        text = '{"logged_in":true,"success":true}'

    class FakeSession:
        def __init__(self):
            self.cookies = {"bc_access_token": "tok-123", "session_id": "sess-456"}
            self.post_calls = []

        def get(self, url, timeout=None):
            return FakeGetResponse()

        def post(self, url, headers=None, data=None, timeout=None):
            self.post_calls.append({"headers": headers, "data": data})
            return FakePostResponse()

    fake_session = FakeSession()
    repo = LibraryRepo(
        base_url="https://library.example", username="my-card", password="my-pin",
        db_path=tmp_path / "library.db",
    )

    with patch("app.repos.library_repo.http.Session", return_value=fake_session):
        access_token, session_id = repo.authenticate()

    assert access_token == "tok-123"
    assert session_id == "sess-456"
    # the CSRF token scraped from the login page must be echoed back correctly
    assert fake_session.post_calls[0]["headers"]["X-CSRF-Token"] == "csrf-abc"
    assert fake_session.post_calls[0]["data"]["authenticity_token"] == "csrf-abc"
    assert fake_session.post_calls[0]["data"]["name"] == "my-card"
    assert fake_session.post_calls[0]["data"]["user_pin"] == "my-pin"


def test_authenticate_raises_on_missing_csrf_token(tmp_path):
    class FakeSession:
        def get(self, url, timeout=None):
            class R:
                text = "<html>no csrf field here</html>"
            return R()

    repo = LibraryRepo(
        base_url="https://library.example", username="u", password="p",
        db_path=tmp_path / "library.db",
    )
    with patch("app.repos.library_repo.http.Session", return_value=FakeSession()):
        with pytest.raises(RuntimeError, match="authenticity_token"):
            repo.authenticate()


def test_authenticate_raises_on_failed_login(tmp_path):
    class FakeSession:
        cookies = {}

        def get(self, url, timeout=None):
            class R:
                text = '<input name="authenticity_token" type="hidden" value="csrf-abc" />'
            return R()

        def post(self, url, headers=None, data=None, timeout=None):
            class R:
                text = '{"logged_in":false,"success":false}'
            return R()

    repo = LibraryRepo(
        base_url="https://library.example", username="u", password="wrong-pin",
        db_path=tmp_path / "library.db",
    )
    with patch("app.repos.library_repo.http.Session", return_value=FakeSession()):
        with pytest.raises(RuntimeError, match="Login failed"):
            repo.authenticate()
