"""LibraryRepo tests, mocking authenticate() and app.repos.library_repo.http.get
so these run with no network access and no real library credentials.
"""
import sqlite3
import threading
import time
from unittest.mock import patch

import pytest

from app.repos.library_repo import LibraryRepo

# Mirrors a real capture (three "Pacific Rim" bibs, same title/year,
# distinguished only by catalogBibs' brief.edition — see search.md's
# disambiguation note).
CATALOG_BIB_RESPONSE = {
    "entities": {
        "catalogBibs": {
            "B1": {
                "brief": {
                    "edition": "Two-disc special edition.",
                    "description": "A war rages between humanity and monstrous creatures.",
                },
                "fields": [
                    {
                        "category": "DETAILS",
                        "items": [
                            {
                                "fieldName": "PUBLICATION",
                                "fieldValues": [
                                    {"primary": {"values": ["Burbank, CA : Warner Bros. Entertainment, c2013."]}}
                                ],
                            }
                        ],
                    }
                ],
            }
        }
    }
}

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
        # Isolated per test — must never read/write the real shared cache
        # file that scripts/library/auth.sh also uses.
        auth_cache_path=tmp_path / "auth_cache",
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
        auth_cache_path=tmp_path / "auth_cache",
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


def test_search_extracts_jacket_url_large_for_the_hover_zoom_preview(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        records, _ = repo.search("terminator", "DVD")

    by_id = {r["bib_id"]: r for r in records}
    assert by_id["B1"]["jacket_url_large"] == "https://secure.syndetics.com/index.aspx?isbn=X/LC.JPG"  # "large" preferred
    assert by_id["B2"]["jacket_url_large"] is None  # no jacket in the fixture at all


def test_jacket_urls_survive_a_cache_round_trip(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        repo.search("terminator", "DVD")
        cached_records, source = repo.search("terminator", "DVD")

    assert source == "cache"
    by_id = {r["bib_id"]: r for r in cached_records}
    assert by_id["B1"]["jacket_url"] == "https://secure.syndetics.com/index.aspx?isbn=X/MC.GIF"
    assert by_id["B1"]["jacket_url_large"] == "https://secure.syndetics.com/index.aspx?isbn=X/LC.JPG"


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


def test_search_caches_empty_results_without_more_http_calls(repo):
    # A genuine "the library doesn't have this" response has no bibs to rank,
    # so _cache_set's per-record loop never runs — regression test for that
    # not silently meaning "never cached, keep hitting the live API".
    empty_response = {"catalogSearch": {"results": []}, "entities": {"bibs": {}}}
    call_count = {"n": 0}

    def counting_get(*args, **kwargs):
        call_count["n"] += 1
        return FakeResponse(empty_response)

    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", side_effect=counting_get):
        records, source = repo.search("christmas under wraps", "DVD")
        calls_after_first = call_count["n"]
        cached_records, cached_source = repo.search("christmas under wraps", "DVD")

    assert records == []
    assert source == "live"
    assert cached_records == []
    assert cached_source == "cache"
    assert call_count["n"] == calls_after_first


def test_search_query_whitespace_does_not_bust_cache(repo):
    call_count = {"n": 0}

    def counting_get(*args, **kwargs):
        call_count["n"] += 1
        return FakeResponse(SEARCH_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", side_effect=counting_get):
        repo.search("terminator", "DVD")
        calls_after_first = call_count["n"]
        records, source = repo.search("  terminator ", "DVD")

    assert source == "cache"
    assert call_count["n"] == calls_after_first
    assert len(records) == 2


def test_force_refresh_bypasses_cache(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        repo.search("terminator", "DVD")
        _, source = repo.search("terminator", "DVD", force_refresh=True)

    assert source == "live"


BRANCH_AVAILABILITY_RESPONSE = {
    "entities": {
        "bibItems": {
            "1370130|29|1": {
                "callNumber": "FLO DVD 791.43 GODZILLA",
                "branch": {"name": "Alpharetta Branch", "code": "ALPH"},
                "availability": {"status": "AVAILABLE"},
            },
            "1370130|39|1": {
                "callNumber": "FLO DVD 791.43 GODZILLA",
                "branch": {"name": "Milton Branch", "code": "MILTON"},
                "availability": {"status": "CHECKED_OUT"},
            },
        }
    }
}


def test_get_bib_branches_extracts_one_entry_per_physical_copy(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(BRANCH_AVAILABILITY_RESPONSE)):
        branches, source = repo.get_bib_branches("B1")

    assert source == "live"
    by_code = {b["branch_code"]: b for b in branches}
    assert by_code["ALPH"] == {
        "branch_name": "Alpharetta Branch", "branch_code": "ALPH",
        "status": "AVAILABLE", "call_number": "FLO DVD 791.43 GODZILLA",
    }
    assert by_code["MILTON"]["status"] == "CHECKED_OUT"


def test_get_bib_branches_caches_second_call_without_more_http_calls(repo):
    call_count = {"n": 0}

    def counting_get(*args, **kwargs):
        call_count["n"] += 1
        return FakeResponse(BRANCH_AVAILABILITY_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", side_effect=counting_get):
        repo.get_bib_branches("B1")
        calls_after_first = call_count["n"]
        branches, source = repo.get_bib_branches("B1")

    assert source == "cache"
    assert call_count["n"] == calls_after_first
    assert len(branches) == 2


def test_get_cached_branches_returns_none_when_never_fetched(repo):
    assert repo.get_cached_branches("B1") is None


def test_get_cached_branches_never_triggers_a_live_fetch(repo):
    with patch("app.repos.library_repo.http.get") as mock_get:
        assert repo.get_cached_branches("B1") is None
    mock_get.assert_not_called()


def test_get_cached_branches_returns_the_list_after_a_prior_live_fetch(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(BRANCH_AVAILABILITY_RESPONSE)):
        repo.get_bib_branches("B1")

    cached = repo.get_cached_branches("B1")
    assert len(cached) == 2
    assert {b["branch_code"] for b in cached} == {"ALPH", "MILTON"}


def test_get_bib_edition_extracts_edition_and_publication_note(repo):
    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(CATALOG_BIB_RESPONSE)):
        edition, source = repo.get_bib_edition("B1")

    assert source == "live"
    assert edition["edition"] == "Two-disc special edition."
    assert edition["publication_note"] == "Burbank, CA : Warner Bros. Entertainment, c2013."
    assert "monstrous creatures" in edition["description"]


def test_get_bib_edition_caches_second_call_without_more_http_calls(repo):
    call_count = {"n": 0}

    def counting_get(*args, **kwargs):
        call_count["n"] += 1
        return FakeResponse(CATALOG_BIB_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "session")), \
         patch("app.repos.library_repo.http.get", side_effect=counting_get):
        repo.get_bib_edition("B1")
        calls_after_first = call_count["n"]
        edition, source = repo.get_bib_edition("B1")

    assert source == "cache"
    assert call_count["n"] == calls_after_first
    assert edition["edition"] == "Two-disc special edition."


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
        # Force both caches to look expired without waiting AUTH_TTL_SECONDS for
        # real — the in-memory one AND the on-disk shared cache, since a fresh
        # login now only happens once neither has a still-valid entry (see
        # _get_auth's shared-file fallback).
        access_token, session_id, _ = repo._auth_cache
        repo._auth_cache = (access_token, session_id, 0)
        repo._write_shared_auth_cache(access_token, session_id, cached_at=0)
        repo.search("dune", "DVD")

    assert auth_calls["n"] == 2


def test_still_valid_shared_cache_file_avoids_a_fresh_login_even_if_memory_cache_is_stale(repo, tmp_path):
    """Regression test for the shared cache added to reduce real login
    volume (see scripts/discovery/auth.md's account-lock note) — a process
    restart (fresh LibraryRepo, empty in-memory cache) should NOT force a
    new login if another process/script already wrote a still-valid entry
    to the shared file."""
    auth_calls = {"n": 0}

    def counting_authenticate():
        auth_calls["n"] += 1
        return "token", "session"

    with patch.object(repo, "authenticate", side_effect=counting_authenticate), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        repo.search("terminator", "DVD")  # writes the shared cache file

    # Simulate a brand-new process: fresh instance, empty in-memory cache,
    # but pointed at the same shared cache file the first repo just wrote.
    fresh_repo = LibraryRepo(
        base_url="https://library.example", username="user", password="pw",
        agency="testagency", gateway_url="https://gateway.example",
        db_path=tmp_path / "library2.db",
        auth_cache_path=repo._auth_cache_path,
    )
    with patch.object(fresh_repo, "authenticate", side_effect=counting_authenticate), \
         patch("app.repos.library_repo.http.get", return_value=FakeResponse(SEARCH_RESPONSE)):
        fresh_repo.search("dune", "DVD")

    assert auth_calls["n"] == 1  # the second instance reused the shared file, no second login


def test_read_shared_auth_cache_returns_none_for_missing_file(repo):
    assert repo._read_shared_auth_cache() is None


def test_read_shared_auth_cache_returns_none_for_malformed_file(repo):
    repo._auth_cache_path.parent.mkdir(parents=True, exist_ok=True)
    repo._auth_cache_path.write_text("not the expected format at all\n")
    assert repo._read_shared_auth_cache() is None


def test_write_then_read_shared_auth_cache_round_trips(repo):
    repo._write_shared_auth_cache("tok-abc", "sess-xyz", cached_at=12345.0)
    assert repo._read_shared_auth_cache() == ("tok-abc", "sess-xyz", 12345.0)


def test_write_shared_auth_cache_sets_restrictive_permissions(repo):
    import stat

    repo._write_shared_auth_cache("tok-abc", "sess-xyz")
    mode = stat.S_IMODE(repo._auth_cache_path.stat().st_mode)
    assert mode == 0o600


def test_force_refresh_bypasses_shared_cache_even_if_valid(repo):
    repo._write_shared_auth_cache("stale-token", "stale-session", cached_at=time.time())
    with patch.object(repo, "authenticate", return_value=("fresh-token", "fresh-session")):
        access_token, session_id = repo._get_auth(force_refresh=True)
    # force_refresh must hit a real login, not the (still fresh) shared file
    assert (access_token, session_id) == ("fresh-token", "fresh-session")


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


CHECKOUTS_RESPONSE = {
    "entities": {
        "bibs": {
            "B1": {"briefInfo": {"format": "DVD", "title": "Ford V Ferrari"}},
            "B2": {"briefInfo": {"format": "BK", "title": "Empire of Storms"}},
        },
        "checkouts": {
            "C1": {"metadataId": "B1", "materialType": "PHYSICAL"},
            "C2": {"metadataId": "B2", "materialType": "PHYSICAL"},
        },
    },
    "borrowing": {"checkouts": {"items": ["C1", "C2"], "pagination": {"count": 2, "page": 1, "limit": 25, "pages": 1}}},
}

HOLDS_RESPONSE = {
    "entities": {
        "bibs": {
            "B3": {"briefInfo": {"format": "DVD", "title": "Paddington 2"}},
            "B4": {"briefInfo": {"format": "DVD", "title": "Captain America"}},
        },
        "holds": {
            "H1": {"metadataId": "B3", "materialType": "PHYSICAL"},
            "H2": {"metadataId": "B4", "materialType": "PHYSICAL"},
        },
    },
    "borrowing": {"holds": {"items": ["H1", "H2"], "pagination": {"count": 2, "page": 1, "limit": 25, "pages": 1}}},
}


def test_get_dvd_activity_count_joins_bibs_and_counts_dvds_only(repo):
    def routed_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/checkouts"):
            return FakeResponse(CHECKOUTS_RESPONSE)
        return FakeResponse(HOLDS_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "sess-3006586696")), \
         patch("app.repos.library_repo.http.get", side_effect=routed_get):
        summary, source = repo.get_dvd_activity_count()

    assert source == "live"
    assert summary == {"checked_out": 1, "on_hold": 2, "total": 3}  # only DVD-format items count


def test_get_dvd_activity_count_derives_account_id_as_session_suffix_plus_one(repo):
    captured_account_ids = []

    def capturing_get(url, headers=None, params=None, timeout=None):
        captured_account_ids.append(params["accountId"])
        return FakeResponse(CHECKOUTS_RESPONSE if url.endswith("/checkouts") else HOLDS_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "sess-3006586696")), \
         patch("app.repos.library_repo.http.get", side_effect=capturing_get):
        repo.get_dvd_activity_count()

    assert all(account_id == 3006586697 for account_id in captured_account_ids)


def test_get_dvd_activity_count_second_call_hits_cache(repo):
    call_count = {"n": 0}

    def counting_get(url, headers=None, params=None, timeout=None):
        call_count["n"] += 1
        return FakeResponse(CHECKOUTS_RESPONSE if url.endswith("/checkouts") else HOLDS_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "sess-3006586696")), \
         patch("app.repos.library_repo.http.get", side_effect=counting_get):
        repo.get_dvd_activity_count()
        calls_after_first = call_count["n"]
        summary, source = repo.get_dvd_activity_count()

    assert source == "cache"
    assert call_count["n"] == calls_after_first
    assert summary == {"checked_out": 1, "on_hold": 2, "total": 3}


def test_get_dvd_activity_count_force_refresh_bypasses_cache(repo):
    with patch.object(repo, "authenticate", return_value=("token", "sess-3006586696")), \
         patch(
             "app.repos.library_repo.http.get",
             side_effect=lambda url, headers=None, params=None, timeout=None: (
                 FakeResponse(CHECKOUTS_RESPONSE) if url.endswith("/checkouts") else FakeResponse(HOLDS_RESPONSE)
             ),
         ):
        repo.get_dvd_activity_count()
        _, source = repo.get_dvd_activity_count(force_refresh=True)

    assert source == "live"


def test_get_dvd_activity_count_paginates_across_multiple_pages(repo):
    page1 = {
        "entities": {
            "bibs": {"B1": {"briefInfo": {"format": "DVD", "title": "A"}}},
            "checkouts": {"C1": {"metadataId": "B1", "materialType": "PHYSICAL"}},
        },
        "borrowing": {"checkouts": {"items": ["C1"], "pagination": {"count": 2, "page": 1, "limit": 1, "pages": 2}}},
    }
    page2 = {
        "entities": {
            "bibs": {"B2": {"briefInfo": {"format": "DVD", "title": "B"}}},
            "checkouts": {"C2": {"metadataId": "B2", "materialType": "PHYSICAL"}},
        },
        "borrowing": {"checkouts": {"items": ["C2"], "pagination": {"count": 2, "page": 2, "limit": 1, "pages": 2}}},
    }
    empty_holds = {"entities": {"bibs": {}, "holds": {}}, "borrowing": {"holds": {"items": [], "pagination": {"count": 0, "page": 1, "limit": 25, "pages": 1}}}}

    def routed_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/holds"):
            return FakeResponse(empty_holds)
        return FakeResponse(page1 if params["page"] == 1 else page2)

    with patch.object(repo, "authenticate", return_value=("token", "sess-3006586696")), \
         patch("app.repos.library_repo.http.get", side_effect=routed_get):
        summary, _ = repo.get_dvd_activity_count()

    assert summary["checked_out"] == 2  # both pages' DVDs counted


def test_get_dvd_activity_count_401_triggers_one_re_login_and_retry(repo):
    auth_calls = {"n": 0}

    def counting_authenticate():
        auth_calls["n"] += 1
        return f"token-{auth_calls['n']}", "sess-3006586696"

    empty_holds = {"entities": {"bibs": {}, "holds": {}}, "borrowing": {"holds": {"items": [], "pagination": {"count": 0, "page": 1, "limit": 25, "pages": 1}}}}
    checkouts_responses = iter([FakeResponse({}, status_code=401), FakeResponse(CHECKOUTS_RESPONSE)])

    def routed_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/checkouts"):
            return next(checkouts_responses)
        return FakeResponse(empty_holds)

    with patch.object(repo, "authenticate", side_effect=counting_authenticate), \
         patch("app.repos.library_repo.http.get", side_effect=routed_get):
        summary, source = repo.get_dvd_activity_count()

    assert auth_calls["n"] == 2
    assert source == "live"
    assert summary["checked_out"] == 1


HOLD_PLACED_RESPONSE = {
    "id": "S171C852280",
    "entities": {
        "holds": {
            "11939290": {
                "actions": ["cancel", "suspend", "updateLocation", "updateExpiry"],
                "metadataId": "S171C852280",
                "holdsId": "11939290",
                "bibTitle": "Pirates of the Caribbean, on stranger tides",
                "holdsPosition": 1,
                "status": "NOT_YET_AVAILABLE",
                "materialType": "PHYSICAL",
                "pickupLocation": {"code": "MILTON", "name": "Milton Branch", "ips": []},
                "holdPlacedDate": "2026-09-20",
                "expiryDate": "2027-07-17",
            }
        }
    },
    "successCount": 1,
}


def test_place_hold_sends_confirmed_body_shape(repo):
    captured = {}

    def capturing_post(url, headers=None, params=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse(HOLD_PLACED_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "sess-3006586696")), \
         patch("app.repos.library_repo.http.post", side_effect=capturing_post):
        result = repo.place_hold("S171C852280")

    assert captured["url"].endswith("/holds")
    assert captured["json"] == {
        "metadataId": "S171C852280",
        "materialType": "PHYSICAL",
        "accountId": 3006586697,
        "enableSingleClickHolds": False,
        "materialParams": {"branchId": "MILTON", "expiryDate": None, "errorMessageLocale": "en-US"},
    }
    assert result == {
        "hold_id": "11939290", "status": "NOT_YET_AVAILABLE",
        "expiry_date": "2027-07-17", "pickup_location": "Milton Branch",
    }


def test_place_hold_uses_explicit_branch_id_override(repo):
    captured = {}

    def capturing_post(url, headers=None, params=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse(HOLD_PLACED_RESPONSE)

    with patch.object(repo, "authenticate", return_value=("token", "sess-3006586696")), \
         patch("app.repos.library_repo.http.post", side_effect=capturing_post):
        repo.place_hold("S171C852280", branch_id="OTHER_BRANCH")

    assert captured["json"]["materialParams"]["branchId"] == "OTHER_BRANCH"


def test_place_hold_401_triggers_one_re_login_and_retry(repo):
    auth_calls = {"n": 0}

    def counting_authenticate():
        auth_calls["n"] += 1
        return f"token-{auth_calls['n']}", "sess-3006586696"

    responses = iter([FakeResponse({}, status_code=401), FakeResponse(HOLD_PLACED_RESPONSE)])

    with patch.object(repo, "authenticate", side_effect=counting_authenticate), \
         patch("app.repos.library_repo.http.post", side_effect=lambda *a, **k: next(responses)):
        result = repo.place_hold("S171C852280")

    assert auth_calls["n"] == 2
    assert result["hold_id"] == "11939290"


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
