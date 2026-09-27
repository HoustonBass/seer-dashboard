"""One-time (or re-runnable) maintenance script: populates the branch-
availability cache (see LibraryRepo.get_bib_branches / scripts/discovery/
branch-availability.md) for every already-matched MOVIE request that doesn't
already have it cached. New matches get this automatically going forward
(see MatchService.save_match / QuickAddService._create_and_match) — this is
only for matches made before that existed.

Same underlying logic as the Settings popover's "Refresh branch cache"
button (see app/services/backfill_service.py, which owns movie_bib_ids() so
the two can't drift on what counts as "a matched movie") — this CLI version
exists for printed progress and to run against the homelab's live data
directly, without going through the running app's HTTP surface.

TV explicitly excluded, same reasoning as MatchService.save_match: per-
season branch data (one bib per season, not per show) is a bigger feature,
out of scope for now.

Throttled to 1 request/second — a real account lock from heavy fetching
during a discovery session is documented in scripts/discovery/auth.md; this
avoids repeating that over a much longer-running batch.

Usage (from repo root, same env as app.main — CONFIG_DIR or repo-root .env):
    python3 -m scripts.backfill_branch_cache

Or against the homelab's live data, from inside its running container:
    docker exec seerr-dashboard python3 -m scripts.backfill_branch_cache
"""
import time

from app.lib.env import load_env
from app.repos.library_repo import LibraryRepo
from app.repos.match_repo import MatchRepo
from app.services.backfill_service import BackfillService


def main():
    load_env()
    library_repo = LibraryRepo()
    match_repo = MatchRepo()
    bib_ids = BackfillService(library_repo, match_repo).movie_bib_ids()

    print(f"{len(bib_ids)} matched movie bib_ids to check")
    for i, bib_id in enumerate(bib_ids, start=1):
        if library_repo.get_cached_branches(bib_id) is not None:
            print(f"[{i}/{len(bib_ids)}] {bib_id}: already cached, skipping")
            continue
        try:
            branches, _ = library_repo.get_bib_branches(bib_id)
            print(f"[{i}/{len(bib_ids)}] {bib_id}: {len(branches)} branch(es)")
        except Exception as e:
            print(f"[{i}/{len(bib_ids)}] {bib_id}: FAILED — {e}")
        time.sleep(1)


if __name__ == "__main__":
    main()
