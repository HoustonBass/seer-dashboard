"""load_env()'s CONFIG_DIR/config.yaml path (containerized deployment) —
see app/lib/env.py and the Dockerfile. The .env path is exercised implicitly
by every other test module (conftest/fixtures rely on it existing), so it's
not retested here.
"""
import os

import pytest
import yaml

from app.lib import env

VALID_CONFIG = {
    "LIBRARY_USERNAME": "user",
    "LIBRARY_PASSWORD": "pw",
    "SEERR_BASE_URL": "https://seerr.example",
    "SEERR_API_KEY": "key",
    "TMDB_API_KEY": "tmdb-key",
}


def write_config(tmp_path, overrides=None):
    config = {**VALID_CONFIG, **(overrides or {})}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config))


@pytest.fixture(autouse=True)
def clean_env():
    # Every key load_env()/config.yaml can set — pop before and after so one
    # test's os.environ mutations can't leak into the next (same reasoning
    # as test_feature_switch.py's clean_env).
    keys = list(VALID_CONFIG) + ["CONFIG_DIR", "DATA_DIR", "LIBRARY_BASE_URL"]
    # load_env() sets os.environ directly (os.environ.setdefault), which
    # monkeypatch can't auto-revert on teardown — it only tracks changes made
    # through its own setenv/delenv. Pop before AND after, or one test's
    # config leaks into the next (same reasoning as test_feature_switch.py's
    # clean_env — found the same way, a later test seeing an unexpectedly
    # already-set var).
    for key in keys:
        os.environ.pop(key, None)
    yield
    for key in keys:
        os.environ.pop(key, None)


def test_missing_config_yaml_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="Missing config.yaml"):
        env.load_env()


def test_config_yaml_missing_required_field_exits(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, {"SEERR_API_KEY": None})

    with pytest.raises(SystemExit) as exc_info:
        env.load_env()
    assert exc_info.value.code == 1
    # Didn't get far enough to set any env vars — a partially-loaded config
    # would be worse than a config load that never happened at all.
    assert "LIBRARY_USERNAME" not in os.environ


def test_config_yaml_missing_field_logs_which_ones(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, {"SEERR_API_KEY": None, "TMDB_API_KEY": ""})

    with pytest.raises(SystemExit):
        env.load_env()

    assert "SEERR_API_KEY" in caplog.text
    assert "TMDB_API_KEY" in caplog.text
    assert "LIBRARY_USERNAME" not in caplog.text


def test_valid_config_yaml_populates_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, {"LIBRARY_BASE_URL": "https://library.example"})

    env.load_env()

    for key, value in VALID_CONFIG.items():
        assert os.environ[key] == value
    assert os.environ["LIBRARY_BASE_URL"] == "https://library.example"


def test_empty_optional_field_left_unset_not_stringified(tmp_path, monkeypatch):
    # LIBRARY_BASE_URL: with nothing after it parses to None — must not
    # become the literal string "None" (which is truthy, breaking
    # LibraryRepo's `os.environ.get(...) or default` fallback).
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    write_config(tmp_path, {"LIBRARY_BASE_URL": None})

    env.load_env()

    assert "LIBRARY_BASE_URL" not in os.environ


def test_data_dir_follows_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    assert env.data_dir() == tmp_path


def test_data_dir_override_wins_over_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    override = tmp_path / "override"
    monkeypatch.setenv("DATA_DIR", str(override))
    assert env.data_dir() == override
