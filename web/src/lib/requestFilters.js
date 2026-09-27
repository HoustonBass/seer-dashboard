import { seasonNumberWord } from "./labels";

// "unmatched"/"matched"/"matched_waiting" aren't Overseerr request statuses —
// Overseerr has no concept of our library match. They're client-side filters
// over whatever got loaded, not a value passed to /api/requests?filter=;
// anything not in this set falls back to "all" for the actual backend query.
export const OVERSEERR_FILTERS = new Set(["all", "available", "processing"]);

// Already-available requests don't need a library match — there's nothing
// left to hunt down, Overseerr already has it covered. For TV, "unmatched"
// means at least one requested season still has no decision at all (neither
// matched nor confirmed unavailable). Shared between the "unmatched" filter
// and Option/Alt+click's "advance to the next unmatched" behavior, so the
// two can't drift apart on what "unmatched" means.
export function isUnmatchedRequest(r) {
  if (Number(r.media_status) === 5) return false;
  if (r.type === "tv" && r.seasons?.length > 0) {
    return r.seasons.some((s) => !r.season_matches?.[s]);
  }
  return !r.match;
}

// Every requested season/the whole item has a library match — shared by the
// "matched" filter and "matched, waiting" below so they can't drift apart on
// what "matched" means.
export function isFullyMatchedRequest(r) {
  if (r.type === "tv" && r.seasons?.length > 0) {
    return r.seasons.length > 0 && r.seasons.every((s) => r.season_matches?.[s]?.status === "matched");
  }
  return r.match?.status === "matched";
}

// The "matched" status pill's opposite number — at least one requested
// season (or the whole item) came back confirmed absent from the catalog.
export function isUnavailableInLibrary(r) {
  if (r.type === "tv" && r.seasons?.length > 0) {
    return r.seasons.some((s) => r.season_matches?.[s]?.status === "unavailable");
  }
  return r.match?.status === "unavailable";
}

// Applies the header dropdown's status filter. `requests` may be null
// (still loading) — passed through untouched so callers don't need their
// own null check on top of this one.
export function filterByStatus(requests, filter) {
  if (requests === null) return null;
  if (filter === "unmatched") return requests.filter(isUnmatchedRequest);
  if (filter === "matched") return requests.filter(isFullyMatchedRequest);
  if (filter === "matched_waiting") {
    return requests.filter((r) => isFullyMatchedRequest(r) && Number(r.media_status) !== 5);
  }
  if (filter === "unavailable") return requests.filter(isUnavailableInLibrary);
  return requests;
}

// Client-side, over whatever the status filter already produced — same
// pattern as that filter, no backend round-trip. Matches title, requester,
// and director (not just title) since all three are already on each row;
// RequestList's search hint strip surfaces that scope so a match on a name
// that isn't visibly "in" the title doesn't look like a bug.
export function searchRequests(requests, searchQuery) {
  const searchNorm = searchQuery.trim().toLowerCase();
  if (requests === null || !searchNorm) return requests;
  return requests.filter((r) =>
    [r.title, r.requested_by, r.tmdb?.director].some((field) => field?.toLowerCase().includes(searchNorm)),
  );
}

// Mirrors the query MatchSearchBox's autoSearchKey effect builds for a
// request (see MatchPanel.jsx) — must stay in sync with that or a prefetch
// built from this warms a cache key the real search never asks for.
export function defaultSearchQueryFor(request) {
  if (request.type === "tv" && request.seasons?.length > 0) {
    const season = [...request.seasons].sort((a, b) => a - b).find((s) => !request.season_matches?.[s]);
    if (season == null) return null;
    return `${request.title} season ${seasonNumberWord(season)}`;
  }
  return request.title;
}
