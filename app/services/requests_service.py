"""Business logic for listing Overseerr requests joined with any chosen
library match and TMDB metadata. Orchestrates SeerrRepo + MatchRepo +
TmdbRepo; no HTTP or SQL of its own.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

STREAM_WORKERS = 10


class RequestsService:
    def __init__(self, seerr_repo, match_repo, tmdb_repo):
        self.seerr_repo = seerr_repo
        self.match_repo = match_repo
        self.tmdb_repo = tmdb_repo

    def get_requests(self, filter_key="all", force_refresh=False):
        """Returns (rows, source) — blocks until the whole batch resolves.
        Kept for callers that want a single response; see stream_requests
        for the progressive version the UI actually uses."""
        rows, source = self.seerr_repo.list_requests(filter_key, force_refresh=force_refresh)
        matches = self.match_repo.get_all_matches()
        tmdb_data = self.tmdb_repo.get_many((row["type"], row["tmdb_id"]) for row in rows)
        enriched = [
            {
                **row,
                "match": matches.get(row["id"]),
                "tmdb": tmdb_data.get((row["type"], row["tmdb_id"])),
            }
            for row in rows
        ]
        return enriched, source

    def stream_requests(self, filter_key="all", force_refresh=False):
        """Yields (row, source) pairs progressively as each request's title
        and TMDB data resolve, instead of blocking until the whole batch is
        ready — see app/controllers/requests_controller.py for the NDJSON
        transport this feeds. Each row already has `tmdb` merged in (unlike
        get_requests, which joins it on afterward) since resolving title and
        TMDB data together, per row, is what makes per-row streaming
        possible in the first place.

        Deliberately bypasses SingleFlightCache: there's nothing to replay
        to a second concurrent caller while the first is still mid-stream,
        and this is a single-user tool where two concurrent live fetches for
        the same filter is a rare enough edge case to just let happen
        independently rather than design around.

        On a cache hit, rows already carry the `tmdb` data they were cached
        with (up to SeerrRepo's 5-minute TTL stale) — replayed directly, no
        re-fetch. Only a cache miss does the live per-row pipeline.
        """
        matches = self.match_repo.get_all_matches()

        if not force_refresh:
            cached_rows = self.seerr_repo.get_cached_requests(filter_key)
            if cached_rows is not None:
                for row in cached_rows:
                    yield {**row, "match": matches.get(row["id"])}, "cache"
                return

        raw_items = self.seerr_repo.fetch_raw_requests(filter_key)
        assembled = []
        with ThreadPoolExecutor(max_workers=STREAM_WORKERS) as pool:
            futures = [pool.submit(self._resolve_and_enrich, raw) for raw in raw_items]
            for future in as_completed(futures):
                row = future.result()
                assembled.append(row)
                yield {**row, "match": matches.get(row["id"])}, "live"

        self.seerr_repo.cache_requests(filter_key, assembled)

    def _resolve_and_enrich(self, raw):
        media_type = raw["type"]
        tmdb_id = raw["media"]["tmdbId"]
        title = self.seerr_repo.fetch_title(media_type, tmdb_id)
        try:
            tmdb_record, _ = self.tmdb_repo.get(media_type, tmdb_id)
        except Exception:
            tmdb_record = None
        return {
            "id": raw["id"],
            "type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "request_status": raw["status"],
            "media_status": raw["media"]["status"],
            "requested_by": raw["requestedBy"]["displayName"],
            "tmdb": tmdb_record,
        }
