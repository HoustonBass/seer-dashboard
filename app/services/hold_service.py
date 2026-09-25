"""Business logic for placing a real library hold on a matched item and
recording the resulting hold id against that match. Orchestrates LibraryRepo
(the actual hold call) and MatchRepo (persisting hold_id) — no HTTP of its
own. See scripts/discovery/hold.md: place is confirmed live; cancel is not
implemented here (still unconfirmed).
"""
from app.repos.match_repo import WHOLE_ITEM_SEASON


class HoldService:
    def __init__(self, library_repo, match_repo):
        self.library_repo = library_repo
        self.match_repo = match_repo

    def place_hold(self, data):
        bib_id = data["bib_id"]
        request_id = data["request_id"]
        season_number = data.get("season_number", WHOLE_ITEM_SEASON)

        result = self.library_repo.place_hold(bib_id, branch_id=data.get("branch_id"))
        self.match_repo.set_hold_id(request_id, season_number, result["hold_id"])
        return result
