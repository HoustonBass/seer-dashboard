"""Business logic for the library account summary (checkouts + holds count).
Thin pass-through to LibraryRepo today — lives here so future logic (e.g.
warning thresholds) doesn't require touching the HTTP layer.
"""


class AccountService:
    def __init__(self, library_repo):
        self.library_repo = library_repo

    def get_dvd_activity_count(self, force_refresh=False):
        return self.library_repo.get_dvd_activity_count(force_refresh=force_refresh)
