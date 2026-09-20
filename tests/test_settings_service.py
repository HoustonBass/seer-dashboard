import os

import pytest

from app.lib import feature_switch
from app.services.settings_service import SettingsService


@pytest.fixture(autouse=True)
def clean_env():
    # See tests/test_feature_switch.py's clean_env for why this needs an
    # explicit before-and-after (not just monkeypatch.delenv) — set_switch
    # mutates os.environ directly, which monkeypatch can't auto-revert.
    env_vars = [meta["env_var"] for meta in feature_switch.REGISTRY.values()]
    for env_var in env_vars:
        os.environ.pop(env_var, None)
    yield
    for env_var in env_vars:
        os.environ.pop(env_var, None)


def test_list_switches_delegates_to_feature_switch():
    service = SettingsService()
    switches = service.list_switches()
    assert any(s["key"] == "seerr_fetch_delay" for s in switches)


def test_set_switch_returns_updated_list():
    service = SettingsService()
    switches = service.set_switch("seerr_fetch_delay", True, seconds=4)
    updated = {s["key"]: s for s in switches}
    assert updated["seerr_fetch_delay"]["enabled"] is True
    assert updated["seerr_fetch_delay"]["seconds"] == 4.0
