"""Persistence for the mock frontend's own state: which Overseerr request got
matched to which library bib_id.

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
            """
            CREATE TABLE IF NOT EXISTS matches (
                request_id INTEGER PRIMARY KEY,
                tmdb_id INTEGER,
                media_type TEXT,
                seerr_title TEXT,
                bib_id TEXT,
                bib_title TEXT,
                bib_subtitle TEXT,
                decided_at REAL NOT NULL
            );
            """
        )
        conn.commit()
        return conn

    def set_match(self, request_id, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle):
        with self._db_lock:
            self._conn.execute(
                """
                INSERT INTO matches (request_id, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    tmdb_id=excluded.tmdb_id,
                    media_type=excluded.media_type,
                    seerr_title=excluded.seerr_title,
                    bib_id=excluded.bib_id,
                    bib_title=excluded.bib_title,
                    bib_subtitle=excluded.bib_subtitle,
                    decided_at=excluded.decided_at
                """,
                (request_id, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, time.time()),
            )
            self._conn.commit()

    def clear_match(self, request_id):
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
