"""Loads .env from the repo root into os.environ. Python equivalent of
scripts/lib/env.sh — needed now that app/ talks to Overseerr/BiblioCommons
natively instead of shelling out to scripts that sourced .env themselves."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"


def load_env():
    if not ENV_PATH.exists():
        raise RuntimeError(f"Missing .env at {ENV_PATH} (copy .env.example)")
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)
