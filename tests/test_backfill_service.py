"""BackfillService tests. Patches threading.Thread to run the target
synchronously (real threads would make assertions racy/nondeterministic) —
see the `sync_thread` fixture."""
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.services.backfill_service import BackfillService


@pytest.fixture
def sync_thread():
    class FakeThread:
        def __init__(self, target, args=(), daemon=None):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    with patch("app.services.backfill_service.threading.Thread", FakeThread):
        yield


def make_matches(*, matched_movie_bib_ids=(), tv_seasons=None, unavailable_bib_id=None):
    matches = {}
    for i, bib_id in enumerate(matched_movie_bib_ids, start=1):
        matches[i] = {0: {"status": "matched", "bib_id": bib_id}}
    if tv_seasons:
        matches[100] = tv_seasons
    if unavailable_bib_id:
        matches[200] = {0: {"status": "unavailable", "bib_id": None}}
    return matches


def test_movie_bib_ids_only_includes_matched_movies():
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = make_matches(
        matched_movie_bib_ids=["B1", "B2"],
        tv_seasons={1: {"status": "matched", "bib_id": "S1"}},  # TV: season key, never key 0
        unavailable_bib_id=True,
    )
    service = BackfillService(MagicMock(), match_repo)

    assert service.movie_bib_ids() == ["B1", "B2"]


def test_movie_bib_ids_dedupes_shared_bib_ids():
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = make_matches(matched_movie_bib_ids=["B1", "B1", "B2"])
    service = BackfillService(MagicMock(), match_repo)

    assert service.movie_bib_ids() == ["B1", "B2"]


def test_start_backfill_skips_already_cached_bib_ids_by_default(sync_thread):
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = make_matches(matched_movie_bib_ids=["CACHED", "MISSING"])
    library_repo = MagicMock()
    library_repo.get_cached_branches.side_effect = lambda bib_id: {"CACHED": ["x"]}.get(bib_id)

    with patch("app.services.backfill_service.time.sleep"):
        BackfillService(library_repo, match_repo).start_backfill(force=False)

    library_repo.get_bib_branches.assert_called_once_with("MISSING", force_refresh=False)


def test_start_backfill_force_refetches_even_cached_bib_ids(sync_thread):
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = make_matches(matched_movie_bib_ids=["CACHED"])
    library_repo = MagicMock()
    library_repo.get_cached_branches.return_value = ["already", "here"]

    with patch("app.services.backfill_service.time.sleep"):
        BackfillService(library_repo, match_repo).start_backfill(force=True)

    library_repo.get_bib_branches.assert_called_once_with("CACHED", force_refresh=True)


def test_start_backfill_isolates_a_single_fetch_failure(sync_thread):
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = make_matches(matched_movie_bib_ids=["BAD", "GOOD"])
    library_repo = MagicMock()
    library_repo.get_cached_branches.return_value = None
    library_repo.get_bib_branches.side_effect = [ConnectionError("boom"), (["ok"], "live")]

    with patch("app.services.backfill_service.time.sleep"):
        service = BackfillService(library_repo, match_repo)
        service.start_backfill()

    assert library_repo.get_bib_branches.call_count == 2
    assert service.is_running() is False  # cleaned up even after a failure


def test_start_backfill_refuses_a_concurrent_second_run():
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    service = BackfillService(MagicMock(), match_repo)
    service._running = True  # simulate an in-flight run

    assert service.start_backfill() is False


def test_start_backfill_marks_not_running_once_finished(sync_thread):
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    service = BackfillService(MagicMock(), match_repo)

    assert service.is_running() is False
    service.start_backfill()
    assert service.is_running() is False


def test_status_tracks_progress_and_persists_after_completion(sync_thread):
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = make_matches(matched_movie_bib_ids=["B1", "B2", "B3"])
    library_repo = MagicMock()
    library_repo.get_cached_branches.return_value = None

    with patch("app.services.backfill_service.time.sleep"):
        service = BackfillService(library_repo, match_repo)
        service.start_backfill()

    # Persists (doesn't reset to 0/0) so the frontend's progress bar can
    # show "3/3" briefly instead of snapping back to empty immediately.
    assert service.status() == {"running": False, "completed": 3, "total": 3}


def test_status_before_any_run():
    service = BackfillService(MagicMock(), MagicMock())
    assert service.status() == {"running": False, "completed": 0, "total": 0}


def test_status_counts_skipped_already_cached_entries_as_completed(sync_thread):
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = make_matches(matched_movie_bib_ids=["CACHED", "MISSING"])
    library_repo = MagicMock()
    library_repo.get_cached_branches.side_effect = lambda bib_id: {"CACHED": ["x"]}.get(bib_id)

    with patch("app.services.backfill_service.time.sleep"):
        service = BackfillService(library_repo, match_repo)
        service.start_backfill(force=False)

    assert service.status()["completed"] == 2


def test_real_thread_actually_used_when_not_patched():
    # Sanity check that start_backfill really does hand off to a thread in
    # normal operation (every other test here fakes that out) rather than
    # running synchronously and just happening to look async.
    match_repo = MagicMock()
    match_repo.get_all_matches.return_value = {}
    library_repo = MagicMock()
    service = BackfillService(library_repo, match_repo)

    with patch("app.services.backfill_service.threading.Thread", wraps=threading.Thread) as thread_cls:
        service.start_backfill()
        thread_cls.assert_called_once()
        assert thread_cls.call_args.kwargs.get("daemon") is True
