"""Business logic for library catalog search. Joins LibraryRepo's ranked
results with MatchRepo so the frontend knows, per result, whether that
library item is already matched to some (possibly different) Overseerr
request — see MatchRepo.get_matches_by_bib_ids for why this cross-reference
exists. Lives here (not in the controller) so validation/ranking/join policy
changes don't require touching the HTTP layer.
"""


class SearchService:
    def __init__(self, library_repo, match_repo):
        self.library_repo = library_repo
        self.match_repo = match_repo

    def search(self, query, format_filter="", force_refresh=False):
        if not query:
            raise ValueError("query is required")
        results, source = self.library_repo.search(query, format_filter, force_refresh=force_refresh)

        matches_by_bib_id = self.match_repo.get_matches_by_bib_ids(r["bib_id"] for r in results)
        enriched = [
            {**r, "existing_match": self._existing_match_summary(matches_by_bib_id.get(r["bib_id"]))}
            for r in results
        ]
        return enriched, source

    def get_bib_edition(self, bib_id, force_refresh=False):
        """Disambiguates same-title search results — see
        LibraryRepo.get_bib_edition for why a live catalogBibs fetch stays
        its own on-demand call rather than happening for every search
        result up front. A cached edition (from a prior call, for any bib_id)
        is still surfaced automatically in search() results — see
        LibraryRepo._attach_cached_editions."""
        return self.library_repo.get_bib_edition(bib_id, force_refresh=force_refresh)

    @staticmethod
    def _existing_match_summary(match):
        if match is None:
            return None
        return {
            "request_id": match["request_id"],
            "seerr_title": match["seerr_title"],
            "media_type": match["media_type"],
        }
