"""Business logic for reading/toggling feature switches. Thin wrapper around
app.lib.feature_switch's registry — lives here rather than in the controller
per the Controller->Service->Repo layering (see CLAUDE.md).
"""
from app.lib import feature_switch


class SettingsService:
    def list_switches(self):
        return feature_switch.list_switches()

    def set_switch(self, key, enabled, seconds=None):
        feature_switch.set_switch(key, enabled, seconds)
        return feature_switch.list_switches()
