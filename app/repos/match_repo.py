"""Persistence for the mock frontend's own state: what's been decided about
each Overseerr request — either matched to a specific library bib_id, or
confirmed the library doesn't have it ("unavailable"). "unmatched" is just
the absence of a row here, not a stored state.

Keyed by (request_id, season_number), not request_id alone — a TV request
covers multiple seasons and the library has one DVD per season (see
CLAUDE.md's TV-matching section), so a single show can have several
independent decisions. Movies (and "the whole item" generally) always use
season_number = WHOLE_ITEM_SEASON (0); TV decisions use Overseerr's real
season numbers, which are always >= 1, so 0 can never collide with a real
season.

Deliberately its own SQLite file (data/matches.db), separate from
SeerrRepo's/LibraryRepo's caches (data/seerr_cache.db, data/library_cache.db)
— those are disposable and safe to delete/rebuild; this one holds actual
decisions made while testing matching strategies and should survive restarts.
No external API calls here, so no auth/live-fetch/singleflight concerns — just
the sqlite3 thread-safety lock (see SeerrRepo for why it's needed).
"""
import sqlite3
import threading
import time
from pathlib import Path

from app.lib.env import data_dir

DB_PATH = data_dir() / "matches.db"

STATUS_MATCHED = "matched"
STATUS_UNAVAILABLE = "unavailable"
WHOLE_ITEM_SEASON = 0

_SCHEMA = f"""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        season_number INTEGER NOT NULL DEFAULT {WHOLE_ITEM_SEASON},
        tmdb_id INTEGER,
        media_type TEXT,
        seerr_title TEXT,
        bib_id TEXT,
        bib_title TEXT,
        bib_subtitle TEXT,
        status TEXT NOT NULL DEFAULT '{STATUS_MATCHED}',
        availability_status TEXT,
        hold_id TEXT,
        decided_at REAL NOT NULL,
        UNIQUE(request_id, season_number)
    );
"""


class MatchRepo:
    def __init__(self, db_path=DB_PATH):
        self._conn = self._connect(db_path)
        self._db_lock = threading.Lock()

    @staticmethod
    def _connect(db_path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        table_exists = (
            conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'").fetchone()
            is not None
        )
        if not table_exists:
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn

        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(matches)")}

        # Two independent migrations, oldest-schema-first: pre-`status`
        # tables predate pre-`season_number` tables' fix, so status must
        # exist before the season_number migration's SELECT can copy it.
        if "status" not in existing_columns:
            conn.execute(f"ALTER TABLE matches ADD COLUMN status TEXT NOT NULL DEFAULT '{STATUS_MATCHED}'")
            existing_columns.add("status")

        if "season_number" not in existing_columns:
            # SQLite can't ALTER a table into having a new composite UNIQUE
            # constraint — recreate + copy. Every pre-existing row predates
            # per-season tracking entirely, so it's unambiguously a
            # WHOLE_ITEM_SEASON (0) decision, not a real season.
            conn.executescript(
                f"""
                ALTER TABLE matches RENAME TO matches_old;
                {_SCHEMA}
                INSERT INTO matches (request_id, season_number, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, status, decided_at)
                    SELECT request_id, {WHOLE_ITEM_SEASON}, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, status, decided_at
                    FROM matches_old;
                DROP TABLE matches_old;
                """
            )
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(matches)")}

        # Plain nullable columns — no UNIQUE constraint involved, so a simple
        # ALTER suffices (unlike the season_number migration above).
        for column in ("availability_status", "hold_id"):
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE matches ADD COLUMN {column} TEXT")

        conn.commit()
        return conn

    def set_match(self, request_id, season_number, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, availability_status=None):
        with self._db_lock:
            self._conn.execute(
                f"""
                INSERT INTO matches (request_id, season_number, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, status, availability_status, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{STATUS_MATCHED}', ?, ?)
                ON CONFLICT(request_id, season_number) DO UPDATE SET
                    tmdb_id=excluded.tmdb_id,
                    media_type=excluded.media_type,
                    seerr_title=excluded.seerr_title,
                    bib_id=excluded.bib_id,
                    bib_title=excluded.bib_title,
                    bib_subtitle=excluded.bib_subtitle,
                    status=excluded.status,
                    availability_status=excluded.availability_status,
                    hold_id=NULL,
                    decided_at=excluded.decided_at
                """,
                (request_id, season_number, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, availability_status, time.time()),
            )
            self._conn.commit()

    def set_hold_id(self, request_id, season_number, hold_id):
        """Records the library's own hold id after a successful place_hold
        call (see LibraryRepo.place_hold / HoldService) — separate from
        set_match so placing a hold doesn't require re-sending every match
        field again."""
        with self._db_lock:
            self._conn.execute(
                "UPDATE matches SET hold_id = ? WHERE request_id = ? AND season_number = ?",
                (hold_id, request_id, season_number),
            )
            self._conn.commit()

    def set_unavailable(self, request_id, season_number, tmdb_id, media_type, seerr_title):
        """Marks (request_id, season_number) as confirmed-not-in-the-library
        — distinct from "unmatched" (nobody's checked yet). No bib_id:
        there's nothing chosen, that's the point."""
        with self._db_lock:
            self._conn.execute(
                f"""
                INSERT INTO matches (request_id, season_number, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, status, decided_at)
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, '{STATUS_UNAVAILABLE}', ?)
                ON CONFLICT(request_id, season_number) DO UPDATE SET
                    tmdb_id=excluded.tmdb_id,
                    media_type=excluded.media_type,
                    seerr_title=excluded.seerr_title,
                    bib_id=NULL,
                    bib_title=NULL,
                    bib_subtitle=NULL,
                    status=excluded.status,
                    decided_at=excluded.decided_at
                """,
                (request_id, season_number, tmdb_id, media_type, seerr_title, time.time()),
            )
            self._conn.commit()

    def clear_match(self, request_id, season_number=WHOLE_ITEM_SEASON):
        """Clears either state (matched or unavailable) for one (request,
        season) — both are just "no decision recorded" once removed."""
        with self._db_lock:
            self._conn.execute(
                "DELETE FROM matches WHERE request_id = ? AND season_number = ?",
                (request_id, season_number),
            )
            self._conn.commit()

    def get_match(self, request_id, season_number=WHOLE_ITEM_SEASON):
        with self._db_lock:
            row = self._conn.execute(
                "SELECT * FROM matches WHERE request_id = ? AND season_number = ?",
                (request_id, season_number),
            ).fetchone()
        return dict(row) if row else None

    def get_matches_by_bib_ids(self, bib_ids):
        """Returns {bib_id: match_dict} for whichever of the given bib_ids
        are already matched (status=matched) to some request. Used by
        SearchService to cross-reference library search results against
        existing matches — a search can surface a title that's unrelated to
        what you searched for (e.g. "Despicable Me 4" showing up while
        searching "Despicable Me 2") but is already matched to a *different*
        request, and quick-add shouldn't offer to create a duplicate
        Overseerr request for something already spoken for. Excludes
        `unavailable` rows deliberately — those have bib_id NULL anyway."""
        bib_ids = list(bib_ids)
        if not bib_ids:
            return {}
        placeholders = ",".join("?" for _ in bib_ids)
        with self._db_lock:
            rows = self._conn.execute(
                f"SELECT * FROM matches WHERE status = '{STATUS_MATCHED}' AND bib_id IN ({placeholders})",
                bib_ids,
            ).fetchall()
        return {row["bib_id"]: dict(row) for row in rows}

    def get_all_matches(self):
        """Returns {request_id: {season_number: match_dict}}. Movies (and any
        other whole-item decision) live under WHOLE_ITEM_SEASON (0) — look
        those up via matches.get(request_id, {}).get(WHOLE_ITEM_SEASON)."""
        with self._db_lock:
            rows = self._conn.execute("SELECT * FROM matches").fetchall()
        result = {}
        for row in rows:
            d = dict(row)
            result.setdefault(d["request_id"], {})[d["season_number"]] = d
        return result
