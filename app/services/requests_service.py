"""Business logic for listing Overseerr requests joined with any chosen
library match and TMDB metadata. Orchestrates SeerrRepo + MatchRepo +
TmdbRepo; no HTTP or SQL of its own.
"""


class RequestsService:
    def __init__(self, seerr_repo, match_repo, tmdb_repo):
        self.seerr_repo = seerr_repo
        self.match_repo = match_repo
        self.tmdb_repo = tmdb_repo

    def get_requests(self, filter_key="all", force_refresh=False):
        """Returns (rows, source) — rows have Overseerr's fields plus `match`
        (the chosen library record for that request, or None) and `tmdb`
        (release_date/overview/genres/poster_path/director/cast/runtime, or
        None if that lookup failed — see TmdbRepo.get_many)."""
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
