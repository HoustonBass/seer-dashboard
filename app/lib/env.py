"""Loads config into os.environ from either repo-root .env (local dev,
default) or a mounted CONFIG_DIR's config.yaml (containerized deployment —
see Dockerfile). The .env path is the Python equivalent of scripts/lib/env.sh
— needed now that app/ talks to Overseerr/BiblioCommons natively instead of
shelling out to scripts that sourced .env themselves.
"""
import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"

# Set by the container (see Dockerfile) to one mounted folder holding
# config.yaml, logs.txt, and every *_cache.db/matches.db/library_auth_cache
# file — a single bind-mount instead of separate .env + data/ mounts. Unset
# for local dev, which keeps using repo-root .env + repo-root data/.
CONFIG_DIR = os.environ.get("CONFIG_DIR")


def data_dir():
    """Where repos' SQLite files (and, under CONFIG_DIR, logs.txt) live.
    Resolution order: $DATA_DIR override > $CONFIG_DIR (containerized —
    everything flat in one mounted folder) > <repo root>/data (local dev
    default). $DATA_DIR still works standalone for a second local instance's
    scratch files (see APP_PORT), independent of CONFIG_DIR."""
    if os.environ.get("DATA_DIR"):
        return Path(os.environ["DATA_DIR"])
    if CONFIG_DIR:
        return Path(CONFIG_DIR)
    return REPO_ROOT / "data"


def load_env():
    if CONFIG_DIR:
        config_path = Path(CONFIG_DIR) / "config.yaml"
        if not config_path.exists():
            raise RuntimeError(f"Missing config.yaml at {config_path} (copy config.yaml.example)")
        config = yaml.safe_load(config_path.read_text()) or {}
        for key, value in config.items():
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
