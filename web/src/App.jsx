import { useEffect, useRef, useState } from "react";
import DvdActivityBadge from "./components/DvdActivityBadge";
import FailedQuickAddsButton from "./components/FailedQuickAddsButton";
import MatchPanel from "./components/MatchPanel";
import QuickAddPanel from "./components/QuickAddPanel";
import RequestList from "./components/RequestList";
import SettingsPopover from "./components/SettingsPopover";
import { QuickAddProvider } from "./QuickAddContext";
import { streamRequests } from "./lib/api";
import { FILTER_OPTIONS, getDefaultFilter } from "./lib/defaultFilter";
import { useThemeMode } from "./theme/ThemeModeContext";

// "unmatched"/"matched" aren't Overseerr request statuses — Overseerr has no
// concept of our library match. They're client-side filters over whatever
// got loaded, not a value passed to /api/requests?filter=; anything not in
// this set falls back to "all" for the actual backend query.
const OVERSEERR_FILTERS = new Set(["all", "approved", "available", "processing"]);

// Already-available requests don't need a library match — there's nothing
// left to hunt down, Overseerr already has it covered. For TV, "unmatched"
// means at least one requested season still has no decision at all (neither
// matched nor confirmed unavailable). Shared between the "unmatched" filter
// and Option/Alt+click's "advance to the next unmatched" behavior below, so
// the two can't drift apart on what "unmatched" means.
function isUnmatchedRequest(r) {
  if (Number(r.media_status) === 5) return false;
  if (r.type === "tv" && r.seasons?.length > 0) {
    return r.seasons.some((s) => !r.season_matches?.[s]);
  }
  return !r.match;
}

// Mock FE — for testing matching strategies against the real Overseerr +
// library APIs before this gets rebuilt as a Jellyfin plugin. Two-pane
// workspace layout: request queue on the left, the active request's match
// panel open on the right — approved direction, see the UI-directions
// artifact this was picked from. Structure (RequestList + MatchPanel, each
// owning their own concern) is meant to be portable to the eventual plugin.
export default function App() {
  const [requests, setRequests] = useState(null);
  const [requestsSource, setRequestsSource] = useState(null);
  const [filter, setFilter] = useState(getDefaultFilter);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [quickAddResult, setQuickAddResult] = useState(null);
  const [dvdCountRefreshKey, setDvdCountRefreshKey] = useState(0);
  const [failedQuickAddsRefreshKey, setFailedQuickAddsRefreshKey] = useState(0);
  const { mode, toggle: toggleTheme } = useThemeMode();
  const loadGeneration = useRef(0);

  // The quick-add search only makes sense in the context of whatever request
  // you were matching when you spotted it — switching to a different request
  // closes it rather than leaving a stale third column open.
  function selectRequest(request) {
    setSelected(request);
    setQuickAddResult(null);
  }

  async function load(refresh = false) {
    // Rows arrive one at a time (see streamRequests) — if the filter changes
    // (or Refresh is clicked) mid-stream, this guard drops the stale
    // stream's late-arriving rows instead of mixing them into the new one.
    const generation = ++loadGeneration.current;
    setRequests(null);
    setRequestsSource(null);
    const seenIds = new Set();
    const backendFilter = OVERSEERR_FILTERS.has(filter) ? filter : "all";

    await streamRequests(backendFilter, { refresh }, ({ row, source }) => {
      if (loadGeneration.current !== generation) return;
      seenIds.add(row.id);
      setRequestsSource(source);
      // Merge this one row into whatever `requests` currently holds, rather
      // than replacing the whole array from a private closure array — a
      // closure-tracked array has no idea about matches chosen mid-stream
      // via updateLocalMatch, so replacing wholesale on every incoming row
      // used to stomp that optimistic update back to unmatched the next
      // time any other row (anywhere in the ~250) finished resolving.
      setRequests((prev) => {
        const next = prev ? prev.filter((r) => r.id !== row.id) : [];
        next.push(row);
        // Rows resolve in completion order, not Overseerr's "most recently
        // added" order — re-sort by id (descending) on every update so the
        // list settles into the right place as each one streams in, instead
        // of looking shuffled by network timing.
        next.sort((a, b) => b.id - a.id);
        return next;
      });
    });

    if (loadGeneration.current === generation && selected && !seenIds.has(selected.id)) {
      setSelected(null);
    }
  }

  useEffect(() => {
    load();
  }, [filter]);

  // Choosing/clearing a match updates just that one row in place — no
  // re-streaming the whole request list (that used to reset scroll position
  // and flash the loading state for an action that only changed one item).
  // Updates `selected` too, since MatchPanel reads request.match from that
  // snapshot, not from `requests` directly.
  // 3-arg so a single season's decision (TV) can update in place without
  // touching the other seasons — see MatchPanel.jsx's SeasonAccordion.
  // Movies (and any whole-item decision) use WHOLE_ITEM_SEASON, which also
  // keeps r.match in sync since that's still what RequestList/filters read
  // for movies.
  function updateLocalMatch(requestId, seasonNumber, match) {
    function patch(r) {
      if (r.id !== requestId) return r;
      const season_matches = { ...(r.season_matches || {}) };
      if (match === null) delete season_matches[seasonNumber];
      else season_matches[seasonNumber] = match;
      return { ...r, season_matches, match: seasonNumber === 0 ? match : r.match };
    }
    setRequests((prev) => (prev ? prev.map(patch) : prev));
    setSelected((prev) => (prev && prev.id === requestId ? patch(prev) : prev));
  }

  const displayedRequests =
    requests === null
      ? null
      : filter === "unmatched"
        ? requests.filter(isUnmatchedRequest)
        : filter === "matched"
          ? requests.filter((r) =>
              r.type === "tv" && r.seasons?.length > 0
                ? r.seasons.length > 0 && r.seasons.every((s) => r.season_matches?.[s]?.status === "matched")
                : r.match?.status === "matched",
            )
          : filter === "unavailable"
            ? requests.filter((r) =>
                r.type === "tv" && r.seasons?.length > 0
                  ? r.seasons.some((s) => r.season_matches?.[s]?.status === "unavailable")
                  : r.match?.status === "unavailable",
              )
            : requests;

  // Client-side, over whatever the status filter already produced — same
  // pattern as that filter, no backend round-trip. Matches title, requester,
  // and director (not just title) since all three are already on each row;
  // RequestList's search hint strip surfaces that scope so a match on a name
  // that isn't visibly "in" the title doesn't look like a bug.
  const searchNorm = search.trim().toLowerCase();
  const searchedRequests =
    displayedRequests === null || !searchNorm
      ? displayedRequests
      : displayedRequests.filter((r) =>
          [r.title, r.requested_by, r.tmdb?.director].some((field) => field?.toLowerCase().includes(searchNorm)),
        );

  // Option/Alt+click on "Choose" (see MatchPanel/SearchResultsTable) saves
  // the match and jumps straight to the next request still needing one —
  // "next" means the next row below the current selection in whatever order
  // the left pane is currently showing (respects the active filter/search),
  // not the full unfiltered request list. No-op if nothing after the
  // current selection still needs a match.
  function advanceToNextUnmatched() {
    if (!selected || !searchedRequests) return;
    const idx = searchedRequests.findIndex((r) => r.id === selected.id);
    if (idx === -1) return;
    const next = searchedRequests.slice(idx + 1).find(isUnmatchedRequest);
    if (next) selectRequest(next);
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <header className="flex items-center gap-3 px-6 py-3 border-b border-[var(--rule)] bg-[var(--surface)]">
        <h1 className="font-serif text-lg tracking-tight" style={{ fontFamily: "Georgia, 'Iowan Old Style', serif" }}>
          seerr-dashboard
        </h1>

        <select
          className="ml-4 text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface-raised)] px-2 py-1"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          {FILTER_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <div className="relative ml-2">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-faint)] pointer-events-none"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title, requester, or director…"
            className="w-52 rounded border border-[var(--rule-strong)] bg-[var(--surface-raised)] pl-7 pr-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
          />
        </div>

        {requestsSource && <span className="text-xs text-[var(--text-faint)]">source: {requestsSource}</span>}

        <DvdActivityBadge refreshKey={dvdCountRefreshKey} />
        <FailedQuickAddsButton refreshKey={failedQuickAddsRefreshKey} />

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => {
              load(true);
              setDvdCountRefreshKey((k) => k + 1);
            }}
            className="px-2.5 py-1.5 text-xs rounded border border-[var(--rule-strong)] hover:bg-[var(--surface-raised)]"
            title="Bypass cache and re-fetch live from Overseerr"
          >
            Refresh
          </button>
          <button
            onClick={toggleTheme}
            aria-label={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            className="w-8 h-8 flex items-center justify-center rounded hover:bg-[var(--surface-raised)] text-base"
          >
            {mode === "dark" ? "☾" : "☀"}
          </button>
          <div className="relative">
            <button
              onClick={() => setSettingsOpen((o) => !o)}
              aria-label="Settings"
              aria-expanded={settingsOpen}
              title="Settings"
              className="w-8 h-8 flex items-center justify-center rounded hover:bg-[var(--surface-raised)] text-base"
            >
              ⚙
            </button>
            {settingsOpen && <SettingsPopover onClose={() => setSettingsOpen(false)} />}
          </div>
        </div>
      </header>

      <QuickAddProvider value={setQuickAddResult}>
        <div
          className={`grid grid-cols-1 gap-px bg-[var(--rule)] border-b border-[var(--rule)] ${
            quickAddResult ? "lg:grid-cols-[1.1fr_1fr_1fr]" : "lg:grid-cols-[1.1fr_1fr]"
          }`}
        >
          <div className="bg-[var(--surface)]">
            <RequestList
              requests={searchedRequests}
              selectedId={selected?.id}
              onSelect={selectRequest}
              searchQuery={search}
              onClearSearch={() => setSearch("")}
            />
          </div>
          <div className="bg-[var(--surface)] p-5 lg:sticky lg:top-0 lg:self-start lg:max-h-screen lg:overflow-y-auto">
            {selected ? (
              <MatchPanel request={selected} onMatchChange={updateLocalMatch} onAdvance={advanceToNextUnmatched} />
            ) : (
              <p className="text-sm text-[var(--text-faint)]">Select a request to search the library.</p>
            )}
          </div>
          {quickAddResult && (
            <div className="bg-[var(--surface)] p-5 lg:sticky lg:top-0 lg:self-start lg:max-h-screen lg:overflow-y-auto">
              <QuickAddPanel
                libraryResult={quickAddResult}
                onClose={() => setQuickAddResult(null)}
                onAddFailed={() => setFailedQuickAddsRefreshKey((k) => k + 1)}
              />
            </div>
          )}
        </div>
      </QuickAddProvider>
    </div>
  );
}
