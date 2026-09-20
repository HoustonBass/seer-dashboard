"""Everything about talking to Overseerr: API calls, and this repo's own
SQLite result cache. This is a native Python port of scripts/seerr/requests.sh
for use by app/ — that script stays as-is as a standalone CLI reference (see
scripts/discovery/seerr.md for the API itself, which is publicly documented
by Overseerr's own Swagger UI, no reverse engineering needed).

Caches per filter (all/approved/pending/etc) because requests.sh's approach —
one Overseerr call per result just to resolve a title via TMDB passthrough —
is expensive to repeat on every page load. A SingleFlightCache ensures
concurrent callers for the same filter wait on one in-flight fetch rather than
each kicking off their own.
"""
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests as http

from app.lib.singleflight import SingleFlightCache
from app.lib.feature_switch import delay_switch

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seerr_cache.db"
DEFAULT_TTL_SECONDS = 5 * 60  # request/media status changes fairly often — short TTL
TITLE_LOOKUP_WORKERS = 10  # neither Overseerr nor TMDB offer a bulk title-lookup
# endpoint — this is one HTTP call per request just to resolve a title, so on
# a cold cache with hundreds of requests that's the dominant cost. They're
# independent GETs, so run them concurrently instead of one at a time.
TEST_DELAY_ENV_VAR = "SEERR_TEST_FETCH_DELAY_SECONDS"


class SeerrRepo:
    def __init__(self, base_url=None, api_key=None, db_path=DB_PATH):
        self.base_url = (base_url or os.environ["SEERR_BASE_URL"]).rstrip("/")
        self.api_key = api_key or os.environ["SEERR_API_KEY"]
        self._conn = self._connect(db_path)
        self._singleflight = SingleFlightCache()
        # sqlite3 Connection objects are not safe for concurrent use from
        # multiple threads even with check_same_thread=False (that flag only
        # disables Python's guard, not actual thread-safety) — this app runs
        # Flask with threaded=True, so guard all access to self._conn.
        self._db_lock = threading.Lock()

    @staticmethod
    def _connect(db_path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS requests_cache (
                filter_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                fetched_at REAL NOT NULL
            );
            """
        )
        conn.commit()
        return conn

    # -- HTTP -----------------------------------------------------------

    def _headers(self):
        return {"X-Api-Key": self.api_key, "Accept": "application/json"}

    def _get(self, path, params=None):
        response = http.get(f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def fetch_title(self, media_type, tmdb_id):
        if media_type == "movie":
            return self._get(f"/api/v1/movie/{tmdb_id}").get("title", "?")
        return self._get(f"/api/v1/tv/{tmdb_id}").get("name", "?")

    def fetch_raw_requests(self, filter_key):
        """Just the Overseerr request-list pagination — no per-row title
        resolution. Used by RequestsService.stream_requests, which does its
        own per-row resolution so it can yield rows as they finish rather
        than waiting for the whole batch (see build_row below for the
        all-at-once equivalent)."""
        delay_switch(TEST_DELAY_ENV_VAR)
        take = 50
        skip = 0
        raw_results = []
        while True:
            page = self._get(
                "/api/v1/request",
                params={"take": take, "skip": skip, "filter": filter_key, "sort": "added"},
            )
            results = page.get("results", [])
            raw_results.extend(results)
            skip += len(results)
            if len(results) == 0 or skip >= page["pageInfo"]["results"]:
                break
        return raw_results

    def _fetch_requests_live(self, filter_key):
        raw_results = self.fetch_raw_requests(filter_key)

        def build_row(r):
            media_type = r["type"]
            tmdb_id = r["media"]["tmdbId"]
            return {
                "id": r["id"],
                "type": media_type,
                "tmdb_id": tmdb_id,
                "title": self.fetch_title(media_type, tmdb_id),
                "request_status": r["status"],
                "media_status": r["media"]["status"],
                "requested_by": r["requestedBy"]["displayName"],
            }

        with ThreadPoolExecutor(max_workers=TITLE_LOOKUP_WORKERS) as pool:
            rows = list(pool.map(build_row, raw_results))
        return rows

    # -- cache ------------------------------------------------------------

    def _cache_get(self, filter_key, ttl):
        cutoff = time.time() - ttl
        with self._db_lock:
            row = self._conn.execute(
                "SELECT payload_json FROM requests_cache WHERE filter_key = ? AND fetched_at >= ?",
                (filter_key, cutoff),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def _cache_set(self, filter_key, rows):
        with self._db_lock:
            self._conn.execute(
                """
                INSERT INTO requests_cache (filter_key, payload_json, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(filter_key) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    fetched_at=excluded.fetched_at
                """,
                (filter_key, json.dumps(rows), time.time()),
            )
            self._conn.commit()

    # -- public API ---------------------------------------------------------

    def list_requests(self, filter_key="all", ttl=DEFAULT_TTL_SECONDS, force_refresh=False):
        """Returns (rows, source) where source is "cache" or "live". Blocks
        until the whole batch resolves — for progressive per-row delivery,
        see RequestsService.stream_requests, which uses get_cached_requests/
        cache_requests/fetch_raw_requests/fetch_title directly instead."""

        def get_cached():
            return self._cache_get(filter_key, ttl)

        def fetch_and_cache():
            rows = self._fetch_requests_live(filter_key)
            self._cache_set(filter_key, rows)
            return rows

        return self._singleflight.get_or_fetch(filter_key, get_cached, fetch_and_cache, force_refresh=force_refresh)

    def get_cached_requests(self, filter_key, ttl=DEFAULT_TTL_SECONDS):
        """Returns the cached row list for filter_key if fresh, else None.
        Bypasses SingleFlightCache deliberately — streaming callers need a
        plain cache read, not the block-until-fetched semantics that make
        sense for list_requests's single-shot contract."""
        return self._cache_get(filter_key, ttl)

    def cache_requests(self, filter_key, rows):
        self._cache_set(filter_key, rows)
