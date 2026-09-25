"""FailedQuickAddRepo tests — pure SQLite persistence, no external API involved."""
from app.repos.failed_quick_add_repo import FailedQuickAddRepo


def test_list_all_starts_empty(tmp_path):
    repo = FailedQuickAddRepo(db_path=tmp_path / "failed.db")
    assert repo.list_all() == []


def test_record_new_failure_then_get_and_list(tmp_path):
    repo = FailedQuickAddRepo(db_path=tmp_path / "failed.db")
    payload = {"media_type": "movie", "tmdb_id": 17529, "title": "True Grit"}

    failed_id = repo.record_new_failure(payload, "Overseerr unreachable")

    row = repo.get(failed_id)
    assert row["payload"] == payload
    assert row["error"] == "Overseerr unreachable"
    assert row["attempts"] == 1

    listed = repo.list_all()
    assert len(listed) == 1
    assert listed[0]["id"] == failed_id


def test_record_retry_failure_increments_attempts_in_place(tmp_path):
    repo = FailedQuickAddRepo(db_path=tmp_path / "failed.db")
    failed_id = repo.record_new_failure({"tmdb_id": 1}, "first error")

    repo.record_retry_failure(failed_id, "second error")

    row = repo.get(failed_id)
    assert row["attempts"] == 2
    assert row["error"] == "second error"
    assert len(repo.list_all()) == 1  # updated in place, not a second row


def test_delete_removes_the_row(tmp_path):
    repo = FailedQuickAddRepo(db_path=tmp_path / "failed.db")
    failed_id = repo.record_new_failure({"tmdb_id": 1}, "error")

    repo.delete(failed_id)

    assert repo.get(failed_id) is None
    assert repo.list_all() == []


def test_get_returns_none_for_unknown_id(tmp_path):
    repo = FailedQuickAddRepo(db_path=tmp_path / "failed.db")
    assert repo.get(999) is None
