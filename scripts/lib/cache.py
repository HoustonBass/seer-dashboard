"""SQLite cache for library catalog search results.

Caches what scripts/library/search.sh returns per (query, format) so repeated
lookups (e.g. re-running the combine step over the same Overseerr requests)
don't re-hit the BiblioCommons API every time.

Schema:
  bibs(bib_id PK, title, subtitle, format, availability_status,
       available_copies, total_copies, publication_date, call_number,
       authors, match_score, fetched_at)
    One row per catalog record, keyed by BiblioCommons' own bib id.
    Re-fetching always overwrites in place (a bib_id's data doesn't
    meaningfully change identity, just availability/counts over time).

  searches(query, format_filter, bib_id, rank_order, fetched_at)
    One row per (query, format_filter, result). Maps a search back to the
    ordered list of bib_ids it returned, so a cache hit reconstructs the same
    ranked order without re-deriving it.

Availability/copy counts are the most time-sensitive fields here — a hit
within `ttl` is still returned as-is, so pass a short ttl (or --refresh at
the CLI) when freshness matters more than avoiding an API call.

  seerr_requests(filter_key PK, payload_json, fetched_at)
    Raw cache of what scripts/seerr/requests.sh returns for a given filter
    (all/approved/pending/etc). requests.sh itself makes one extra Overseerr
    API call per result just to resolve a title, so re-running it on every
    page load is expensive for no reason — see app/main.py, which also holds
    a lock across the live-fetch path so concurrent callers wait for one
    in-flight fetch instead of each kicking off their own.
"""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cache.db"
DEFAULT_TTL_SECONDS = 6 * 60 * 60  # 6 hours — availability changes during the day


def get_connection(db_path=DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn):
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
        CREATE TABLE IF NOT EXISTS seerr_requests (
            filter_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            fetched_at REAL NOT NULL
        );
        """
    )
    conn.commit()


REQUESTS_DEFAULT_TTL_SECONDS = 5 * 60  # 5 minutes — request/media status changes fairly often


def cache_requests(conn, filter_key, rows, fetched_at=None):
    """Overwrite the cached Overseerr request list for `filter_key` with
    `rows` (list of plain dicts, as returned by scripts/seerr/requests.sh)."""
    fetched_at = fetched_at if fetched_at is not None else time.time()
    conn.execute(
        """
        INSERT INTO seerr_requests (filter_key, payload_json, fetched_at)
        VALUES (?, ?, ?)
        ON CONFLICT(filter_key) DO UPDATE SET
            payload_json=excluded.payload_json,
            fetched_at=excluded.fetched_at
        """,
        (filter_key, json.dumps(rows), fetched_at),
    )
    conn.commit()


def get_cached_requests(conn, filter_key, ttl=REQUESTS_DEFAULT_TTL_SECONDS):
    """Returns the cached list of request dicts for `filter_key` if a
    fresh-enough entry exists, else None (a cache miss)."""
    cutoff = time.time() - ttl
    row = conn.execute(
        "SELECT payload_json FROM seerr_requests WHERE filter_key = ? AND fetched_at >= ?",
        (filter_key, cutoff),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def cache_search(conn, query, format_filter, records, fetched_at=None):
    """Overwrite the cached result set for (query, format_filter) with `records`
    (list of dicts with bib_id/title/subtitle/format/availability_status/
    available_copies/total_copies/publication_date/call_number/authors/
    match_score, in the order they should be returned in)."""
    fetched_at = fetched_at if fetched_at is not None else time.time()
    format_filter = format_filter or ""

    conn.execute(
        "DELETE FROM searches WHERE query = ? AND format_filter = ?",
        (query, format_filter),
    )
    for rank_order, record in enumerate(records):
        conn.execute(
            """
            INSERT INTO bibs (bib_id, title, subtitle, format, availability_status,
                available_copies, total_copies, publication_date, call_number, authors,
                match_score, fetched_at)
            VALUES (:bib_id, :title, :subtitle, :format, :availability_status,
                :available_copies, :total_copies, :publication_date, :call_number, :authors,
                :match_score, :fetched_at)
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
                fetched_at=excluded.fetched_at
            """,
            {**record, "fetched_at": fetched_at},
        )
        conn.execute(
            """
            INSERT INTO searches (query, format_filter, bib_id, rank_order, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (query, format_filter, record["bib_id"], rank_order, fetched_at),
        )
    conn.commit()


def get_cached_search(conn, query, format_filter, ttl=DEFAULT_TTL_SECONDS):
    """Returns the cached, ordered list of record dicts for (query,
    format_filter) if a fresh-enough entry exists, else None (a cache miss —
    caller should fetch live and call cache_search)."""
    format_filter = format_filter or ""
    cutoff = time.time() - ttl
    rows = conn.execute(
        """
        SELECT b.*, s.rank_order
        FROM searches s
        JOIN bibs b ON b.bib_id = s.bib_id
        WHERE s.query = ? AND s.format_filter = ? AND s.fetched_at >= ?
        ORDER BY s.rank_order
        """,
        (query, format_filter, cutoff),
    ).fetchall()
    if not rows:
        return None
    return [dict(row) for row in rows]
