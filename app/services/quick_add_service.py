"""Business logic for "I found this in the library and want it in Overseerr
too" — search TMDB for candidates matching a library title, then create the
Overseerr request and record the library match in one action. Orchestrates
TmdbRepo (search), SeerrRepo (create the request), MatchRepo (persist the
match), and FailedQuickAddRepo (persist the attempt if SeerrRepo can't be
reached, so it can be retried later instead of lost — see CLAUDE.md's note
on the Overseerr host being flaky) — no HTTP or SQL of its own.
"""
from app.repos.match_repo import WHOLE_ITEM_SEASON


class QuickAddError(Exception):
    """Raised when add_and_match (or a retry of one) fails to create the
    Overseerr request. Carries the FailedQuickAddRepo row id the attempt was
    recorded under, so the controller can surface it to the frontend for a
    later retry."""

    def __init__(self, message, failed_id):
        super().__init__(message)
        self.failed_id = failed_id


class QuickAddService:
    def __init__(self, tmdb_repo, seerr_repo, match_repo, failed_repo, library_repo):
        self.tmdb_repo = tmdb_repo
        self.seerr_repo = seerr_repo
        self.match_repo = match_repo
        self.failed_repo = failed_repo
        self.library_repo = library_repo

    def search_candidates(self, query):
        if not query:
            raise ValueError("query is required")
        return self.tmdb_repo.search(query)

    def add_and_match(self, data):
        try:
            return self._create_and_match(data)
        except Exception as e:
            failed_id = self.failed_repo.record_new_failure(data, str(e))
            raise QuickAddError(str(e), failed_id) from e

    def list_failed(self):
        return self.failed_repo.list_all()

    def dismiss_failed(self, failed_id):
        self.failed_repo.delete(failed_id)

    def retry_failed(self, failed_id):
        row = self.failed_repo.get(failed_id)
        if row is None:
            raise ValueError(f"no failed quick-add with id {failed_id}")
        try:
            result = self._create_and_match(row["payload"])
        except Exception as e:
            self.failed_repo.record_retry_failure(failed_id, str(e))
            raise QuickAddError(str(e), failed_id) from e
        self.failed_repo.delete(failed_id)
        return result

    def _create_and_match(self, data):
        media_type = data["media_type"]
        tmdb_id = data["tmdb_id"]

        created = self.seerr_repo.create_request(media_type, tmdb_id, seasons=data.get("seasons"))

        # bib_id is omitted by the frontend for a TV candidate (see
        # QuickAddModal.jsx) — a library search result doesn't reliably tell
        # us which season it corresponds to, so TV quick-adds only create the
        # request; matching a specific season happens afterward through the
        # normal season accordion once the new request appears in the list.
        if data.get("bib_id"):
            season_number = data.get("season_number", WHOLE_ITEM_SEASON)
            self.match_repo.set_match(
                request_id=created["id"],
                season_number=season_number,
                tmdb_id=tmdb_id,
                media_type=media_type,
                seerr_title=data.get("title"),
                bib_id=data["bib_id"],
                bib_title=data["bib_title"],
                bib_subtitle=data.get("bib_subtitle"),
            )
            # Same reasoning as MatchService.save_match — warm the branch
            # cache so this shows up with "at my branch" data immediately,
            # movies only, best-effort.
            if season_number == WHOLE_ITEM_SEASON:
                try:
                    self.library_repo.get_bib_branches(data["bib_id"])
                except Exception:
                    pass
        return {"request_id": created["id"]}
