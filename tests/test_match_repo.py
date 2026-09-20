"""MatchRepo tests — pure SQLite persistence, no external API involved."""
import sqlite3

from app.repos.match_repo import STATUS_MATCHED, STATUS_UNAVAILABLE, MatchRepo


def test_get_match_and_get_all_matches_start_empty(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    assert repo.get_match(1) is None
    assert repo.get_all_matches() == {}


def test_set_then_get_match(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(
        request_id=1, tmdb_id=100, media_type="movie",
        seerr_title="The Terminator", bib_id="B1", bib_title="The Terminator", bib_subtitle="",
    )

    match = repo.get_match(1)
    assert match["bib_id"] == "B1"
    assert match["seerr_title"] == "The Terminator"
    assert match["status"] == STATUS_MATCHED
    assert repo.get_all_matches() == {1: match}


def test_set_unavailable_has_no_bib_and_correct_status(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_unavailable(request_id=1, tmdb_id=100, media_type="movie", seerr_title="The Terminator")

    match = repo.get_match(1)
    assert match["status"] == STATUS_UNAVAILABLE
    assert match["bib_id"] is None
    assert match["bib_title"] is None


def test_set_unavailable_then_set_match_overwrites_to_matched(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_unavailable(1, 100, "movie", "A")
    repo.set_match(1, 100, "movie", "A", "B1", "A", "")

    match = repo.get_match(1)
    assert match["status"] == STATUS_MATCHED
    assert match["bib_id"] == "B1"


def test_set_match_then_set_unavailable_clears_bib_fields(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, 100, "movie", "A", "B1", "A", "")
    repo.set_unavailable(1, 100, "movie", "A")

    match = repo.get_match(1)
    assert match["status"] == STATUS_UNAVAILABLE
    assert match["bib_id"] is None


def test_migrates_pre_existing_db_missing_status_column(tmp_path):
    db_path = tmp_path / "old_schema.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE matches (
            request_id INTEGER PRIMARY KEY,
            tmdb_id INTEGER,
            media_type TEXT,
            seerr_title TEXT,
            bib_id TEXT,
            bib_title TEXT,
            bib_subtitle TEXT,
            decided_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO matches VALUES (1, 100, 'movie', 'A', 'B1', 'A', '', 123.0)"
    )
    conn.commit()
    conn.close()

    # Pre-existing rows predate "unavailable" entirely, so they're all real
    # matches — the DEFAULT on the migrated column should backfill them as
    # STATUS_MATCHED without a separate UPDATE statement.
    repo = MatchRepo(db_path=db_path)
    assert repo.get_match(1)["status"] == STATUS_MATCHED


def test_set_match_upserts_on_same_request_id(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, 100, "movie", "A", "B1", "A", "")
    repo.set_match(1, 100, "movie", "A", "B2", "A (different edition)", "")

    match = repo.get_match(1)
    assert match["bib_id"] == "B2"
    assert len(repo.get_all_matches()) == 1  # not two rows


def test_clear_match_removes_it(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, 100, "movie", "A", "B1", "A", "")
    repo.clear_match(1)

    assert repo.get_match(1) is None
    assert repo.get_all_matches() == {}


def test_matches_persist_across_separate_repo_instances(tmp_path):
    db_path = tmp_path / "matches.db"
    MatchRepo(db_path=db_path).set_match(1, 100, "movie", "A", "B1", "A", "")

    reopened = MatchRepo(db_path=db_path)
    assert reopened.get_match(1)["bib_id"] == "B1"
