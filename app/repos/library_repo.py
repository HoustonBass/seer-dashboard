"""Everything about talking to the Fulton County Library (BiblioCommons)
system: auth, catalog search, and this repo's own SQLite result cache.

Native Python port of scripts/library/auth.sh + search.sh for use by app/ —
those scripts stay as-is as standalone CLI reference implementations. See
scripts/discovery/auth.md and search.md for how this flow was
reverse-engineered; don't re-derive it, this is a straight port.
"""
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

import requests as http

from app.lib.singleflight import SingleFlightCache
from app.lib.feature_switch import delay_switch

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "library_cache.db"
DEFAULT_TTL_SECONDS = 6 * 60 * 60  # availability changes during the day, but not by the minute
TEST_DELAY_ENV_VAR = "LIBRARY_TEST_FETCH_DELAY_SECONDS"
# bc_access_token/session_id's real lifetime is undocumented (see
# scripts/discovery/auth.md) — this is a conservative guess, not a confirmed
# expiry. _fetch_search_live() also retries once on a 401/403 by forcing a
# fresh login, so an expired-but-still-cached token self-heals rather than
# needing this TTL to be exactly right.
AUTH_TTL_SECONDS = 10 * 60


class LibraryRepo:
    def __init__(
        self,
        base_url=None,
        username=None,
        password=None,
        agency=None,
        gateway_url=None,
        db_path=DB_PATH,
    ):
        self.base_url = (base_url or os.environ.get("LIBRARY_BASE_URL") or "https://fulcolibrary.bibliocommons.com").rstrip("/")
        self.username = username or os.environ["LIBRARY_USERNAME"]
        self.password = password or os.environ["LIBRARY_PASSWORD"]
        self.agency = agency or os.environ.get("LIBRARY_AGENCY", "fulcolibrary")
        self.gateway_url = (gateway_url or os.environ.get("LIBRARY_GATEWAY_URL") or "https://gateway.bibliocommons.com").rstrip("/")
        self._conn = self._connect(db_path)
        self._singleflight = SingleFlightCache()
        # See SeerrRepo — sqlite3 Connections aren't safe for concurrent use
        # from multiple threads, and Flask runs threaded=True here.
        self._db_lock = threading.Lock()
        # In-memory only, deliberately never written to the sqlite cache —
        # it's a live session credential, not catalog data. Every distinct
        # search used to call authenticate() fresh (no reuse at all), which
        # meant repeatedly logging into a real account on every cache miss —
        # a likely contributor to the "Invalid sequence number" flakiness
        # documented in scripts/discovery/auth.md. One shared, locked login
        # instead of one per search.
        self._auth_cache = None  # (access_token, session_id, cached_at) | None
        self._auth_lock = threading.Lock()

    @staticmethod
    def _connect(db_path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bibs (
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
                jacket_url TEXT,
                jacket_url_large TEXT,
                record_url TEXT,
                fetched_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS searches (
                query TEXT NOT NULL,
                format_filter TEXT NOT NULL DEFAULT '',
                bib_id TEXT NOT NULL,
                rank_order INTEGER NOT NULL,
                fetched_at REAL NOT NULL,
                PRIMARY KEY (query, format_filter, bib_id)
            );
            """
        )
        # CREATE TABLE IF NOT EXISTS doesn't add columns to an already-created
        # table — this cache is disposable (safe to just delete the file),
        # but a lightweight migration is friendlier than a startup crash.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(bibs)")}
        for column in ("jacket_url", "jacket_url_large", "record_url"):
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE bibs ADD COLUMN {column} TEXT")
        conn.commit()
        return conn

    # -- auth (see scripts/discovery/auth.md) ------------------------------

    def authenticate(self):
        """Returns (bc_access_token, session_id). Ports scripts/library/auth.sh:
        scrape CSRF token off the login page, POST credentials with XHR-style
        headers so the server responds 200 JSON + Set-Cookie directly (no
        /sso/web hop needed outside a real browser)."""
        session = http.Session()
        login_url = f"{self.base_url}/user/login"

        login_page = session.get(login_url, timeout=15)
        match = re.search(r'name="authenticity_token" type="hidden" value="([^"]*)"', login_page.text)
        if not match:
            raise RuntimeError("Could not find authenticity_token on login page — page markup may have changed.")
        csrf_token = match.group(1)

        response = session.post(
            login_url,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Token": csrf_token,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            data={
                "utf8": "✓",
                "authenticity_token": csrf_token,
                "name": self.username,
                "user_pin": self.password,
                "local": "false",
            },
            timeout=15,
        )
        if '"logged_in":true' not in response.text:
            raise RuntimeError(f"Login failed — check LIBRARY_USERNAME/LIBRARY_PASSWORD. Response: {response.text}")

        access_token = session.cookies.get("bc_access_token")
        session_id = session.cookies.get("session_id")
        if not access_token or not session_id:
            raise RuntimeError("Login succeeded but bc_access_token/session_id cookies were not set.")
        return access_token, session_id

    def _get_auth(self, force_refresh=False):
        """Returns (access_token, session_id), reusing a cached login within
        AUTH_TTL_SECONDS instead of calling authenticate() on every search."""
        with self._auth_lock:
            if not force_refresh and self._auth_cache is not None:
                access_token, session_id, cached_at = self._auth_cache
                if time.time() - cached_at < AUTH_TTL_SECONDS:
                    return access_token, session_id

            access_token, session_id = self.authenticate()
            self._auth_cache = (access_token, session_id, time.time())
            return access_token, session_id

    # -- search ranking (see scripts/discovery/search.md) ------------------

    @staticmethod
    def _normalize(text):
        text = text.lower().strip()
        text = re.sub(r"^the ", "", text)
        text = re.sub(r"[^a-z0-9 ]", "", text)
        text = re.sub(r" +", " ", text).strip()
        return text

    def _score_match(self, title, subtitle, query_norm):
        full_title = f"{title}: {subtitle}" if subtitle else title
        if self._normalize(full_title) == query_norm:
            return 2
        if self._normalize(title) == query_norm:
            return 1
        return 0

    def _search_request(self, query, format_filter, access_token, session_id):
        search_query = f"formatcode:({format_filter}) {query}" if format_filter else query
        return http.get(
            f"{self.gateway_url}/v2/libraries/{self.agency}/bibs/search",
            headers={
                "Accept": "application/json",
                "X-Access-Token": access_token,
                "X-Session-Id": session_id,
            },
            params={"query": search_query, "searchType": "bl", "locale": "en-US"},
            timeout=15,
        )

    def _fetch_search_live(self, query, format_filter):
        delay_switch(TEST_DELAY_ENV_VAR)
        access_token, session_id = self._get_auth()
        response = self._search_request(query, format_filter, access_token, session_id)

        if response.status_code in (401, 403):
            # Cached token likely expired — AUTH_TTL_SECONDS is a guess, not
            # a confirmed lifetime, so self-heal here rather than trust it.
            access_token, session_id = self._get_auth(force_refresh=True)
            response = self._search_request(query, format_filter, access_token, session_id)

        response.raise_for_status()
        data = response.json()

        query_norm = self._normalize(query)
        records = []
        for result in data["catalogSearch"]["results"]:
            bib = data["entities"]["bibs"][result["representative"]]
            info = bib["briefInfo"]
            availability = bib.get("availability") or {}
            title = info.get("title", "")
            subtitle = info.get("subtitle") or ""
            jacket = info.get("jacket") or {}
            records.append(
                {
                    "bib_id": bib["id"],
                    "title": title,
                    "subtitle": subtitle,
                    "format": info.get("format", ""),
                    "availability_status": availability.get("status", ""),
                    "available_copies": availability.get("availableCopies"),
                    "total_copies": availability.get("totalCopies"),
                    "publication_date": info.get("publicationDate"),
                    "call_number": info.get("callNumber"),
                    "authors": "; ".join(info.get("authors") or []),
                    "match_score": self._score_match(title, subtitle, query_norm),
                    # "medium" is a reasonable thumbnail size; not every bib
                    # has cover art (e.g. sparse/no-info catalog records — see
                    # scripts/discovery/search.md's Dune investigation), so
                    # this is often None and the frontend needs to handle that.
                    "jacket_url": jacket.get("medium") or jacket.get("small"),
                    # "large" specifically for the hover-zoom preview — using
                    # "medium" there too looked visibly blurry once scaled up.
                    "jacket_url_large": jacket.get("large") or jacket.get("medium") or jacket.get("small"),
                    # Public record detail page — no auth needed to view (see
                    # scripts/discovery/search.md), so this is safe to link
                    # to directly for "see the real listing" in the UI.
                    "record_url": f"{self.base_url}/v2/record/{bib['id']}",
                }
            )
        records.sort(key=lambda r: (-r["match_score"], r["publication_date"] or ""))
        return records

    # -- cache --------------------------------------------------------------

    def _cache_get(self, query, format_filter, ttl):
        cutoff = time.time() - ttl
        with self._db_lock:
            rows = self._conn.execute(
                """
                SELECT b.*, s.rank_order
                FROM searches s
                JOIN bibs b ON b.bib_id = s.bib_id
                WHERE s.query = ? AND s.format_filter = ? AND s.fetched_at >= ?
                ORDER BY s.rank_order
                """,
                (query, format_filter or "", cutoff),
            ).fetchall()
        return [dict(row) for row in rows] if rows else None

    def _cache_set(self, query, format_filter, records):
        fetched_at = time.time()
        format_filter = format_filter or ""
        with self._db_lock:
            self._conn.execute(
                "DELETE FROM searches WHERE query = ? AND format_filter = ?",
                (query, format_filter),
            )
            for rank_order, record in enumerate(records):
                self._conn.execute(
                    """
                    INSERT INTO bibs (bib_id, title, subtitle, format, availability_status,
                        available_copies, total_copies, publication_date, call_number, authors,
                        match_score, jacket_url, jacket_url_large, record_url, fetched_at)
                    VALUES (:bib_id, :title, :subtitle, :format, :availability_status,
                        :available_copies, :total_copies, :publication_date, :call_number, :authors,
                        :match_score, :jacket_url, :jacket_url_large, :record_url, :fetched_at)
                    ON CONFLICT(bib_id) DO UPDATE SET
                        title=excluded.title,
                        subtitle=excluded.subtitle,
                        format=excluded.format,
                        availability_status=excluded.availability_status,
                        available_copies=excluded.available_copies,
                        total_copies=excluded.total_copies,
                        publication_date=excluded.publication_date,
                        call_number=excluded.call_number,
                        authors=excluded.authors,
                        match_score=excluded.match_score,
                        jacket_url=excluded.jacket_url,
                        jacket_url_large=excluded.jacket_url_large,
                        record_url=excluded.record_url,
                        fetched_at=excluded.fetched_at
                    """,
                    {**record, "fetched_at": fetched_at},
                )
                self._conn.execute(
                    """
                    INSERT INTO searches (query, format_filter, bib_id, rank_order, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (query, format_filter, record["bib_id"], rank_order, fetched_at),
                )
            self._conn.commit()

    # -- public API -----------------------------------------------------

    def search(self, query, format_filter="", ttl=DEFAULT_TTL_SECONDS, force_refresh=False):
        """Returns (records, source) where source is "cache" or "live"."""
        cache_key = (query, format_filter or "")

        def get_cached():
            return self._cache_get(query, format_filter, ttl)

        def fetch_and_cache():
            records = self._fetch_search_live(query, format_filter)
            self._cache_set(query, format_filter, records)
            return records

        return self._singleflight.get_or_fetch(cache_key, get_cached, fetch_and_cache, force_refresh=force_refresh)
