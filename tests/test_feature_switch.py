"""feature_switch.py's registry drives the /api/settings UI — these tests
guard the env-var mutation logic directly, without needing Flask."""
import os

import pytest

from app.lib import feature_switch


@pytest.fixture(autouse=True)
def clean_env():
    # feature_switch.set_switch() mutates os.environ directly (that's the
    # point — it's meant to take effect process-wide immediately), so
    # monkeypatch.setenv/delenv can't auto-revert it: monkeypatch only
    # tracks changes made through its own setenv/delenv calls. Without this
    # explicit before-and-after cleanup, a switch enabled by one test leaks
    # into every later test in the same pytest process — including
    # unrelated SeerrRepo/LibraryRepo tests, which then actually sleep for
    # real seconds on every fetch. (Found the hard way: a clean ~1s test
    # run became an 88s one.)
    env_vars = [meta["env_var"] for meta in feature_switch.REGISTRY.values()]
    for env_var in env_vars:
        os.environ.pop(env_var, None)
    yield
    for env_var in env_vars:
        os.environ.pop(env_var, None)


def test_list_switches_reports_disabled_by_default():
    switches = feature_switch.list_switches()
    keys = {s["key"] for s in switches}
    assert keys == set(feature_switch.REGISTRY.keys())
    assert all(not s["enabled"] for s in switches)


def test_set_switch_enables_with_default_seconds():
    feature_switch.set_switch("seerr_fetch_delay", True)
    switches = {s["key"]: s for s in feature_switch.list_switches()}
    assert switches["seerr_fetch_delay"]["enabled"] is True
    assert switches["seerr_fetch_delay"]["seconds"] == feature_switch.REGISTRY["seerr_fetch_delay"]["default_seconds"]


def test_set_switch_enables_with_custom_seconds():
    feature_switch.set_switch("library_fetch_delay", True, seconds=7)
    switches = {s["key"]: s for s in feature_switch.list_switches()}
    assert switches["library_fetch_delay"]["enabled"] is True
    assert switches["library_fetch_delay"]["seconds"] == 7.0


def test_set_switch_disable_clears_env_var():
    feature_switch.set_switch("seerr_fetch_delay", True, seconds=5)
    feature_switch.set_switch("seerr_fetch_delay", False)
    switches = {s["key"]: s for s in feature_switch.list_switches()}
    assert switches["seerr_fetch_delay"]["enabled"] is False


def test_set_switch_rejects_unknown_key():
    with pytest.raises(KeyError):
        feature_switch.set_switch("not-a-real-switch", True)


def test_delay_switch_sleeps_when_enabled(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(feature_switch.time, "sleep", lambda s: sleep_calls.append(s))

    feature_switch.set_switch("seerr_fetch_delay", True, seconds=2.5)
    feature_switch.delay_switch(feature_switch.REGISTRY["seerr_fetch_delay"]["env_var"])

    assert sleep_calls == [2.5]


def test_delay_switch_noop_when_disabled(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(feature_switch.time, "sleep", lambda s: sleep_calls.append(s))

    feature_switch.delay_switch(feature_switch.REGISTRY["seerr_fetch_delay"]["env_var"])

    assert sleep_calls == []
