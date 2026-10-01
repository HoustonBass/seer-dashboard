"""Everything about talking to TMDB (The Movie Database) directly: API calls,
and this repo's own SQLite result cache.

Why this exists separately from SeerrRepo: Overseerr's /api/v1/movie/{id} and
/api/v1/tv/{id} do proxy TMDB, but SeerrRepo only pulls the bare title out of
that response (see app/repos/seerr_repo.py's fetch_title) — release year,
overview, genres, cast/crew, poster, etc. aren't captured anywhere. Rather
than widening SeerrRepo's scope, this hits TMDB directly with its own API key
so "give me everything we know about this tmdbId" is its own concern,
following the one-repo-per-external-system shape (see CLAUDE.md).

Auth: TMDB v3 API key, passed as an `api_key` query param (simpler than the
v4 Bearer read-access-token flow — no separate token generation step).
Get one at https://www.themoviedb.org/settings/api — needs TMDB_API_KEY in
.env.
"""
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests as http

from app.lib.env import data_dir
from app.lib.singleflight import SingleFlightCache

DB_PATH = data_dir() / "tmdb_cache.db"
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60  # movie/tv metadata rarely changes, even week to week


class TmdbRepo:
    def __init__(self, api_key=None, base_url=None, db_path=DB_PATH):
        self.api_key = api_key or os.environ["TMDB_API_KEY"]
        self.base_url = (base_url or os.environ.get("TMDB_BASE_URL") or "https://api.themoviedb.org/3").rstrip("/")
        self._conn = self._connect(db_path)
        self._singleflight = SingleFlightCache()
        # See SeerrRepo/LibraryRepo — sqlite3 Connections aren't safe for
        # concurrent use from multiple threads, and Flask runs threaded=True.
        self._db_lock = threading.Lock()

    @staticmethod
    def _connect(db_path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS media (
                media_type TEXT NOT NULL,
                tmdb_id INTEGER NOT NULL,
                title TEXT,
                release_date TEXT,
                overview TEXT,
                genres TEXT,
                poster_path TEXT,
                director TEXT,
                cast TEXT,
                runtime INTEGER,
                fetched_at REAL NOT NULL,
                PRIMARY KEY (media_type, tmdb_id)
            );
            """
        )
        # Collection columns were added after the table already existed in
        # real caches. Zeroing fetched_at on that first migration expires
        # every old row, so each one refetches and picks up its collection
        # instead of staying collection-less until the TTL lapses.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(media)")}
        if "collection_id" not in columns:
            conn.execute("ALTER TABLE media ADD COLUMN collection_id INTEGER")
            conn.execute("ALTER TABLE media ADD COLUMN collection_name TEXT")
            conn.execute("UPDATE media SET fetched_at = 0")
        conn.commit()
        return conn

    # -- HTTP -----------------------------------------------------------

    def _get(self, path, params=None):
        params = {**(params or {}), "api_key": self.api_key}
        response = http.get(f"{self.base_url}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def _fetch_live(self, media_type, tmdb_id):
        path = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
        data = self._get(path, params={"append_to_response": "credits"})

        credits = data.get("credits") or {}
        director = next(
            (c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"),
            None,
        )
        cast = [c["name"] for c in credits.get("cast", [])[:5]]
        collection = data.get("belongs_to_collection") or {}

        return {
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": data.get("title") or data.get("name"),
            "release_date": data.get("release_date") or data.get("first_air_date"),
            "overview": data.get("overview"),
            "genres": [g["name"] for g in data.get("genres", [])],
            "poster_path": data.get("poster_path"),
            "director": director,
            "cast": cast,
            "runtime": data.get("runtime") or (data.get("episode_run_time") or [None])[0],
            "collection_id": collection.get("id"),
            "collection_name": collection.get("name"),
        }

    # -- cache --------------------------------------------------------------

    def _cache_get(self, media_type, tmdb_id, ttl):
        cutoff = time.time() - ttl
        with self._db_lock:
            row = self._conn.execute(
                "SELECT * FROM media WHERE media_type = ? AND tmdb_id = ? AND fetched_at >= ?",
                (media_type, tmdb_id, cutoff),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["genres"] = record["genres"].split("|") if record["genres"] else []
        record["cast"] = record["cast"].split("|") if record["cast"] else []
        return record

    def _cache_set(self, media_type, tmdb_id, record):
        with self._db_lock:
            self._conn.execute(
                """
                INSERT INTO media (media_type, tmdb_id, title, release_date, overview,
                    genres, poster_path, director, cast, runtime, collection_id,
                    collection_name, fetched_at)
                VALUES (:media_type, :tmdb_id, :title, :release_date, :overview,
                    :genres, :poster_path, :director, :cast, :runtime, :collection_id,
                    :collection_name, :fetched_at)
                ON CONFLICT(media_type, tmdb_id) DO UPDATE SET
                    title=excluded.title,
                    release_date=excluded.release_date,
                    overview=excluded.overview,
                    genres=excluded.genres,
                    poster_path=excluded.poster_path,
                    director=excluded.director,
                    cast=excluded.cast,
                    runtime=excluded.runtime,
                    collection_id=excluded.collection_id,
                    collection_name=excluded.collection_name,
                    fetched_at=excluded.fetched_at
                """,
                {
                    **record,
                    "genres": "|".join(record["genres"]),
                    "cast": "|".join(record["cast"]),
                    "fetched_at": time.time(),
                },
            )
            self._conn.commit()

    # -- public API -----------------------------------------------------

    def get(self, media_type, tmdb_id, ttl=DEFAULT_TTL_SECONDS, force_refresh=False):
        """media_type is "movie" or "tv" (same values Overseerr uses).
        Returns (record, source) where source is "cache" or "live"."""
        cache_key = (media_type, tmdb_id)

        def get_cached():
            return self._cache_get(media_type, tmdb_id, ttl)

        def fetch_and_cache():
            record = self._fetch_live(media_type, tmdb_id)
            self._cache_set(media_type, tmdb_id, record)
            return record

        return self._singleflight.get_or_fetch(cache_key, get_cached, fetch_and_cache, force_refresh=force_refresh)

    def search(self, query):
        """TMDB's /search/multi, filtered to movie/tv (drops "person" results
        multi-search also returns). Used by the quick-add flow (see
        QuickAddService) to resolve a library title the user found into a
        confirmed tmdb_id before creating an Overseerr request — a one-off
        interactive lookup, not repeated per page load like get()/get_many(),
        so it isn't cached."""
        if not query:
            return []
        data = self._get("/search/multi", params={"query": query})
        results = []
        for r in data.get("results", []):
            media_type = r.get("media_type")
            if media_type not in ("movie", "tv"):
                continue
            results.append(
                {
                    "tmdb_id": r["id"],
                    "media_type": media_type,
                    "title": r.get("title") or r.get("name"),
                    "release_date": r.get("release_date") or r.get("first_air_date"),
                    "poster_path": r.get("poster_path"),
                }
            )
        return results

    def get_many(self, items, ttl=DEFAULT_TTL_SECONDS, force_refresh=False):
        """items: iterable of (media_type, tmdb_id). Fetches concurrently
        (each item's own cache/single-flight still applies) — same reasoning
        as SeerrRepo's title-lookup parallelization: TMDB has no bulk lookup,
        and doing these one at a time would be slow on a cold cache.

        Returns {(media_type, tmdb_id): record_or_None} — a per-item failure
        (bad id, TMDB rate limit, etc.) yields None for that item rather than
        failing the whole batch."""
        items = list(items)

        def fetch_one(item):
            media_type, tmdb_id = item
            try:
                record, _ = self.get(media_type, tmdb_id, ttl=ttl, force_refresh=force_refresh)
                return item, record
            except Exception:
                return item, None

        with ThreadPoolExecutor(max_workers=10) as pool:
            return dict(pool.map(fetch_one, items))
