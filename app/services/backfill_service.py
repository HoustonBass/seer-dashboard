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

Tracks an arbitrary number of concurrent named tasks (self._tasks, keyed by
task id) rather than one global running/completed/total, so the frontend's
BackgroundTasksPanel can show more than one progress bar at once — a real
backfill plus any number of simulated "Test progress bar" runs (see
start_test_task), which are deliberately never deduped against each other
since they're harmless and exist specifically to demo/exercise that UI.
Only the real backfill dedups against itself (one `branch_backfill` task at
a time — two overlapping real runs would just double the actual API
traffic without finishing any faster).
"""
import itertools
import threading
import time

from app.repos.match_repo import STATUS_MATCHED, WHOLE_ITEM_SEASON

BACKFILL_TASK_ID = "branch_backfill"
SIMULATED_TASK_STEPS = 20
SIMULATED_TASK_DELAY_SECONDS = 0.5


class BackfillService:
    def __init__(self, library_repo, match_repo):
        self.library_repo = library_repo
        self.match_repo = match_repo
        self._lock = threading.Lock()
        self._tasks = {}
        self._test_task_counter = itertools.count(1)

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
        with self._lock:
            return any(task["running"] for task in self._tasks.values())

    def status(self):
        """List of every known task (running or finished-but-not-yet-
        cleared) — {"id", "label", "running", "completed", "total"} each.
        Polled by BackgroundTasksPanel.jsx, one progress bar per task.
        completed/total persist after a task finishes (not reset to 0) so
        the frontend can show "20/20" briefly rather than snapping back to
        empty the instant the backend-side loop ends — tasks are only
        actually dropped from self._tasks when a fresh run reuses the same
        id (real backfill) or never, for test tasks (harmless — the process
        restarts long before that'd meaningfully accumulate)."""
        with self._lock:
            return list(self._tasks.values())

    def start_backfill(self, force=False):
        """Kicks off the throttled backfill in a background thread and
        returns immediately. Refuses to start a second *real* backfill
        concurrently (returns False) — see module docstring. `force=True`
        re-fetches every matched movie's branches (a "hard refresh"), not
        just the ones missing from the cache."""
        with self._lock:
            existing = self._tasks.get(BACKFILL_TASK_ID)
            if existing and existing["running"]:
                return False
            self._tasks[BACKFILL_TASK_ID] = {
                "id": BACKFILL_TASK_ID,
                "label": "Hard-refreshing branch cache" if force else "Refreshing branch cache",
                "running": True,
                "completed": 0,
                "total": 0,
            }
        threading.Thread(target=self._run_backfill, args=(force,), daemon=True).start()
        return True

    def start_test_task(self):
        """Runs a fake ~10s progression instead of touching movie_bib_ids()/
        library_repo at all — once everything's already cached, a real
        "fill missing only" run finds nothing to fetch and finishes in
        milliseconds, faster than the frontend's first status poll can ever
        observe, so the progress chip never has a chance to appear. This is
        what Settings' "Test progress bar" button uses to exercise that UI
        on demand — never deduped, so clicking it more than once (or
        Option/Alt+click, functionally identical — see SettingsPopover.jsx)
        runs several concurrently, to demo multiple tasks tracked at once."""
        task_id = f"test-{next(self._test_task_counter)}"
        with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "label": f"Test task #{task_id.split('-')[1]}",
                "running": True,
                "completed": 0,
                "total": SIMULATED_TASK_STEPS,
            }
        threading.Thread(target=self._run_test_task, args=(task_id,), daemon=True).start()
        return True

    def _increment(self, task_id):
        with self._lock:
            self._tasks[task_id]["completed"] += 1

    def _finish(self, task_id):
        with self._lock:
            self._tasks[task_id]["running"] = False

    def _run_backfill(self, force):
        try:
            bib_ids = self.movie_bib_ids()
            with self._lock:
                self._tasks[BACKFILL_TASK_ID]["total"] = len(bib_ids)
            for bib_id in bib_ids:
                if not force and self.library_repo.get_cached_branches(bib_id) is not None:
                    self._increment(BACKFILL_TASK_ID)
                    continue
                try:
                    self.library_repo.get_bib_branches(bib_id, force_refresh=force)
                except Exception:
                    pass
                self._increment(BACKFILL_TASK_ID)
                time.sleep(1)
        finally:
            self._finish(BACKFILL_TASK_ID)

    def _run_test_task(self, task_id):
        try:
            for _ in range(SIMULATED_TASK_STEPS):
                time.sleep(SIMULATED_TASK_DELAY_SECONDS)
                self._increment(task_id)
        finally:
            self._finish(task_id)
