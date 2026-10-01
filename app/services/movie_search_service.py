"""Business logic for the "find movies" search: Overseerr's movie search,
each hit tagged with the TMDB collection it belongs to (from TmdbRepo's
cache), the full part list of a collection on demand, and requesting
individual movies or a whole collection. Orchestrates SeerrRepo + TmdbRepo;
no HTTP or SQL of its own.
"""
import requests as http

# Overseerr media statuses that mean "already requested or available" — a
# movie in any of these must never be requested again.
ALREADY_REQUESTED = {2, 3, 4, 5}


class MovieRequestError(Exception):
    """Overseerr refused or couldn't be reached for a request."""


class MovieSearchService:
    def __init__(self, seerr_repo, tmdb_repo):
        self.seerr_repo = seerr_repo
        self.tmdb_repo = tmdb_repo

    def search(self, query):
        query = (query or "").strip()
        if not query:
            raise ValueError("query is required")
        movies = self.seerr_repo.search_movies(query)
        tmdb = self.tmdb_repo.get_many(("movie", m["tmdb_id"]) for m in movies)
        return [{**m, "collection": self._collection_of(tmdb.get(("movie", m["tmdb_id"])))} for m in movies]

    def get_collection(self, collection_id, force_refresh=False):
        return self.seerr_repo.get_collection(collection_id, force_refresh=force_refresh)

    def request_movie(self, tmdb_id):
        """Creates a real Overseerr request. Returns {"id", "media_status"}."""
        result = self._create_request(tmdb_id)
        self._drop_collection_cache_for(tmdb_id)
        return result

    def request_collection(self, collection_id):
        """Requests every movie in the collection that isn't already
        requested or available. Re-reads the collection live first, so a
        stale cache or a double click can't request something twice, and
        keeps going past individual failures. Returns {"requested": [...],
        "failed": [...], "collection": <fresh collection>}."""
        collection, _ = self.seerr_repo.get_collection(collection_id, force_refresh=True)
        requested, failed = [], []
        for part in collection["parts"]:
            if part["media_status"] in ALREADY_REQUESTED:
                continue
            try:
                result = self._create_request(part["tmdb_id"])
            except MovieRequestError as e:
                failed.append({"tmdb_id": part["tmdb_id"], "title": part["title"], "error": str(e)})
            else:
                requested.append({"tmdb_id": part["tmdb_id"], "title": part["title"], **result})
        self.seerr_repo.drop_collection_cache(collection_id)
        fresh, _ = self.seerr_repo.get_collection(collection_id, force_refresh=True)
        return {"requested": requested, "failed": failed, "collection": fresh}

    def _create_request(self, tmdb_id):
        try:
            return self.seerr_repo.create_request("movie", tmdb_id)
        except http.RequestException as e:
            status = getattr(e.response, "status_code", None)
            raise MovieRequestError(f"Overseerr rejected the request ({status})" if status else "Couldn't reach Overseerr") from e

    def _drop_collection_cache_for(self, tmdb_id):
        try:
            record, _ = self.tmdb_repo.get("movie", tmdb_id)
        except Exception:
            return
        if record and record.get("collection_id"):
            self.seerr_repo.drop_collection_cache(record["collection_id"])

    @staticmethod
    def _collection_of(tmdb_record):
        if not tmdb_record or not tmdb_record.get("collection_id"):
            return None
        return {"id": tmdb_record["collection_id"], "name": tmdb_record["collection_name"]}
