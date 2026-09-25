"""MatchRepo tests — pure SQLite persistence, no external API involved."""
import sqlite3

from app.repos.match_repo import STATUS_MATCHED, STATUS_UNAVAILABLE, WHOLE_ITEM_SEASON, MatchRepo


def test_get_match_and_get_all_matches_start_empty(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    assert repo.get_match(1) is None
    assert repo.get_all_matches() == {}


def test_set_then_get_match_uses_whole_item_season_by_default(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(
        request_id=1, season_number=WHOLE_ITEM_SEASON, tmdb_id=100, media_type="movie",
        seerr_title="The Terminator", bib_id="B1", bib_title="The Terminator", bib_subtitle="",
    )

    match = repo.get_match(1)  # default season_number=WHOLE_ITEM_SEASON
    assert match["bib_id"] == "B1"
    assert match["seerr_title"] == "The Terminator"
    assert match["status"] == STATUS_MATCHED
    assert repo.get_all_matches() == {1: {WHOLE_ITEM_SEASON: match}}


def test_tv_request_can_have_multiple_independent_season_matches(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, 1, 100, "tv", "Brooklyn Nine-Nine", "B1", "Brooklyn Nine-Nine", "Season One")
    repo.set_match(1, 2, 100, "tv", "Brooklyn Nine-Nine", "B2", "Brooklyn Nine-Nine", "Season Two")
    repo.set_unavailable(1, 4, 100, "tv", "Brooklyn Nine-Nine")

    assert repo.get_match(1, 1)["bib_id"] == "B1"
    assert repo.get_match(1, 2)["bib_id"] == "B2"
    assert repo.get_match(1, 4)["status"] == STATUS_UNAVAILABLE
    assert repo.get_match(1, 3) is None  # never decided

    all_matches = repo.get_all_matches()
    assert set(all_matches[1].keys()) == {1, 2, 4}


def test_set_unavailable_has_no_bib_and_correct_status(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_unavailable(request_id=1, season_number=WHOLE_ITEM_SEASON, tmdb_id=100, media_type="movie", seerr_title="The Terminator")

    match = repo.get_match(1)
    assert match["status"] == STATUS_UNAVAILABLE
    assert match["bib_id"] is None
    assert match["bib_title"] is None


def test_set_unavailable_then_set_match_overwrites_to_matched(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_unavailable(1, WHOLE_ITEM_SEASON, 100, "movie", "A")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "")

    match = repo.get_match(1)
    assert match["status"] == STATUS_MATCHED
    assert match["bib_id"] == "B1"


def test_set_match_then_set_unavailable_clears_bib_fields(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "")
    repo.set_unavailable(1, WHOLE_ITEM_SEASON, 100, "movie", "A")

    match = repo.get_match(1)
    assert match["status"] == STATUS_UNAVAILABLE
    assert match["bib_id"] is None


def test_migrates_pre_existing_db_missing_status_and_season_columns(tmp_path):
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

    # Pre-existing rows predate both "unavailable" and per-season tracking —
    # they're all real whole-item matches, so the migration should land them
    # at status=STATUS_MATCHED, season_number=WHOLE_ITEM_SEASON automatically.
    repo = MatchRepo(db_path=db_path)
    match = repo.get_match(1)
    assert match["status"] == STATUS_MATCHED
    assert match["bib_id"] == "B1"

    # And the table should now support adding a real season-level match
    # alongside the migrated row without conflict.
    repo.set_match(1, 1, 100, "tv", "A", "B2", "A", "Season One")
    assert repo.get_match(1, WHOLE_ITEM_SEASON)["bib_id"] == "B1"
    assert repo.get_match(1, 1)["bib_id"] == "B2"


def test_set_match_upserts_on_same_request_and_season(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B2", "A (different edition)", "")

    match = repo.get_match(1)
    assert match["bib_id"] == "B2"
    assert len(repo.get_all_matches()[1]) == 1  # not two rows for the same season


def test_clear_match_removes_it(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "")
    repo.clear_match(1)

    assert repo.get_match(1) is None
    assert repo.get_all_matches() == {}


def test_clear_match_only_removes_the_specified_season(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, 1, 100, "tv", "A", "B1", "A", "Season One")
    repo.set_match(1, 2, 100, "tv", "A", "B2", "A", "Season Two")
    repo.clear_match(1, 1)

    assert repo.get_match(1, 1) is None
    assert repo.get_match(1, 2)["bib_id"] == "B2"


def test_set_match_stores_availability_status(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "", availability_status="UNAVAILABLE")

    assert repo.get_match(1)["availability_status"] == "UNAVAILABLE"


def test_set_hold_id_records_hold_against_existing_match(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "", availability_status="UNAVAILABLE")
    repo.set_hold_id(1, WHOLE_ITEM_SEASON, "11939290")

    assert repo.get_match(1)["hold_id"] == "11939290"


def test_set_match_clears_any_stale_hold_id_on_re_match(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "")
    repo.set_hold_id(1, WHOLE_ITEM_SEASON, "11939290")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B2", "A (different edition)", "")

    assert repo.get_match(1)["hold_id"] is None


def test_migrates_pre_existing_db_missing_availability_status_and_hold_id_columns(tmp_path):
    db_path = tmp_path / "old_schema.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"""
        CREATE TABLE matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            season_number INTEGER NOT NULL DEFAULT {WHOLE_ITEM_SEASON},
            tmdb_id INTEGER,
            media_type TEXT,
            seerr_title TEXT,
            bib_id TEXT,
            bib_title TEXT,
            bib_subtitle TEXT,
            status TEXT NOT NULL DEFAULT '{STATUS_MATCHED}',
            decided_at REAL NOT NULL,
            UNIQUE(request_id, season_number)
        )
        """
    )
    conn.execute(
        f"INSERT INTO matches (request_id, season_number, tmdb_id, media_type, seerr_title, bib_id, bib_title, bib_subtitle, status, decided_at) "
        f"VALUES (1, {WHOLE_ITEM_SEASON}, 100, 'movie', 'A', 'B1', 'A', '', '{STATUS_MATCHED}', 123.0)"
    )
    conn.commit()
    conn.close()

    repo = MatchRepo(db_path=db_path)
    match = repo.get_match(1)
    assert match["bib_id"] == "B1"
    assert match["availability_status"] is None
    assert match["hold_id"] is None

    repo.set_hold_id(1, WHOLE_ITEM_SEASON, "11939290")
    assert repo.get_match(1)["hold_id"] == "11939290"


def test_get_matches_by_bib_ids_returns_only_matched_status_for_requested_ids(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    repo.set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "Despicable Me 2", "B1", "Despicable Me 2", "")
    repo.set_match(2, WHOLE_ITEM_SEASON, 101, "movie", "Despicable Me 4", "B2", "Despicable Me 4", "")
    repo.set_unavailable(3, WHOLE_ITEM_SEASON, 102, "movie", "Despicable Me 3")

    result = repo.get_matches_by_bib_ids(["B1", "B2", "B3-not-matched"])

    assert set(result.keys()) == {"B1", "B2"}
    assert result["B2"]["request_id"] == 2
    assert result["B2"]["seerr_title"] == "Despicable Me 4"


def test_get_matches_by_bib_ids_empty_input_short_circuits(tmp_path):
    repo = MatchRepo(db_path=tmp_path / "matches.db")
    assert repo.get_matches_by_bib_ids([]) == {}


def test_matches_persist_across_separate_repo_instances(tmp_path):
    db_path = tmp_path / "matches.db"
    MatchRepo(db_path=db_path).set_match(1, WHOLE_ITEM_SEASON, 100, "movie", "A", "B1", "A", "")

    reopened = MatchRepo(db_path=db_path)
    assert reopened.get_match(1)["bib_id"] == "B1"
