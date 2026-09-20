"""Business logic for library catalog search. Currently a thin pass-through
to LibraryRepo — lives here (not in the controller) so validation/ranking
policy changes don't require touching the HTTP layer.
"""


class SearchService:
    def __init__(self, library_repo):
        self.library_repo = library_repo

    def search(self, query, format_filter="", force_refresh=False):
        if not query:
            raise ValueError("query is required")
        return self.library_repo.search(query, format_filter, force_refresh=force_refresh)
