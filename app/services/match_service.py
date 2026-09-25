"""Business logic for saving/clearing a chosen Overseerr-request<->library
match. Thin today, but this is where future validation (e.g. rejecting a
match against a request that doesn't exist) belongs, not the controller.
"""
from app.repos.match_repo import WHOLE_ITEM_SEASON


class MatchService:
    def __init__(self, match_repo):
        self.match_repo = match_repo

    def save_match(self, data):
        self.match_repo.set_match(
            request_id=data["request_id"],
            season_number=data.get("season_number", WHOLE_ITEM_SEASON),
            tmdb_id=data.get("tmdb_id"),
            media_type=data.get("media_type"),
            seerr_title=data.get("seerr_title"),
            bib_id=data.get("bib_id"),
            bib_title=data.get("bib_title"),
            bib_subtitle=data.get("bib_subtitle"),
            availability_status=data.get("availability_status"),
        )

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
