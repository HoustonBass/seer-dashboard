"""Service-layer tests with fully mocked repos — these verify orchestration
logic (joining, validation, delegation), not the repos' own behavior (covered
in test_seerr_repo.py / test_library_repo.py / test_match_repo.py)."""
from unittest.mock import MagicMock

import pytest

from app.repos.match_repo import WHOLE_ITEM_SEASON
from app.services.account_service import AccountService
from app.services.hold_service import HoldService
from app.services.match_service import MatchService
from app.services.quick_add_service import QuickAddError, QuickAddService
from app.services.requests_service import RequestsService
from app.services.search_service import SearchService


def test_requests_service_joins_whole_item_match_onto_matching_rows_only():
    seerr_repo = MagicMock()
    seerr_repo.list_requests.return_value = (
        [
            {"id": 1, "title": "A", "type": "movie", "tmdb_id": 100},
            {"id": 2, "title": "B", "type": "movie", "tmdb_id": 200},
        ],
        "live",
    )
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {1: {WHOLE_ITEM_SEASON: {"bib_id": "X"}}}
    tmdb_repo = MagicMock()
    tmdb_repo.get_many.return_value = {}

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    rows, source = service.get_requests("all")

    assert source == "live"
    assert rows[0]["match"] == {"bib_id": "X"}
    assert rows[1]["match"] is None


def test_requests_service_joins_season_matches_for_tv():
    seerr_repo = MagicMock()
    seerr_repo.list_requests.return_value = (
        [{"id": 1, "title": "Brooklyn 99", "type": "tv", "tmdb_id": 100, "seasons": [1, 2, 3]}],
        "live",
    )
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {
        1: {1: {"bib_id": "S1", "status": "matched"}, 4: {"status": "unavailable"}},
    }
    tmdb_repo = MagicMock()
    tmdb_repo.get_many.return_value = {}

    service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    rows, _ = service.get_requests("all")

    # TV rows never have a whole-item (season 0) match — season_matches carries everything.
    assert rows[0]["match"] is None
    assert rows[0]["season_matches"] == {1: {"bib_id": "S1", "status": "matched"}, 4: {"status": "unavailable"}}


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
    match_repo.get_all_matches.return_value = {1: {WHOLE_ITEM_SEASON: {"bib_id": "M1"}}}
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
    service = SearchService(MagicMock(), MagicMock())
    with pytest.raises(ValueError):
        service.search("")


def test_search_service_delegates_to_repo():
    library_repo = MagicMock()
    library_repo.search.return_value = ([{"bib_id": "B1"}], "cache")
    match_repo = MagicMock()
    match_repo.get_matches_by_bib_ids.return_value = {}

    service = SearchService(library_repo, match_repo)
    records, source = service.search("dune", "DVD", force_refresh=True)

    library_repo.search.assert_called_once_with("dune", "DVD", force_refresh=True)
    assert source == "cache"
    assert records == [{"bib_id": "B1", "existing_match": None}]


def test_search_service_flags_results_already_matched_to_a_different_request():
    library_repo = MagicMock()
    library_repo.search.return_value = (
        [{"bib_id": "B1"}, {"bib_id": "B2"}],
        "live",
    )
    match_repo = MagicMock()
    match_repo.get_matches_by_bib_ids.return_value = {
        "B2": {"request_id": 42, "seerr_title": "Despicable Me 4", "media_type": "movie", "bib_id": "B2"},
    }

    service = SearchService(library_repo, match_repo)
    records, _ = service.search("despicable me 2")

    assert set(match_repo.get_matches_by_bib_ids.call_args[0][0]) == {"B1", "B2"}
    assert records[0]["existing_match"] is None
    assert records[1]["existing_match"] == {"request_id": 42, "seerr_title": "Despicable Me 4", "media_type": "movie"}


def test_match_service_save_passes_all_fields_through():
    match_repo = MagicMock()
    MatchService(match_repo).save_match({
        "request_id": 1, "season_number": 2, "tmdb_id": 100, "media_type": "tv",
        "seerr_title": "A", "bib_id": "B1", "bib_title": "A", "bib_subtitle": "Season Two",
        "availability_status": "AVAILABLE",
    })

    match_repo.set_match.assert_called_once_with(
        request_id=1, season_number=2, tmdb_id=100, media_type="tv",
        seerr_title="A", bib_id="B1", bib_title="A", bib_subtitle="Season Two",
        availability_status="AVAILABLE",
    )


def test_match_service_save_defaults_missing_optional_fields_including_season(tmp_path):
    match_repo = MagicMock()
    MatchService(match_repo).save_match({"request_id": 1})

    match_repo.set_match.assert_called_once_with(
        request_id=1, season_number=WHOLE_ITEM_SEASON, tmdb_id=None, media_type=None,
        seerr_title=None, bib_id=None, bib_title=None, bib_subtitle=None, availability_status=None,
    )


def test_match_service_clear_delegates_to_repo_with_whole_item_season_by_default():
    match_repo = MagicMock()
    MatchService(match_repo).clear_match(5)

    match_repo.clear_match.assert_called_once_with(5, WHOLE_ITEM_SEASON)


def test_match_service_clear_passes_explicit_season_through():
    match_repo = MagicMock()
    MatchService(match_repo).clear_match(5, 2)

    match_repo.clear_match.assert_called_once_with(5, 2)


def test_match_service_mark_unavailable_passes_fields_through():
    match_repo = MagicMock()
    MatchService(match_repo).mark_unavailable({
        "request_id": 1, "season_number": 3, "tmdb_id": 100, "media_type": "tv", "seerr_title": "A",
    })

    match_repo.set_unavailable.assert_called_once_with(
        request_id=1, season_number=3, tmdb_id=100, media_type="tv", seerr_title="A",
    )


def test_match_service_mark_unavailable_defaults_missing_optional_fields_including_season():
    match_repo = MagicMock()
    MatchService(match_repo).mark_unavailable({"request_id": 1})

    match_repo.set_unavailable.assert_called_once_with(
        request_id=1, season_number=WHOLE_ITEM_SEASON, tmdb_id=None, media_type=None, seerr_title=None,
    )


def test_account_service_delegates_to_library_repo():
    library_repo = MagicMock()
    library_repo.get_dvd_activity_count.return_value = ({"checked_out": 1, "on_hold": 2, "total": 3}, "cache")

    service = AccountService(library_repo)
    summary, source = service.get_dvd_activity_count(force_refresh=True)

    library_repo.get_dvd_activity_count.assert_called_once_with(force_refresh=True)
    assert summary == {"checked_out": 1, "on_hold": 2, "total": 3}
    assert source == "cache"


def test_hold_service_places_hold_and_records_id_against_the_match():
    library_repo = MagicMock()
    library_repo.place_hold.return_value = {
        "hold_id": "11939290", "status": "NOT_YET_AVAILABLE",
        "expiry_date": "2027-07-17", "pickup_location": "Milton Branch",
    }
    match_repo = MagicMock()

    service = HoldService(library_repo, match_repo)
    result = service.place_hold({"request_id": 254, "bib_id": "S171C852280"})

    library_repo.place_hold.assert_called_once_with("S171C852280", branch_id=None)
    match_repo.set_hold_id.assert_called_once_with(254, WHOLE_ITEM_SEASON, "11939290")
    assert result["hold_id"] == "11939290"


def test_hold_service_passes_season_number_and_branch_id_through():
    library_repo = MagicMock()
    library_repo.place_hold.return_value = {"hold_id": "H1", "status": "IN_TRANSIT", "expiry_date": None, "pickup_location": None}
    match_repo = MagicMock()

    service = HoldService(library_repo, match_repo)
    service.place_hold({"request_id": 205, "season_number": 1, "bib_id": "B2", "branch_id": "OTHER"})

    library_repo.place_hold.assert_called_once_with("B2", branch_id="OTHER")
    match_repo.set_hold_id.assert_called_once_with(205, 1, "H1")


def test_quick_add_service_rejects_empty_query():
    service = QuickAddService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    with pytest.raises(ValueError):
        service.search_candidates("")


def test_quick_add_service_search_delegates_to_tmdb_repo():
    tmdb_repo = MagicMock()
    tmdb_repo.search.return_value = [{"tmdb_id": 1, "media_type": "movie", "title": "Dune"}]

    service = QuickAddService(tmdb_repo, MagicMock(), MagicMock(), MagicMock())
    results = service.search_candidates("dune")

    tmdb_repo.search.assert_called_once_with("dune")
    assert results == [{"tmdb_id": 1, "media_type": "movie", "title": "Dune"}]


def test_quick_add_service_creates_request_then_saves_match_for_movie():
    tmdb_repo = MagicMock()
    seerr_repo = MagicMock()
    seerr_repo.create_request.return_value = {"id": 99, "media_status": 2}
    match_repo = MagicMock()

    service = QuickAddService(tmdb_repo, seerr_repo, match_repo, MagicMock())
    result = service.add_and_match(
        {
            "media_type": "movie", "tmdb_id": 438631, "title": "Dune",
            "bib_id": "B1", "bib_title": "Dune", "bib_subtitle": None,
        }
    )

    seerr_repo.create_request.assert_called_once_with("movie", 438631, seasons=None)
    match_repo.set_match.assert_called_once_with(
        request_id=99, season_number=WHOLE_ITEM_SEASON, tmdb_id=438631, media_type="movie",
        seerr_title="Dune", bib_id="B1", bib_title="Dune", bib_subtitle=None,
    )
    assert result == {"request_id": 99}


def test_quick_add_service_creates_tv_request_without_matching_when_bib_id_omitted():
    tmdb_repo = MagicMock()
    seerr_repo = MagicMock()
    seerr_repo.create_request.return_value = {"id": 101, "media_status": 2}
    match_repo = MagicMock()

    service = QuickAddService(tmdb_repo, seerr_repo, match_repo, MagicMock())
    result = service.add_and_match({"media_type": "tv", "tmdb_id": 4056, "title": "Brooklyn 99"})

    seerr_repo.create_request.assert_called_once_with("tv", 4056, seasons=None)
    match_repo.set_match.assert_not_called()
    assert result == {"request_id": 101}


def test_quick_add_service_creates_tv_request_with_seasons_and_matches_specific_season():
    tmdb_repo = MagicMock()
    seerr_repo = MagicMock()
    seerr_repo.create_request.return_value = {"id": 100, "media_status": 2}
    match_repo = MagicMock()

    service = QuickAddService(tmdb_repo, seerr_repo, match_repo, MagicMock())
    service.add_and_match(
        {
            "media_type": "tv", "tmdb_id": 4056, "seasons": [1, 2], "season_number": 1,
            "title": "Brooklyn 99", "bib_id": "B2", "bib_title": "Brooklyn 99", "bib_subtitle": "Season One",
        }
    )


def test_quick_add_service_records_failure_and_raises_when_create_request_fails():
    tmdb_repo = MagicMock()
    seerr_repo = MagicMock()
    seerr_repo.create_request.side_effect = ConnectionError("Overseerr unreachable")
    match_repo = MagicMock()
    failed_repo = MagicMock()
    failed_repo.record_new_failure.return_value = 7

    service = QuickAddService(tmdb_repo, seerr_repo, match_repo, failed_repo)
    payload = {"media_type": "movie", "tmdb_id": 17529, "title": "True Grit", "bib_id": "B3"}

    with pytest.raises(QuickAddError) as exc_info:
        service.add_and_match(payload)

    failed_repo.record_new_failure.assert_called_once_with(payload, "Overseerr unreachable")
    match_repo.set_match.assert_not_called()
    assert exc_info.value.failed_id == 7


def test_quick_add_service_retry_failed_succeeds_and_deletes_the_row():
    tmdb_repo = MagicMock()
    seerr_repo = MagicMock()
    seerr_repo.create_request.return_value = {"id": 55, "media_status": 2}
    match_repo = MagicMock()
    failed_repo = MagicMock()
    failed_repo.get.return_value = {
        "id": 7,
        "payload": {"media_type": "movie", "tmdb_id": 17529, "title": "True Grit", "bib_id": "B3", "bib_title": "True Grit", "bib_subtitle": ""},
    }

    service = QuickAddService(tmdb_repo, seerr_repo, match_repo, failed_repo)
    result = service.retry_failed(7)

    seerr_repo.create_request.assert_called_once_with("movie", 17529, seasons=None)
    failed_repo.delete.assert_called_once_with(7)
    assert result == {"request_id": 55}


def test_quick_add_service_retry_failed_records_retry_failure_when_still_unreachable():
    tmdb_repo = MagicMock()
    seerr_repo = MagicMock()
    seerr_repo.create_request.side_effect = ConnectionError("still down")
    match_repo = MagicMock()
    failed_repo = MagicMock()
    failed_repo.get.return_value = {
        "id": 7,
        "payload": {"media_type": "movie", "tmdb_id": 17529, "title": "True Grit"},
    }

    service = QuickAddService(tmdb_repo, seerr_repo, match_repo, failed_repo)

    with pytest.raises(QuickAddError):
        service.retry_failed(7)

    failed_repo.record_retry_failure.assert_called_once_with(7, "still down")
    failed_repo.delete.assert_not_called()


def test_quick_add_service_retry_failed_raises_value_error_for_unknown_id():
    failed_repo = MagicMock()
    failed_repo.get.return_value = None
    service = QuickAddService(MagicMock(), MagicMock(), MagicMock(), failed_repo)

    with pytest.raises(ValueError):
        service.retry_failed(999)
