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


def test_api_key_sent_as_query_param(repo):
    captured_params = {}

    def capturing_get(url, params=None, timeout=None):
        captured_params.update(params)
        return FakeResponse(MOVIE_RESPONSE)

    with patch("app.repos.tmdb_repo.http.get", side_effect=capturing_get):
        repo.get("movie", 438631)

    assert captured_params["api_key"] == "test-key"
