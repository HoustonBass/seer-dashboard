"""Env-var-controlled switches for behavior that's only ever turned on
deliberately. `REGISTRY` is the single source of truth for which switches
exist — the /api/settings endpoint (app/controllers/settings_controller.py)
lists and toggles exactly these, so a new switch just needs an entry here to
show up in the UI, no separate wiring.

Switches are process-only state (mutate os.environ at runtime) — deliberately
not persisted to disk. These are debug/test knobs; resetting to off on
restart is the right default, not a gap.
"""
import os
import time

REGISTRY = {
    "seerr_fetch_delay": {
        "label": "Overseerr fetch delay",
        "description": (
            "Artificially slow SeerrRepo's live fetch so single-flight/cache "
            "concurrency behavior can be reproduced on demand instead of "
            "needing 245 real slow requests to create a wide enough race window."
        ),
        "env_var": "SEERR_TEST_FETCH_DELAY_SECONDS",
        "default_seconds": 3,
    },
    "library_fetch_delay": {
        "label": "Library fetch delay",
        "description": (
            "Same idea for LibraryRepo's live search fetch — forces it slow "
            "enough to reliably observe concurrent callers waiting on the cache."
        ),
        "env_var": "LIBRARY_TEST_FETCH_DELAY_SECONDS",
        "default_seconds": 3,
    },
}


def delay_switch(env_var):
    """If the given env var is set to a number, sleep that many seconds."""
    raw = os.environ.get(env_var)
    if raw:
        time.sleep(float(raw))


def list_switches():
    return [
        {
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "enabled": bool(os.environ.get(meta["env_var"])),
            "seconds": float(os.environ[meta["env_var"]]) if os.environ.get(meta["env_var"]) else meta["default_seconds"],
        }
        for key, meta in REGISTRY.items()
    ]


def set_switch(key, enabled, seconds=None):
    if key not in REGISTRY:
        raise KeyError(f"unknown feature switch: {key}")
    meta = REGISTRY[key]
    if enabled:
        os.environ[meta["env_var"]] = str(seconds if seconds is not None else meta["default_seconds"])
    else:
        os.environ.pop(meta["env_var"], None)
