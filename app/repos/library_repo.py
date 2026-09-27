"""Everything about talking to the Fulton County Library (BiblioCommons)
system: auth, catalog search, and this repo's own SQLite result cache.

Native Python port of scripts/library/auth.sh + search.sh for use by app/ —
those scripts stay as-is as standalone CLI reference implementations. See
scripts/discovery/auth.md and search.md for how this flow was
reverse-engineered; don't re-derive it, this is a straight port.
"""
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

import requests as http

from app.lib.env import data_dir
from app.lib.singleflight import SingleFlightCache
from app.lib.feature_switch import delay_switch

DB_PATH = data_dir() / "library_cache.db"
# Shared with scripts/library/auth.sh — same file, same TTL, so a script run
# and any app process reuse one login instead of each keeping their own.
# Keep AUTH_TTL_SECONDS in sync with that script's AUTH_TTL_SECONDS.
AUTH_CACHE_PATH = data_dir() / "library_auth_cache"
DEFAULT_TTL_SECONDS = 6 * 60 * 60  # availability changes during the day, but not by the minute
ACCOUNT_SUMMARY_TTL_SECONDS = 5 * 60  # checkouts/holds change with real-world activity — short TTL, same reasoning as SeerrRepo's request cache
EDITION_TTL_SECONDS = 7 * 24 * 60 * 60  # a catalog record's edition/publication note never changes — same reasoning as TmdbRepo's TTL
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
        default_hold_branch=None,
        db_path=DB_PATH,
        auth_cache_path=AUTH_CACHE_PATH,
    ):
        self.base_url = (base_url or os.environ.get("LIBRARY_BASE_URL") or "https://fulcolibrary.bibliocommons.com").rstrip("/")
        self.username = username or os.environ["LIBRARY_USERNAME"]
        self.password = password or os.environ["LIBRARY_PASSWORD"]
        self.agency = agency or os.environ.get("LIBRARY_AGENCY", "fulcolibrary")
        self.gateway_url = (gateway_url or os.environ.get("LIBRARY_GATEWAY_URL") or "https://gateway.bibliocommons.com").rstrip("/")
        # Pickup branch for place_hold — see scripts/discovery/hold.md, which
        # confirmed "MILTON" live for this account specifically. Don't assume
        # it's universal; override via LIBRARY_HOLD_BRANCH for a different
        # account/home branch.
        self.default_hold_branch = default_hold_branch or os.environ.get("LIBRARY_HOLD_BRANCH", "MILTON")
        self._auth_cache_path = Path(auth_cache_path)
        self._conn = self._connect(db_path)
        self._singleflight = SingleFlightCache()
        # See SeerrRepo — sqlite3 Connections aren't safe for concurrent use
        # from multiple threads, and Flask runs threaded=True here.
        self._db_lock = threading.Lock()
        # In-memory cache (fastest path, no file I/O) plus a shared on-disk
        # cache at AUTH_CACHE_PATH (see that constant) so a fresh process —
        # a restarted app, a second isolated instance, a scripts/library/*.sh
        # run — reuses a still-valid login instead of hitting the network
        # again. This isn't just an optimization: repeatedly logging in with
        # zero reuse (the original design here, and every scripts/library/
        # auth.sh invocation before this) is what actually tripped a real
        # "user record is locked for text update" account lock during one
        # heavy discovery session (see scripts/discovery/auth.md). The file
        # holds a live session credential, same sensitivity as .env — it's
        # gitignored, never commit it.
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
            CREATE TABLE IF NOT EXISTS account_summary (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                checked_out INTEGER NOT NULL,
                on_hold INTEGER NOT NULL,
                fetched_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bib_editions (
                bib_id TEXT PRIMARY KEY,
                edition TEXT,
                publication_note TEXT,
                description TEXT,
                fetched_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS empty_searches (
                query TEXT NOT NULL,
                format_filter TEXT NOT NULL DEFAULT '',
                fetched_at REAL NOT NULL,
                PRIMARY KEY (query, format_filter)
            );
            CREATE TABLE IF NOT EXISTS bib_branches (
                bib_id TEXT PRIMARY KEY,
                branches_json TEXT NOT NULL,
                fetched_at REAL NOT NULL
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

    def _read_shared_auth_cache(self):
        """Reads the on-disk cache shared with scripts/library/auth.sh.
        Returns (access_token, session_id, cached_at) or None on any miss —
        missing file, malformed content, or missing fields all just mean
        "no usable cache", not an error worth raising."""
        try:
            values = {}
            for line in self._auth_cache_path.read_text().splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    values[key] = value
            access_token = values["CACHED_ACCESS_TOKEN"]
            session_id = values["CACHED_SESSION_ID"]
            cached_at = float(values["CACHED_AT"])
        except (FileNotFoundError, KeyError, ValueError):
            return None
        if not access_token or not session_id:
            return None
        return access_token, session_id, cached_at

    def _write_shared_auth_cache(self, access_token, session_id, cached_at=None):
        # Whole seconds, not a float — scripts/library/auth.sh does plain
        # POSIX shell integer arithmetic ($((NOW - CACHED_AT))) on this value,
        # which errors out on a fractional-seconds float like Python's raw
        # time.time(). Sub-second precision isn't meaningful for a
        # 600-second TTL anyway.
        cached_at = int(cached_at if cached_at is not None else time.time())
        self._auth_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._auth_cache_path.write_text(
            f"CACHED_ACCESS_TOKEN={access_token}\nCACHED_SESSION_ID={session_id}\nCACHED_AT={cached_at}\n"
        )
        self._auth_cache_path.chmod(0o600)

    def _get_auth(self, force_refresh=False):
        """Returns (access_token, session_id). Checks the in-memory cache
        first, then the on-disk cache shared with scripts/library/auth.sh,
        and only calls authenticate() (a real network login) if both are
        missing or stale past AUTH_TTL_SECONDS."""
        with self._auth_lock:
            if not force_refresh and self._auth_cache is not None:
                access_token, session_id, cached_at = self._auth_cache
                if time.time() - cached_at < AUTH_TTL_SECONDS:
                    return access_token, session_id

            if not force_refresh:
                shared = self._read_shared_auth_cache()
                if shared is not None:
                    access_token, session_id, cached_at = shared
                    if time.time() - cached_at < AUTH_TTL_SECONDS:
                        self._auth_cache = (access_token, session_id, cached_at)
                        return access_token, session_id

            access_token, session_id = self.authenticate()
            now = time.time()
            self._auth_cache = (access_token, session_id, now)
            self._write_shared_auth_cache(access_token, session_id)
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

    @staticmethod
    def _escape_query(text):
        # The search backend is Solr-based and treats bare "?"/"*" as
        # wildcard operators, not literal punctuation — e.g. a trailing "?"
        # in "O Brother, Where Art Thou?" silently zeroes out the result
        # count instead of matching the literal title. Escape them so title
        # text is always searched literally.
        return re.sub(r"([?*])", r"\\\1", text)

    def _search_request(self, query, format_filter, access_token, session_id):
        escaped_query = self._escape_query(query)
        search_query = f"formatcode:({format_filter}) {escaped_query}" if format_filter else escaped_query
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

    # -- edition detail (disambiguating same-title search results) ----------
    #
    # A bare-title search (see search() above) often returns several bibs
    # that share the same normalized title and publication year — not
    # duplicates, but distinct physical editions of the same release (e.g.
    # "Rental" vs "Two-disc special edition." vs "Anamorphic widescreen.").
    # None of that distinction is visible from bibs/search's briefInfo; it
    # only shows up in catalogBibs' per-record `brief.edition` field. Fetched
    # on demand per bib_id (human-triggered from the frontend), not eagerly
    # for every search result — see CLAUDE.md's "known unknowns" note this
    # was deferred from.

    @staticmethod
    def _extract_field(fields, field_name):
        for field in fields or []:
            for item in field.get("items", []):
                if item.get("fieldName") != field_name:
                    continue
                values = (item.get("fieldValues") or [{}])[0].get("primary", {}).get("values") or []
                if values:
                    return values[0]
        return None

    def _fetch_bib_edition_live(self, bib_id):
        access_token, session_id = self._get_auth()
        response = self._catalog_bib_request(bib_id, access_token, session_id)

        if response.status_code in (401, 403):
            access_token, session_id = self._get_auth(force_refresh=True)
            response = self._catalog_bib_request(bib_id, access_token, session_id)

        response.raise_for_status()
        data = response.json()
        record = data["entities"]["catalogBibs"][bib_id]
        brief = record["brief"]
        return {
            "bib_id": bib_id,
            "edition": brief.get("edition"),
            "description": brief.get("description"),
            "publication_note": self._extract_field(record.get("fields"), "PUBLICATION"),
        }

    def _fetch_branches_live(self, bib_id):
        """Per-branch physical copy breakdown — search/catalogBibs only ever
        expose the aggregate available/total counts, not which branches
        actually hold a copy. See scripts/discovery/branch-availability.md."""
        access_token, session_id = self._get_auth()
        response = self._branch_availability_request(bib_id, access_token, session_id)

        if response.status_code in (401, 403):
            access_token, session_id = self._get_auth(force_refresh=True)
            response = self._branch_availability_request(bib_id, access_token, session_id)

        response.raise_for_status()
        data = response.json()
        bib_items = data.get("entities", {}).get("bibItems") or {}
        return [
            {
                "branch_name": item["branch"]["name"],
                "branch_code": item["branch"]["code"],
                "status": (item.get("availability") or {}).get("status", ""),
                "call_number": item.get("callNumber", ""),
            }
            for item in bib_items.values()
        ]

    def _branch_availability_request(self, bib_id, access_token, session_id):
        return http.get(
            f"{self.gateway_url}/v2/libraries/{self.agency}/bibs/{bib_id}/availability",
            headers={
                "Accept": "application/json",
                "X-Access-Token": access_token,
                "X-Session-Id": session_id,
            },
            params={"locale": "en-US"},
            timeout=15,
        )

    def _branches_cache_get(self, bib_id, ttl):
        cutoff = time.time() - ttl
        with self._db_lock:
            row = self._conn.execute(
                "SELECT branches_json FROM bib_branches WHERE bib_id = ? AND fetched_at >= ?",
                (bib_id, cutoff),
            ).fetchone()
        return json.loads(row["branches_json"]) if row else None

    def _branches_cache_set(self, bib_id, branches):
        with self._db_lock:
            self._conn.execute(
                """
                INSERT INTO bib_branches (bib_id, branches_json, fetched_at) VALUES (?, ?, ?)
                ON CONFLICT(bib_id) DO UPDATE SET branches_json=excluded.branches_json, fetched_at=excluded.fetched_at
                """,
                (bib_id, json.dumps(branches), time.time()),
            )
            self._conn.commit()

    def get_bib_branches(self, bib_id, ttl=DEFAULT_TTL_SECONDS, force_refresh=False):
        """Returns (branches, source) where branches is a list of
        {branch_name, branch_code, status, call_number} — one per physical
        copy. Same TTL reasoning as search's DEFAULT_TTL_SECONDS: which
        branches hold a copy doesn't change, but each copy's checked-out
        status does, during the day."""

        def get_cached():
            return self._branches_cache_get(bib_id, ttl)

        def fetch_and_cache():
            branches = self._fetch_branches_live(bib_id)
            self._branches_cache_set(bib_id, branches)
            return branches

        return self._singleflight.get_or_fetch(f"branches:{bib_id}", get_cached, fetch_and_cache, force_refresh=force_refresh)

    def get_cached_branches(self, bib_id, ttl=DEFAULT_TTL_SECONDS):
        """Read-only — returns cached branches for bib_id if present and
        fresh, else None. Never triggers a live fetch (that's
        get_bib_branches); used by RequestsService to attach branch data to
        already-matched movies without adding a live call to the read-heavy
        /api/requests path — the cache gets populated at match time instead
        (see MatchService.save_match) or by scripts/backfill_branch_cache.py
        for matches made before that existed."""
        return self._branches_cache_get(bib_id, ttl)

    def _catalog_bib_request(self, bib_id, access_token, session_id):
        return http.get(
            f"{self.gateway_url}/v2/libraries/{self.agency}/catalogBibs/{bib_id}",
            headers={
                "Accept": "application/json",
                "X-Access-Token": access_token,
                "X-Session-Id": session_id,
            },
            timeout=15,
        )

    def _edition_cache_get(self, bib_id, ttl):
        cutoff = time.time() - ttl
        with self._db_lock:
            row = self._conn.execute(
                "SELECT * FROM bib_editions WHERE bib_id = ? AND fetched_at >= ?",
                (bib_id, cutoff),
            ).fetchone()
        return dict(row) if row else None

    def _edition_cache_set(self, edition):
        with self._db_lock:
            self._conn.execute(
                """
                INSERT INTO bib_editions (bib_id, edition, publication_note, description, fetched_at)
                VALUES (:bib_id, :edition, :publication_note, :description, :fetched_at)
                ON CONFLICT(bib_id) DO UPDATE SET
                    edition=excluded.edition,
                    publication_note=excluded.publication_note,
                    description=excluded.description,
                    fetched_at=excluded.fetched_at
                """,
                {**edition, "fetched_at": time.time()},
            )
            self._conn.commit()

    def get_bib_edition(self, bib_id, ttl=EDITION_TTL_SECONDS, force_refresh=False):
        """Returns (edition_dict, source) where source is "cache" or "live"."""

        def get_cached():
            cached = self._edition_cache_get(bib_id, ttl)
            return {k: v for k, v in cached.items() if k != "fetched_at"} if cached else None

        def fetch_and_cache():
            edition = self._fetch_bib_edition_live(bib_id)
            self._edition_cache_set(edition)
            return edition

        return self._singleflight.get_or_fetch(f"edition:{bib_id}", get_cached, fetch_and_cache, force_refresh=force_refresh)

    def _attach_cached_editions(self, records):
        """Fills in `record["edition"]` from the bib_editions cache when
        already present (e.g. a prior "what edition is this?" click, or
        another search that happened to include the same bib_id) — None
        otherwise. Never triggers a live catalogBibs fetch itself; that
        stays an on-demand get_bib_edition call (see its docstring for why
        editions aren't fetched for every search result up front)."""
        for record in records:
            cached = self._edition_cache_get(record["bib_id"], EDITION_TTL_SECONDS)
            record["edition"] = (
                {k: v for k, v in cached.items() if k not in ("bib_id", "fetched_at")} if cached else None
            )
        return records

    def _attach_cached_branches(self, records):
        """Fills in `record["branches"]` from the bib_branches cache when
        already present — e.g. this same bib_id is already matched to some
        other request (see RequestsService._join_match / MatchService.
        save_match, which warm this cache) or scripts/backfill_branch_cache.py
        already covered it — None otherwise. Same reasoning as
        _attach_cached_editions above: never triggers a live fetch itself,
        that stays an on-demand get_bib_branches call via the "Which
        branches?" button (see search_controller.py's /branches route)."""
        for record in records:
            record["branches"] = self.get_cached_branches(record["bib_id"])
        return records

    # -- account summary (checkouts/holds — see scripts/discovery/account.md) --

    @staticmethod
    def _account_id(session_id):
        # +1 from the session_id's numeric suffix — confirmed live against
        # the real account (scripts/discovery/account.md); the bare suffix
        # (no +1), which an earlier /header/state capture suggested, 500s.
        return int(session_id.rsplit("-", 1)[-1]) + 1

    @staticmethod
    def _is_dvd(bib):
        return bool(bib) and (bib.get("briefInfo") or {}).get("format") == "DVD"

    def _account_request(self, kind, account_id, page, access_token, session_id):
        return http.get(
            f"{self.gateway_url}/v2/libraries/{self.agency}/{kind}",
            headers={"Accept": "application/json", "X-Access-Token": access_token, "X-Session-Id": session_id},
            params={"accountId": account_id, "materialType": "PHYSICAL", "locale": "en-US", "page": page},
            timeout=15,
        )

    def _fetch_account_items(self, kind):
        """kind: "checkouts" | "holds". Returns [(item, bib_or_None), ...]
        across all pages — see scripts/discovery/account.md for why the join
        against `bibs` is necessary (the API has no server-side DVD filter,
        only PHYSICAL/DIGITAL)."""
        access_token, session_id = self._get_auth()
        account_id = self._account_id(session_id)

        response = self._account_request(kind, account_id, 1, access_token, session_id)
        if response.status_code in (401, 403):
            access_token, session_id = self._get_auth(force_refresh=True)
            account_id = self._account_id(session_id)
            response = self._account_request(kind, account_id, 1, access_token, session_id)
        response.raise_for_status()

        items = []
        page = 1
        while True:
            data = response.json()
            entities = data.get("entities", {})
            bibs = entities.get("bibs", {})
            for item in entities.get(kind, {}).values():
                items.append((item, bibs.get(item.get("metadataId"))))

            pagination = data.get("borrowing", {}).get(kind, {}).get("pagination") or {}
            if page >= pagination.get("pages", 1):
                break
            page += 1
            response = self._account_request(kind, account_id, page, access_token, session_id)
            response.raise_for_status()
        return items

    def _fetch_dvd_activity_count_live(self):
        checked_out = sum(1 for _, bib in self._fetch_account_items("checkouts") if self._is_dvd(bib))
        on_hold = sum(1 for _, bib in self._fetch_account_items("holds") if self._is_dvd(bib))
        return {"checked_out": checked_out, "on_hold": on_hold, "total": checked_out + on_hold}

    def _account_summary_cache_get(self, ttl):
        cutoff = time.time() - ttl
        with self._db_lock:
            row = self._conn.execute(
                "SELECT checked_out, on_hold FROM account_summary WHERE id = 1 AND fetched_at >= ?",
                (cutoff,),
            ).fetchone()
        if row is None:
            return None
        return {"checked_out": row["checked_out"], "on_hold": row["on_hold"], "total": row["checked_out"] + row["on_hold"]}

    def _account_summary_cache_set(self, summary):
        with self._db_lock:
            self._conn.execute(
                """
                INSERT INTO account_summary (id, checked_out, on_hold, fetched_at) VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    checked_out=excluded.checked_out, on_hold=excluded.on_hold, fetched_at=excluded.fetched_at
                """,
                (summary["checked_out"], summary["on_hold"], time.time()),
            )
            self._conn.commit()

    def get_dvd_activity_count(self, ttl=ACCOUNT_SUMMARY_TTL_SECONDS, force_refresh=False):
        """Returns ({"checked_out", "on_hold", "total"}, source) — physical
        DVD items currently checked out or on hold, combined. Net new
        endpoints (see scripts/discovery/account.md), separate from the
        hold-placement API in hold.md."""

        def get_cached():
            return self._account_summary_cache_get(ttl)

        def fetch_and_cache():
            summary = self._fetch_dvd_activity_count_live()
            self._account_summary_cache_set(summary)
            return summary

        return self._singleflight.get_or_fetch("dvd_activity_count", get_cached, fetch_and_cache, force_refresh=force_refresh)

    def place_hold(self, bib_id, branch_id=None):
        """Places a REAL hold on the live account. Confirmed live 2026-09-20
        via a human-driven capture session (scripts/discovery/capture-hold.mjs
        + hold.md) — the request body shape below is not a guess, it's what
        actually worked. Cancel is still unconfirmed; this repo intentionally
        has no cancel_hold method yet."""
        branch_id = branch_id or self.default_hold_branch
        access_token, session_id = self._get_auth()
        account_id = self._account_id(session_id)

        def request(access_token, session_id, account_id):
            return http.post(
                f"{self.gateway_url}/v2/libraries/{self.agency}/holds",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Access-Token": access_token,
                    "X-Session-Id": session_id,
                },
                params={"locale": "en-US"},
                json={
                    "metadataId": bib_id,
                    "materialType": "PHYSICAL",
                    "accountId": account_id,
                    "enableSingleClickHolds": False,
                    "materialParams": {"branchId": branch_id, "expiryDate": None, "errorMessageLocale": "en-US"},
                },
                timeout=15,
            )

        response = request(access_token, session_id, account_id)
        if response.status_code in (401, 403):
            access_token, session_id = self._get_auth(force_refresh=True)
            account_id = self._account_id(session_id)
            response = request(access_token, session_id, account_id)
        response.raise_for_status()

        data = response.json()
        holds = (data.get("entities") or {}).get("holds") or {}
        hold = next(iter(holds.values()), {})
        return {
            "hold_id": hold.get("holdsId"),
            "status": hold.get("status"),
            "expiry_date": hold.get("expiryDate"),
            "pickup_location": (hold.get("pickupLocation") or {}).get("name"),
        }

    # -- cache --------------------------------------------------------------

    def _cache_get(self, query, format_filter, ttl):
        cutoff = time.time() - ttl
        format_filter = format_filter or ""
        with self._db_lock:
            rows = self._conn.execute(
                """
                SELECT b.*, s.rank_order
                FROM searches s
                JOIN bibs b ON b.bib_id = s.bib_id
                WHERE s.query = ? AND s.format_filter = ? AND s.fetched_at >= ?
                ORDER BY s.rank_order
                """,
                (query, format_filter, cutoff),
            ).fetchall()
            if rows:
                return [dict(row) for row in rows]
            # A prior live fetch that genuinely found nothing doesn't add any
            # row to `searches` (there's nothing to rank), so an empty result
            # needs its own marker table — otherwise it's indistinguishable
            # from "never fetched" and every lookup re-hits the live API.
            empty = self._conn.execute(
                "SELECT 1 FROM empty_searches WHERE query = ? AND format_filter = ? AND fetched_at >= ?",
                (query, format_filter, cutoff),
            ).fetchone()
        return [] if empty else None

    def _cache_set(self, query, format_filter, records):
        fetched_at = time.time()
        format_filter = format_filter or ""
        with self._db_lock:
            self._conn.execute(
                "DELETE FROM searches WHERE query = ? AND format_filter = ?",
                (query, format_filter),
            )
            if not records:
                self._conn.execute(
                    """
                    INSERT INTO empty_searches (query, format_filter, fetched_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(query, format_filter) DO UPDATE SET fetched_at=excluded.fetched_at
                    """,
                    (query, format_filter, fetched_at),
                )
                self._conn.commit()
                return
            self._conn.execute(
                "DELETE FROM empty_searches WHERE query = ? AND format_filter = ?",
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
        # A stray leading/trailing/doubled space doesn't change matchScore
        # (_normalize already collapses whitespace before comparing) or,
        # almost certainly, the live Solr search itself — but the cache key
        # was using the raw string, so "title" and "title " looked like two
        # different queries and forced an avoidable live re-fetch.
        query = re.sub(r"\s+", " ", query.strip())
        cache_key = (query, format_filter or "")

        def get_cached():
            return self._cache_get(query, format_filter, ttl)

        def fetch_and_cache():
            records = self._fetch_search_live(query, format_filter)
            self._cache_set(query, format_filter, records)
            return records

        records, source = self._singleflight.get_or_fetch(cache_key, get_cached, fetch_and_cache, force_refresh=force_refresh)
        return self._attach_cached_branches(self._attach_cached_editions(records)), source
