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
