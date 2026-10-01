"""TmdbRepo tests, mocking app.repos.tmdb_repo.http.get so these run with no
network access and no real TMDB_API_KEY."""
from unittest.mock import patch

import pytest

from app.repos.tmdb_repo import TmdbRepo

MOVIE_RESPONSE = {
    "title": "Dune",
    "release_date": "2021-09-15",
    "overview": "Paul Atreides arrives on Arrakis...",
    "genres": [{"id": 878, "name": "Science Fiction"}, {"id": 12, "name": "Adventure"}],
    "poster_path": "/d5NXSklXo0qyIYkgV94XAgMIckC.jpg",
    "runtime": 155,
    "credits": {
        "cast": [{"name": "Timothée Chalamet"}, {"name": "Rebecca Ferguson"}],
        "crew": [{"name": "Denis Villeneuve", "job": "Director"}, {"name": "Someone Else", "job": "Producer"}],
    },
}

TV_RESPONSE = {
    "name": "Brooklyn Nine-Nine",
    "first_air_date": "2013-09-17",
    "overview": "Det. Jake Peralta...",
    "genres": [{"id": 35, "name": "Comedy"}],
    "poster_path": "/abc.jpg",
    "episode_run_time": [22],
    "credits": {"cast": [{"name": "Andy Samberg"}], "crew": []},
}


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


@pytest.fixture
def repo(tmp_path):
    return TmdbRepo(api_key="test-key", base_url="https://tmdb.example", db_path=tmp_path / "tmdb.db")


def test_get_movie_extracts_director_and_top_cast(repo):
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(MOVIE_RESPONSE)):
        record, source = repo.get("movie", 438631)

    assert source == "live"
    assert record["title"] == "Dune"
    assert record["release_date"] == "2021-09-15"
    assert record["director"] == "Denis Villeneuve"
    assert record["cast"] == ["Timothée Chalamet", "Rebecca Ferguson"]
    assert record["genres"] == ["Science Fiction", "Adventure"]
    assert record["runtime"] == 155


def test_get_tv_falls_back_to_name_first_air_date_and_episode_runtime(repo):
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(TV_RESPONSE)):
        record, source = repo.get("tv", 4056)

    assert source == "live"
    assert record["title"] == "Brooklyn Nine-Nine"
    assert record["release_date"] == "2013-09-17"
    assert record["runtime"] == 22
    assert record["director"] is None  # no crew entry has job == "Director"


def test_second_call_hits_cache_without_more_http_calls(repo):
    call_count = {"n": 0}

    def counting_get(*args, **kwargs):
        call_count["n"] += 1
        return FakeResponse(MOVIE_RESPONSE)

    with patch("app.repos.tmdb_repo.http.get", side_effect=counting_get):
        repo.get("movie", 438631)
        calls_after_first = call_count["n"]
        record, source = repo.get("movie", 438631)

    assert source == "cache"
    assert call_count["n"] == calls_after_first
    assert record["title"] == "Dune"


def test_force_refresh_bypasses_cache(repo):
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(MOVIE_RESPONSE)):
        repo.get("movie", 438631)
        _, source = repo.get("movie", 438631, force_refresh=True)

    assert source == "live"


def test_movie_and_tv_cache_independently_for_the_same_id(repo):
    # Overseerr's movie/tv tmdbId spaces are independent, so id 4056 as a
    # movie must not collide with id 4056 as a tv show in the cache.
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(MOVIE_RESPONSE)):
        repo.get("movie", 4056)
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(TV_RESPONSE)) as mock_get:
        record, source = repo.get("tv", 4056)

    assert source == "live"
    mock_get.assert_called_once()
    assert record["title"] == "Brooklyn Nine-Nine"


def test_get_many_fetches_multiple_items_concurrently(repo):
    def routed_get(url, params=None, timeout=None):
        if "/movie/" in url:
            return FakeResponse(MOVIE_RESPONSE)
        return FakeResponse(TV_RESPONSE)

    with patch("app.repos.tmdb_repo.http.get", side_effect=routed_get):
        results = repo.get_many([("movie", 438631), ("tv", 4056)])

    assert results[("movie", 438631)]["title"] == "Dune"
    assert results[("tv", 4056)]["title"] == "Brooklyn Nine-Nine"


def test_get_many_isolates_a_single_item_failure(repo):
    def flaky_get(url, params=None, timeout=None):
        if "/movie/438631" in url:
            raise ConnectionError("simulated network failure")
        return FakeResponse(TV_RESPONSE)

    with patch("app.repos.tmdb_repo.http.get", side_effect=flaky_get):
        results = repo.get_many([("movie", 438631), ("tv", 4056)])

    assert results[("movie", 438631)] is None
    assert results[("tv", 4056)]["title"] == "Brooklyn Nine-Nine"


SEARCH_MULTI_RESPONSE = {
    "results": [
        {"id": 1, "media_type": "movie", "title": "Dune", "release_date": "1984-12-14", "poster_path": "/a.jpg"},
        {"id": 2, "media_type": "tv", "name": "Dune: Prophecy", "first_air_date": "2024-11-17", "poster_path": "/b.jpg"},
        {"id": 3, "media_type": "person", "name": "Denis Villeneuve"},
    ]
}


def test_search_filters_to_movie_and_tv_and_normalizes_title_and_date(repo):
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(SEARCH_MULTI_RESPONSE)):
        results = repo.search("dune")

    assert results == [
        {"tmdb_id": 1, "media_type": "movie", "title": "Dune", "release_date": "1984-12-14", "poster_path": "/a.jpg"},
        {"tmdb_id": 2, "media_type": "tv", "title": "Dune: Prophecy", "release_date": "2024-11-17", "poster_path": "/b.jpg"},
    ]


def test_search_returns_empty_list_for_empty_query(repo):
    with patch("app.repos.tmdb_repo.http.get") as mock_get:
        assert repo.search("") == []
    mock_get.assert_not_called()


def test_api_key_sent_as_query_param(repo):
    captured_params = {}

    def capturing_get(url, params=None, timeout=None):
        captured_params.update(params)
        return FakeResponse(MOVIE_RESPONSE)

    with patch("app.repos.tmdb_repo.http.get", side_effect=capturing_get):
        repo.get("movie", 438631)

    assert captured_params["api_key"] == "test-key"


SPIDER_MAN_RESPONSE = {
    **MOVIE_RESPONSE,
    "title": "Spider-Man: Homecoming",
    "belongs_to_collection": {"id": 531241, "name": "Spider-Man (MCU) Collection"},
}


def test_get_movie_captures_collection_and_survives_the_cache_round_trip(repo):
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(SPIDER_MAN_RESPONSE)):
        live, _ = repo.get("movie", 315635)
        cached, source = repo.get("movie", 315635)

    assert source == "cache"
    for record in (live, cached):
        assert record["collection_id"] == 531241
        assert record["collection_name"] == "Spider-Man (MCU) Collection"


def test_movie_without_a_collection_has_null_collection_fields(repo):
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(MOVIE_RESPONSE)):
        record, _ = repo.get("movie", 438631)

    assert record["collection_id"] is None
    assert record["collection_name"] is None


def test_pre_collection_cache_is_migrated_and_old_rows_refetch(tmp_path):
    import sqlite3
    import time

    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE media (
            media_type TEXT NOT NULL, tmdb_id INTEGER NOT NULL, title TEXT,
            release_date TEXT, overview TEXT, genres TEXT, poster_path TEXT,
            director TEXT, cast TEXT, runtime INTEGER, fetched_at REAL NOT NULL,
            PRIMARY KEY (media_type, tmdb_id)
        );
        """
    )
    legacy.execute(
        "INSERT INTO media (media_type, tmdb_id, title, fetched_at) VALUES ('movie', 315635, 'Old', ?)",
        (time.time(),),  # fresh by TTL — would be served as-is without the migration
    )
    legacy.commit()
    legacy.close()

    repo = TmdbRepo(api_key="k", base_url="https://tmdb.example", db_path=db_path)
    with patch("app.repos.tmdb_repo.http.get", return_value=FakeResponse(SPIDER_MAN_RESPONSE)):
        record, source = repo.get("movie", 315635)

    assert source == "live"
    assert record["collection_id"] == 531241
