// Thin wrapper over app/main.py's JSON API. Kept separate from components so
// swapping the backend later (e.g. for the real Jellyfin plugin's API) means
// changing this file, not every component that calls it.

// Mirrors app/repos/match_repo.py's WHOLE_ITEM_SEASON — movies (and any
// other whole-item decision) always use this; TV seasons use Overseerr's
// real season numbers, which are always >= 1, so this can never collide.
export const WHOLE_ITEM_SEASON = 0;

// /api/search returns { source: "cache"|"live", results } so the FE can show
// whether a response came from the repo's SQLite cache or a live API call —
// see app/repos/*_repo.py.

// /api/requests streams newline-delimited JSON — one `{"row": ..., "source":
// "cache"|"live"}` object per line — instead of one big array, so rows can
// render as each request's title/TMDB data resolves rather than waiting for
// the whole batch (a cold cache used to mean ~250 requests before anything
// appeared). `onRow` is called once per line as it arrives.
export async function streamRequests(filter = "all", { refresh = false, signal } = {}, onRow) {
  const params = new URLSearchParams({ filter });
  if (refresh) params.set("refresh", "1");
  const res = await fetch(`/api/requests?${params}`, { signal });
  if (!res.ok) throw new Error(`fetchRequests failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex;
    while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newlineIndex);
      buffer = buffer.slice(newlineIndex + 1);
      if (line.trim()) onRow(JSON.parse(line));
    }
  }
}

export async function searchLibrary(query, format = "", { refresh = false } = {}) {
  const params = new URLSearchParams({ query, format });
  if (refresh) params.set("refresh", "1");
  const res = await fetch(`/api/search?${params}`);
  if (!res.ok) throw new Error(`searchLibrary failed: ${res.status}`);
  return res.json();
}

// Disambiguates same-title/same-year search results that briefInfo alone
// can't tell apart (e.g. three "Pacific Rim" DVDs that are actually a
// rental edition, a two-disc special edition, and an anamorphic widescreen
// release) — see LibraryRepo.get_bib_edition. Fetched on demand per result,
// not baked into every /api/search response, since it's an extra live call
// per bib_id.
export async function fetchBibEdition(bibId) {
  const res = await fetch(`/api/search/${bibId}/edition`);
  if (!res.ok) throw new Error(`fetchBibEdition failed: ${res.status}`);
  return res.json();
}

// Which physical branches hold a copy of this bib, and each copy's status —
// see LibraryRepo.get_bib_branches / scripts/discovery/branch-availability.md.
// Same on-demand-per-bib_id shape as fetchBibEdition above.
export async function fetchBibBranches(bibId) {
  const res = await fetch(`/api/search/${bibId}/branches`);
  if (!res.ok) throw new Error(`fetchBibBranches failed: ${res.status}`);
  return res.json();
}

// `match`/the body for markUnavailable below may include `season_number` —
// omit it for a whole-item (movie) decision, include it for a specific TV
// season. See app/repos/match_repo.py's WHOLE_ITEM_SEASON for the default.
export async function saveMatch(match) {
  const res = await fetch("/api/matches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(match),
  });
  if (!res.ok) throw new Error(`saveMatch failed: ${res.status}`);
  return res.json();
}

// seasonNumber omitted -> whole-item decision (movies). Passed -> that TV
// season specifically — see app/repos/match_repo.py's WHOLE_ITEM_SEASON.
export async function clearMatch(requestId, seasonNumber) {
  const url = seasonNumber === undefined ? `/api/matches/${requestId}` : `/api/matches/${requestId}/${seasonNumber}`;
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok) throw new Error(`clearMatch failed: ${res.status}`);
  return res.json();
}

export async function markUnavailable(match) {
  const res = await fetch("/api/matches/unavailable", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(match),
  });
  if (!res.ok) throw new Error(`markUnavailable failed: ${res.status}`);
  return res.json();
}

// Quick-add: "found this in the library, want it in Overseerr too" — search
// TMDB for candidates matching a library title, then create the Overseerr
// request and mark it matched in one action. See MatchPanel's SeasonAccordion note:
// TV candidates only create the request (whole series); marking a specific
// season's match still happens through the normal season accordion once the
// new request shows up in the list, since a library search result doesn't
// reliably tell us which season it corresponds to.
export async function searchTmdb(query) {
  const params = new URLSearchParams({ query });
  const res = await fetch(`/api/quick-add/search?${params}`);
  if (!res.ok) throw new Error(`searchTmdb failed: ${res.status}`);
  return res.json();
}

export async function quickAdd(payload) {
  const res = await fetch("/api/quick-add", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error || `quickAdd failed: ${res.status}`);
  return body;
}

// Failed quick-adds: attempts that couldn't reach Overseerr (see
// app/repos/failed_quick_add_repo.py) — saved instead of lost so they can be
// retried once the connection's back, via the header's FailedQuickAdds
// popover.
export async function listFailedQuickAdds() {
  const res = await fetch("/api/quick-add/failed");
  if (!res.ok) throw new Error(`listFailedQuickAdds failed: ${res.status}`);
  return res.json();
}

export async function retryFailedQuickAdd(failedId) {
  const res = await fetch(`/api/quick-add/failed/${failedId}/retry`, { method: "POST" });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error || `retryFailedQuickAdd failed: ${res.status}`);
  return body;
}

export async function dismissFailedQuickAdd(failedId) {
  const res = await fetch(`/api/quick-add/failed/${failedId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`dismissFailedQuickAdd failed: ${res.status}`);
  return res.json();
}

// Places a REAL hold on the live library account — see
// app/repos/library_repo.py's place_hold and scripts/discovery/hold.md.
// `season_number` matters for TV (which season's match record gets the
// resulting hold_id); omit it for a movie/whole-item match.
export async function placeHold({ request_id, season_number, bib_id, branch_id }) {
  const res = await fetch("/api/holds", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id, season_number, bib_id, branch_id }),
  });
  if (!res.ok) throw new Error(`placeHold failed: ${res.status}`);
  return res.json();
}

// Combined "checked out or on hold" count for physical DVDs — see
// app/repos/library_repo.py's get_dvd_activity_count and
// scripts/discovery/account.md. Read-only; does not place/cancel anything.
export async function fetchDvdActivityCount({ refresh = false } = {}) {
  const params = new URLSearchParams();
  if (refresh) params.set("refresh", "1");
  const res = await fetch(`/api/account/dvd-count?${params}`);
  if (!res.ok) throw new Error(`fetchDvdActivityCount failed: ${res.status}`);
  return res.json();
}

export async function fetchSettings() {
  const res = await fetch("/api/settings");
  if (!res.ok) throw new Error(`fetchSettings failed: ${res.status}`);
  return res.json();
}

export async function setSetting(key, enabled, seconds) {
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, enabled, seconds }),
  });
  if (!res.ok) throw new Error(`setSetting failed: ${res.status}`);
  return res.json();
}

// Kicks off the branch-availability backfill (see
// app/services/backfill_service.py) — fills in missing entries only unless
// force is true (re-fetches every matched movie, a "hard refresh"). Returns
// {started} or, if one's already running, a 409 with {started: false,
// already_running: true} — not thrown as an error, since that's an
// expected/normal outcome the caller should handle, not a failure.
export async function startBranchBackfill(force = false) {
  const res = await fetch(`/api/branches/backfill${force ? "?force=1" : ""}`, { method: "POST" });
  if (!res.ok && res.status !== 409) throw new Error(`startBranchBackfill failed: ${res.status}`);
  return res.json();
}

// {running, completed, total} — see BackgroundTasksPanel.jsx, which polls
// this while a backfill might be in progress.
export async function fetchBranchBackfillStatus() {
  const res = await fetch("/api/branches/backfill");
  if (!res.ok) throw new Error(`fetchBranchBackfillStatus failed: ${res.status}`);
  return res.json();
}
