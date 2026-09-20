"""Service-layer tests with fully mocked repos — these verify orchestration
logic (joining, validation, delegation), not the repos' own behavior (covered
in test_seerr_repo.py / test_library_repo.py / test_match_repo.py)."""
from unittest.mock import MagicMock

import pytest

from app.services.match_service import MatchService
from app.services.requests_service import RequestsService
from app.services.search_service import SearchService


def test_requests_service_joins_match_onto_matching_rows_only():
    seerr_repo = MagicMock()
    seerr_repo.list_requests.return_value = (
        [
            {"id": 1, "title": "A", "type": "movie", "tmdb_id": 100},
            {"id": 2, "title": "B", "type": "movie", "tmdb_id": 200},
        ],
        "live",
    )
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {1: {"bib_id": "X"}}
    tmdb_repo = MagicMock()
    tmdb_repo.get_many.return_value = {}

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    rows, source = service.get_requests("all")

    assert source == "live"
    assert rows[0]["match"] == {"bib_id": "X"}
    assert rows[1]["match"] is None


def test_requests_service_joins_tmdb_data_by_type_and_id():
    seerr_repo = MagicMock()
    seerr_repo.list_requests.return_value = (
        [
            {"id": 1, "title": "Dune", "type": "movie", "tmdb_id": 438631},
            {"id": 2, "title": "Brooklyn 99", "type": "tv", "tmdb_id": 4056},
        ],
        "live",
    )
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    tmdb_repo = MagicMock()
    tmdb_repo.get_many.return_value = {
        ("movie", 438631): {"director": "Denis Villeneuve"},
        ("tv", 4056): None,  # e.g. a failed lookup
    }

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    rows, _ = service.get_requests("all")

    assert rows[0]["tmdb"] == {"director": "Denis Villeneuve"}
    assert rows[1]["tmdb"] is None
    tmdb_repo.get_many.assert_called_once()
    assert set(tmdb_repo.get_many.call_args[0][0]) == {("movie", 438631), ("tv", 4056)}


def test_requests_service_passes_filter_and_refresh_through():
    seerr_repo = MagicMock()
    seerr_repo.list_requests.return_value = ([], "live")
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    tmdb_repo = MagicMock()
    tmdb_repo.get_many.return_value = {}

    RequestsService(seerr_repo, match_repo, tmdb_repo).get_requests("approved", force_refresh=True)

    seerr_repo.list_requests.assert_called_once_with("approved", force_refresh=True)


def test_stream_requests_replays_cached_rows_directly_without_live_fetch():
    seerr_repo = MagicMock()
    seerr_repo.get_cached_requests.return_value = [
        {"id": 1, "title": "A", "type": "movie", "tmdb_id": 100, "tmdb": {"director": "X"}},
        {"id": 2, "title": "B", "type": "movie", "tmdb_id": 200, "tmdb": None},
    ]
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {1: {"bib_id": "M1"}}
    tmdb_repo = MagicMock()

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    results = list(service.stream_requests("all"))

    assert [source for _, source in results] == ["cache", "cache"]
    rows = [row for row, _ in results]
    assert rows[0]["match"] == {"bib_id": "M1"}
    assert rows[0]["tmdb"] == {"director": "X"}
    assert rows[1]["match"] is None
    seerr_repo.fetch_raw_requests.assert_not_called()
    tmdb_repo.get.assert_not_called()  # cached rows already carry their tmdb data


def test_stream_requests_live_path_resolves_and_caches_full_set():
    seerr_repo = MagicMock()
    seerr_repo.get_cached_requests.return_value = None
    seerr_repo.fetch_raw_requests.return_value = [
        {"id": 1, "type": "movie", "status": 2, "media": {"tmdbId": 100, "status": 3}, "requestedBy": {"displayName": "Houston"}},
        {"id": 2, "type": "tv", "status": 1, "media": {"tmdbId": 200, "status": 2}, "requestedBy": {"displayName": "Houston"}},
    ]
    seerr_repo.fetch_title.side_effect = lambda media_type, tmdb_id: f"Title-{tmdb_id}"
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    tmdb_repo = MagicMock()
    tmdb_repo.get.side_effect = lambda media_type, tmdb_id: ({"tmdb_id": tmdb_id}, "live")

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    results = list(service.stream_requests("all"))

    assert len(results) == 2
    assert all(source == "live" for _, source in results)
    titles = {row["id"]: row["title"] for row, _ in results}
    assert titles == {1: "Title-100", 2: "Title-200"}

    # the full resolved set gets cached, tmdb data baked in, for next time's cache-hit replay
    seerr_repo.cache_requests.assert_called_once()
    cached_filter, cached_rows = seerr_repo.cache_requests.call_args[0]
    assert cached_filter == "all"
    assert {r["id"] for r in cached_rows} == {1, 2}
    assert all("tmdb" in r for r in cached_rows)


def test_stream_requests_isolates_a_single_tmdb_failure():
    seerr_repo = MagicMock()
    seerr_repo.get_cached_requests.return_value = None
    seerr_repo.fetch_raw_requests.return_value = [
        {"id": 1, "type": "movie", "status": 2, "media": {"tmdbId": 100, "status": 3}, "requestedBy": {"displayName": "H"}},
    ]
    seerr_repo.fetch_title.return_value = "Some Movie"
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    tmdb_repo = MagicMock()
    tmdb_repo.get.side_effect = ConnectionError("simulated TMDB failure")

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    results = list(service.stream_requests("all"))

    assert len(results) == 1
    row, source = results[0]
    assert source == "live"
    assert row["tmdb"] is None  # failure isolated, not raised


def test_stream_requests_force_refresh_skips_cache():
    seerr_repo = MagicMock()
    seerr_repo.fetch_raw_requests.return_value = []
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    tmdb_repo = MagicMock()

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    list(service.stream_requests("all", force_refresh=True))

    seerr_repo.get_cached_requests.assert_not_called()
    seerr_repo.fetch_raw_requests.assert_called_once_with("all")


def test_search_service_rejects_empty_query():
    service = SearchService(MagicMock())
    with pytest.raises(ValueError):
        service.search("")


def test_search_service_delegates_to_repo():
    library_repo = MagicMock()
    library_repo.search.return_value = ([{"bib_id": "B1"}], "cache")

    service = SearchService(library_repo)
    records, source = service.search("dune", "DVD", force_refresh=True)

    library_repo.search.assert_called_once_with("dune", "DVD", force_refresh=True)
    assert source == "cache"
    assert records == [{"bib_id": "B1"}]


def test_match_service_save_passes_all_fields_through():
    match_repo = MagicMock()
    MatchService(match_repo).save_match({
        "request_id": 1, "tmdb_id": 100, "media_type": "movie",
        "seerr_title": "A", "bib_id": "B1", "bib_title": "A", "bib_subtitle": "",
    })

    match_repo.set_match.assert_called_once_with(
        request_id=1, tmdb_id=100, media_type="movie",
        seerr_title="A", bib_id="B1", bib_title="A", bib_subtitle="",
    )


def test_match_service_save_defaults_missing_optional_fields_to_none():
    match_repo = MagicMock()
    MatchService(match_repo).save_match({"request_id": 1})

    match_repo.set_match.assert_called_once_with(
        request_id=1, tmdb_id=None, media_type=None,
        seerr_title=None, bib_id=None, bib_title=None, bib_subtitle=None,
    )


def test_match_service_clear_delegates_to_repo():
    match_repo = MagicMock()
    MatchService(match_repo).clear_match(5)

    match_repo.clear_match.assert_called_once_with(5)


def test_match_service_mark_unavailable_passes_fields_through():
    match_repo = MagicMock()
    MatchService(match_repo).mark_unavailable({
        "request_id": 1, "tmdb_id": 100, "media_type": "movie", "seerr_title": "A",
    })

    match_repo.set_unavailable.assert_called_once_with(
        request_id=1, tmdb_id=100, media_type="movie", seerr_title="A",
    )


def test_match_service_mark_unavailable_defaults_missing_optional_fields_to_none():
    match_repo = MagicMock()
    MatchService(match_repo).mark_unavailable({"request_id": 1})

    match_repo.set_unavailable.assert_called_once_with(
        request_id=1, tmdb_id=None, media_type=None, seerr_title=None,
    )
