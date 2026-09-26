"""Loads config into os.environ from either repo-root .env (local dev,
default) or a mounted CONFIG_DIR's config.yaml (containerized deployment —
see Dockerfile). The .env path is the Python equivalent of scripts/lib/env.sh
— needed now that app/ talks to Overseerr/BiblioCommons natively instead of
shelling out to scripts that sourced .env themselves.
"""
import logging
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"

# Repos/services that hard-require a value (os.environ["KEY"], no fallback —
# see app/repos/*.py's __init__ methods). Checked against config.yaml at
# startup so a missing one is a clean log + exit instead of a KeyError deep
# inside some repo's constructor once the app's already serving requests.
REQUIRED_CONFIG_KEYS = ("LIBRARY_USERNAME", "LIBRARY_PASSWORD", "SEERR_BASE_URL", "SEERR_API_KEY", "TMDB_API_KEY")


def _config_dir():
    """Set by the container (see Dockerfile) to one mounted folder holding
    config.yaml, logs.txt, and (unless $DATA_DIR overrides it — see the
    real deployment's run command, which mounts the `data` git submodule
    separately) every *_cache.db/matches.db/library_auth_cache file.
    Unset for local dev, which keeps using repo-root .env + repo-root data/
    (itself a git submodule — see CLAUDE.md). Read fresh from os.environ
    (not cached at import time) so it reflects whatever the current
    process/test has set."""
    return os.environ.get("CONFIG_DIR")


def data_dir():
    """Where repos' SQLite files (and, under CONFIG_DIR with no DATA_DIR
    override, logs.txt) live. Resolution order: $DATA_DIR override >
    $CONFIG_DIR (containerized, flat mounted folder) > <repo root>/data
    (local dev default, also where the `data` submodule lands). $DATA_DIR
    lets a container mount the submodule-backed data dir separately from
    CONFIG_DIR's config.yaml/logs.txt, and also works standalone for a
    second local instance's scratch files (see APP_PORT)."""
    if os.environ.get("DATA_DIR"):
        return Path(os.environ["DATA_DIR"])
    config_dir = _config_dir()
    if config_dir:
        return Path(config_dir)
    return REPO_ROOT / "data"


def _configure_container_logging(config_dir):
    handler = logging.FileHandler(Path(config_dir) / "logs.txt")
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)


def load_env():
    config_dir = _config_dir()
    if config_dir:
        _configure_container_logging(config_dir)
        config_path = Path(config_dir) / "config.yaml"
        if not config_path.exists():
            raise RuntimeError(f"Missing config.yaml at {config_path} (copy config.yaml.example)")
        config = yaml.safe_load(config_path.read_text()) or {}
        missing = [key for key in REQUIRED_CONFIG_KEYS if not config.get(key)]
        if missing:
            logging.error(
                "config.yaml at %s is missing required field(s): %s — refusing to start",
                config_path, ", ".join(missing),
            )
            sys.exit(1)
        for key, value in config.items():
            if value is None:
                # An empty YAML value (`KEY:` with nothing after it) parses
                # to None — str(None) would literally set the env var to
                # "None", which is truthy and breaks repos' `os.environ.get
                # (...) or default` fallback for optional keys (e.g.
                # LibraryRepo's LIBRARY_BASE_URL). Leave it unset instead, so
                # that fallback actually fires, same as an empty .env line.
                continue
            os.environ.setdefault(key, str(value))
        return

    if not ENV_PATH.exists():
        raise RuntimeError(f"Missing .env at {ENV_PATH} (copy .env.example)")
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)
