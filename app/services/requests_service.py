"""Business logic for listing Overseerr requests joined with any chosen
library match and TMDB metadata. Orchestrates SeerrRepo + MatchRepo +
TmdbRepo; no HTTP or SQL of its own.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.repos.match_repo import WHOLE_ITEM_SEASON

STREAM_WORKERS = 10


class RequestsService:
    def __init__(self, seerr_repo, match_repo, tmdb_repo, library_repo):
        self.seerr_repo = seerr_repo
        self.match_repo = match_repo
        self.tmdb_repo = tmdb_repo
        self.library_repo = library_repo

    def get_requests(self, filter_key="all", force_refresh=False):
        """Returns (rows, source) — blocks until the whole batch resolves.
        Kept for callers that want a single response; see stream_requests
        for the progressive version the UI actually uses."""
        rows, source = self.seerr_repo.list_requests(filter_key, force_refresh=force_refresh)
        matches = self.match_repo.get_all_matches()
        tmdb_data = self.tmdb_repo.get_many((row["type"], row["tmdb_id"]) for row in rows)
        enriched = [
            {
                **self._join_match(row, matches),
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
        re-fetch. Only a cache miss does the live per-row pipeline. `match`/
        `season_matches` are joined fresh every time regardless of cache
        state, since those live in MatchRepo (a different cache entirely)
        and change independently of Overseerr/TMDB data.
        """
        matches = self.match_repo.get_all_matches()

        if not force_refresh:
            cached_rows = self.seerr_repo.get_cached_requests(filter_key)
            if cached_rows is not None:
                for row in cached_rows:
                    yield self._join_match(row, matches), "cache"
                return

        raw_items = self.seerr_repo.fetch_raw_requests(filter_key)
        assembled = []
        with ThreadPoolExecutor(max_workers=STREAM_WORKERS) as pool:
            futures = [pool.submit(self._resolve_and_enrich, raw) for raw in raw_items]
            for future in as_completed(futures):
                row = future.result()
                assembled.append(row)
                yield self._join_match(row, matches), "live"

        self.seerr_repo.cache_requests(filter_key, assembled)

    def _join_match(self, row, matches):
        """Merges MatchRepo's per-(request, season) decisions onto a row.

        `match` — the whole-item decision (season 0), which is the only kind
        movies ever have. Always None for TV. When present and matched to a
        bib_id, also carries `branches` — cached (never live-fetched here;
        see LibraryRepo.get_cached_branches) per-branch availability, so the
        frontend can flag "available at your preferred branch" without an
        extra round trip. Deliberately movie-only (TV's per-season match
        shape makes this a bigger feature, out of scope for now) — this
        falls out for free since only the whole-item match gets enriched,
        never season_matches.
        `season_matches` — {season_number: match_dict}, keyed by Overseerr's
        real season numbers. Only meaningful for TV (empty dict for movies).
        The frontend picks whichever of the two matters based on `row["type"]`
        rather than this method deciding — see RequestList.jsx/MatchPanel.jsx.
        """
        request_matches = matches.get(row["id"], {})
        match = request_matches.get(WHOLE_ITEM_SEASON)
        if match and match.get("bib_id"):
            match = {**match, "branches": self.library_repo.get_cached_branches(match["bib_id"])}
        return {
            **row,
            "match": match,
            "season_matches": request_matches,
        }

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
            "seasons": [s["seasonNumber"] for s in raw.get("seasons", [])],
        }
