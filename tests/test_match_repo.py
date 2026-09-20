"""MatchRepo tests — pure SQLite persistence, no external API involved."""
from app.repos.match_repo import MatchRepo


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
    assert repo.get_all_matches() == {1: match}


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
