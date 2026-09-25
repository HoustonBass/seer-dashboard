"""Persistence for quick-add attempts that failed before reaching Overseerr
(e.g. the network to SEERR_BASE_URL is down — see QuickAddService). Lets a
failed attempt be retried later instead of the user having to re-search TMDB
and re-enter it from scratch.

Deliberately its own SQLite file (data/failed_quick_adds.db), same reasoning
as MatchRepo: this is durable state (an attempt the user actually made and
hasn't resolved yet), not a disposable cache. No external API calls here, so
just the sqlite3 thread-safety lock (see SeerrRepo for why it's needed).
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

from app.lib.env import data_dir

DB_PATH = data_dir() / "failed_quick_adds.db"

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS failed_quick_adds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payload_json TEXT NOT NULL,
        error TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 1,
        first_failed_at REAL NOT NULL,
        last_failed_at REAL NOT NULL
    );
"""


class FailedQuickAddRepo:
    def __init__(self, db_path=DB_PATH):
        self._conn = self._connect(db_path)
        self._db_lock = threading.Lock()

    @staticmethod
    def _connect(db_path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        conn.commit()
        return conn

    def record_new_failure(self, payload, error):
        """Called the first time a given quick-add attempt fails — inserts a
        fresh row. Returns the new row's id."""
        with self._db_lock:
            now = time.time()
            cursor = self._conn.execute(
                """
                INSERT INTO failed_quick_adds (payload_json, error, attempts, first_failed_at, last_failed_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (json.dumps(payload), error, now, now),
            )
            self._conn.commit()
            return cursor.lastrowid

    def record_retry_failure(self, failed_id, error):
        """Called when a retry of an already-recorded failure fails again —
        updates the existing row in place rather than piling up duplicate
        rows for the same attempt."""
        with self._db_lock:
            self._conn.execute(
                """
                UPDATE failed_quick_adds
                SET error = ?, attempts = attempts + 1, last_failed_at = ?
                WHERE id = ?
                """,
                (error, time.time(), failed_id),
            )
            self._conn.commit()

    def get(self, failed_id):
        with self._db_lock:
            row = self._conn.execute(
                "SELECT * FROM failed_quick_adds WHERE id = ?", (failed_id,)
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["payload"] = json.loads(record.pop("payload_json"))
        return record

    def list_all(self):
        """Most recently failed first."""
        with self._db_lock:
            rows = self._conn.execute(
                "SELECT * FROM failed_quick_adds ORDER BY last_failed_at DESC"
            ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["payload"] = json.loads(record.pop("payload_json"))
            records.append(record)
        return records

    def delete(self, failed_id):
        with self._db_lock:
            self._conn.execute("DELETE FROM failed_quick_adds WHERE id = ?", (failed_id,))
            self._conn.commit()
