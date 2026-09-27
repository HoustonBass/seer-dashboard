"""Business logic for saving/clearing a chosen Overseerr-request<->library
match. Thin today, but this is where future validation (e.g. rejecting a
match against a request that doesn't exist) belongs, not the controller.
"""
from app.repos.match_repo import WHOLE_ITEM_SEASON


class MatchService:
    def __init__(self, match_repo, library_repo):
        self.match_repo = match_repo
        self.library_repo = library_repo

    def save_match(self, data):
        season_number = data.get("season_number", WHOLE_ITEM_SEASON)
        bib_id = data.get("bib_id")
        self.match_repo.set_match(
            request_id=data["request_id"],
            season_number=season_number,
            tmdb_id=data.get("tmdb_id"),
            media_type=data.get("media_type"),
            seerr_title=data.get("seerr_title"),
            bib_id=bib_id,
            bib_title=data.get("bib_title"),
            bib_subtitle=data.get("bib_subtitle"),
            availability_status=data.get("availability_status"),
        )
        # Warm the branch-availability cache right away so the request
        # list's "at my branch" pill/filter (see RequestsService._join_match)
        # has data immediately instead of waiting for someone to click
        # "Which branches?" later, or for scripts/backfill_branch_cache.py
        # to run. Movies only (WHOLE_ITEM_SEASON) — TV's one-bib-per-season
        # shape makes this a bigger feature, deliberately out of scope for
        # now (see that script's same restriction). Best-effort: a live
        # BiblioCommons hiccup here shouldn't fail the match-save itself.
        if season_number == WHOLE_ITEM_SEASON and bib_id:
            try:
                self.library_repo.get_bib_branches(bib_id)
            except Exception:
                pass

    def mark_unavailable(self, data):
        self.match_repo.set_unavailable(
            request_id=data["request_id"],
            season_number=data.get("season_number", WHOLE_ITEM_SEASON),
            tmdb_id=data.get("tmdb_id"),
            media_type=data.get("media_type"),
            seerr_title=data.get("seerr_title"),
        )

    def clear_match(self, request_id, season_number=WHOLE_ITEM_SEASON):
        self.match_repo.clear_match(request_id, season_number)
