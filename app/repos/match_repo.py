"""Persistence for the mock frontend's own state: what's been decided about
each Overseerr request — either matched to a specific library bib_id, or
confirmed the library doesn't have it ("unavailable"). Both live in the same
table/row per request_id since a request is in exactly one of these states
at a time (see `status`); "unmatched" is just the absence of a row here, not
a stored state.

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

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "matches.db"

STATUS_MATCHED = "matched"
STATUS_UNAVAILABLE = "unavailable"


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
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS matches (
                request_id INTEGER PRIMARY KEY,
                tmdb_id INTEGER,
                media_type TEXT,
                seerr_title TEXT,
                bib_id TEXT,
                bib_title TEXT,
                bib_subtitle TEXT,
                status TEXT NOT NULL DEFAULT '{STATUS_MATCHED}',
                decided_at REAL NOT NULL
            );
            """
        )
        # Existing rows all predate `status` and are all real chosen matches
        # (the only thing this table stored before "unavailable" existed),
        # so DEFAULT '{STATUS_MATCHED}' above is the correct backfill for
        # them automatically — no separate UPDATE needed.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(matches)")}
        if "status" not in existing_columns:
            conn.execute(f"ALTER TABLE matches ADD COLUMN status TEXT NOT NULL DEFAULT '{STATUS_MATCHED}'")
        conn.commit()
        return conn

    def set_match(self, request_id, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle):
        with self._db_lock:
            self._conn.execute(
                f"""
                INSERT INTO matches (request_id, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, status, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '{STATUS_MATCHED}', ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    tmdb_id=excluded.tmdb_id,
                    media_type=excluded.media_type,
                    seerr_title=excluded.seerr_title,
                    bib_id=excluded.bib_id,
                    bib_title=excluded.bib_title,
                    bib_subtitle=excluded.bib_subtitle,
                    status=excluded.status,
                    decided_at=excluded.decided_at
                """,
                (request_id, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, time.time()),
            )
            self._conn.commit()

    def set_unavailable(self, request_id, tmdb_id, media_type, seerr_title):
        """Marks a request as confirmed-not-in-the-library-catalog — distinct
        from "unmatched" (which just means nobody's checked yet). No bib_id:
        there's nothing chosen, that's the point."""
        with self._db_lock:
            self._conn.execute(
                f"""
                INSERT INTO matches (request_id, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, status, decided_at)
                VALUES (?, ?, ?, ?, NULL, NULL, NULL, '{STATUS_UNAVAILABLE}', ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    tmdb_id=excluded.tmdb_id,
                    media_type=excluded.media_type,
                    seerr_title=excluded.seerr_title,
                    bib_id=NULL,
                    bib_title=NULL,
                    bib_subtitle=NULL,
                    status=excluded.status,
                    decided_at=excluded.decided_at
                """,
                (request_id, tmdb_id, media_type, seerr_title, time.time()),
            )
            self._conn.commit()

    def clear_match(self, request_id):
        """Clears either state (matched or unavailable) — both are just "no
        decision recorded" once removed, so one delete covers both."""
        with self._db_lock:
            self._conn.execute("DELETE FROM matches WHERE request_id = ?", (request_id,))
            self._conn.commit()

    def get_match(self, request_id):
        with self._db_lock:
            row = self._conn.execute("SELECT * FROM matches WHERE request_id = ?", (request_id,)).fetchone()
        return dict(row) if row else None

    def get_all_matches(self):
        with self._db_lock:
            rows = self._conn.execute("SELECT * FROM matches").fetchall()
        return {row["request_id"]: dict(row) for row in rows}
