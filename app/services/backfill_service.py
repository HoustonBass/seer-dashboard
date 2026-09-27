"""Populates the branch-availability cache (see LibraryRepo.get_bib_branches
/ scripts/discovery/branch-availability.md) for matched movies, throttled to
1 request/second — a real account lock from heavy fetching during a
discovery session is documented in scripts/discovery/auth.md, this avoids
repeating that over a much longer-running batch.

Runs in a background thread (see start_backfill) since ~200+ movies at
1/sec is minutes, far past any reasonable HTTP request timeout — this is
what backs the Settings popover's "Refresh branch cache" button.
scripts/backfill_branch_cache.py (the CLI/docker-exec version) shares
movie_bib_ids() with this so the two can't drift on what counts as
"a matched movie" — only the throttled-fetch loop itself is separately
implemented there, so it can print progress a background thread can't.

TV explicitly excluded, same reasoning as MatchService.save_match: per-
season branch data (one bib per season, not per show) is a bigger feature,
out of scope for now.
"""
import threading
import time

from app.repos.match_repo import STATUS_MATCHED, WHOLE_ITEM_SEASON


class BackfillService:
    def __init__(self, library_repo, match_repo):
        self.library_repo = library_repo
        self.match_repo = match_repo
        self._lock = threading.Lock()
        self._running = False
        # completed/total persist after a run finishes (not reset to 0) so
        # the frontend's progress bar can show "207/207" briefly rather than
        # snapping back to empty the instant the backend-side loop ends —
        # see status(). Only reset at the start of the *next* run.
        self._completed = 0
        self._total = 0

    def movie_bib_ids(self):
        matches = self.match_repo.get_all_matches()
        return sorted(
            {
                seasons[WHOLE_ITEM_SEASON]["bib_id"]
                for seasons in matches.values()
                if WHOLE_ITEM_SEASON in seasons
                and seasons[WHOLE_ITEM_SEASON].get("status") == STATUS_MATCHED
                and seasons[WHOLE_ITEM_SEASON].get("bib_id")
            }
        )

    def is_running(self):
        return self._running

    def status(self):
        """{"running", "completed", "total"} — polled by the frontend's
        background-task progress bar (see BackgroundTasksPanel.jsx)."""
        return {"running": self._running, "completed": self._completed, "total": self._total}

    def start_backfill(self, force=False):
        """Kicks off the throttled backfill in a background thread and
        returns immediately. Refuses to start a second run concurrently
        (returns False) — two overlapping loops would just double the real
        API traffic without finishing any faster. `force=True` re-fetches
        every matched movie's branches (a "hard refresh"), not just the
        ones missing from the cache."""
        with self._lock:
            if self._running:
                return False
            self._running = True
        threading.Thread(target=self._run, args=(force,), daemon=True).start()
        return True

    def _run(self, force):
        try:
            bib_ids = self.movie_bib_ids()
            self._total = len(bib_ids)
            self._completed = 0
            for bib_id in bib_ids:
                if not force and self.library_repo.get_cached_branches(bib_id) is not None:
                    self._completed += 1
                    continue
                try:
                    self.library_repo.get_bib_branches(bib_id, force_refresh=force)
                except Exception:
                    pass
                self._completed += 1
                time.sleep(1)
        finally:
            self._running = False
