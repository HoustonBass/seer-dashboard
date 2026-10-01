import pytest

from app.services.movie_search_service import MovieSearchService


class FakeSeerr:
    def __init__(self, movies):
        self.movies = movies

    def search_movies(self, query):
        self.last_query = query
        return self.movies


class FakeTmdb:
    def __init__(self, records):
        self.records = records

    def get_many(self, items):
        return {item: self.records.get(item) for item in items}


def service(movies, records):
    return MovieSearchService(FakeSeerr(movies), FakeTmdb(records))


def test_search_tags_each_hit_with_its_collection():
    svc = service(
        [{"tmdb_id": 1, "title": "A"}, {"tmdb_id": 2, "title": "B"}, {"tmdb_id": 3, "title": "C"}],
        {
            ("movie", 1): {"collection_id": 10, "collection_name": "Col"},
            ("movie", 2): {"collection_id": None, "collection_name": None},
            # 3: TMDB lookup failed (None)
        },
    )
    results = svc.search("  a  ")

    assert svc.seerr_repo.last_query == "a"
    assert [r["collection"] for r in results] == [{"id": 10, "name": "Col"}, None, None]


def test_search_requires_a_query():
    with pytest.raises(ValueError):
        service([], {}).search("   ")


import requests as http


class RequestingSeerr:
    """In-memory Overseerr: a collection whose parts get requested for real."""

    def __init__(self, parts, fail_ids=()):
        self.parts = {p["tmdb_id"]: dict(p) for p in parts}
        self.fail_ids = set(fail_ids)
        self.created = []
        self.dropped = []

    def get_collection(self, collection_id, force_refresh=False):
        return {"id": collection_id, "name": "Col", "parts": list(self.parts.values())}, "live"

    def create_request(self, media_type, tmdb_id):
        assert media_type == "movie"
        if tmdb_id in self.fail_ids:
            raise http.HTTPError(response=type("R", (), {"status_code": 500})())
        self.created.append(tmdb_id)
        self.parts[tmdb_id]["media_status"] = 2
        return {"id": 1000 + tmdb_id, "media_status": 2}

    def drop_collection_cache(self, collection_id):
        self.dropped.append(collection_id)


def part(tmdb_id, status=None):
    return {"tmdb_id": tmdb_id, "title": f"M{tmdb_id}", "media_status": status}


def test_request_collection_only_requests_what_is_not_already_requested():
    seerr = RequestingSeerr([part(1, 5), part(2, 2), part(3), part(4, 1)])
    result = MovieSearchService(seerr, FakeTmdb({})).request_collection(10)

    assert seerr.created == [3, 4]  # 1 available, 2 pending are skipped; 1="unknown" status is requestable
    assert [r["tmdb_id"] for r in result["requested"]] == [3, 4]
    assert result["failed"] == []
    assert seerr.dropped == [10]


def test_request_collection_keeps_going_past_a_failure_and_reports_it():
    seerr = RequestingSeerr([part(1), part(2), part(3)], fail_ids={2})
    result = MovieSearchService(seerr, FakeTmdb({})).request_collection(10)

    assert seerr.created == [1, 3]
    assert result["failed"] == [{"tmdb_id": 2, "title": "M2", "error": "Overseerr rejected the request (500)"}]


def test_request_movie_drops_its_collections_cache():
    seerr = RequestingSeerr([part(1)])
    tmdb = type("T", (), {"get": lambda self, mt, i: ({"collection_id": 10}, "cache")})()
    result = MovieSearchService(seerr, tmdb).request_movie(1)

    assert result == {"id": 1001, "media_status": 2}
    assert seerr.dropped == [10]
