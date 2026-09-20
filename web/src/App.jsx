import { useEffect, useRef, useState } from "react";
import MatchPanel from "./components/MatchPanel";
import RequestList from "./components/RequestList";
import SettingsPopover from "./components/SettingsPopover";
import { streamRequests } from "./lib/api";
import { FILTER_OPTIONS, getDefaultFilter } from "./lib/defaultFilter";
import { useThemeMode } from "./theme/ThemeModeContext";

// "unmatched"/"matched" aren't Overseerr request statuses — Overseerr has no
// concept of our library match. They're client-side filters over whatever
// got loaded, not a value passed to /api/requests?filter=; anything not in
// this set falls back to "all" for the actual backend query.
const OVERSEERR_FILTERS = new Set(["all", "approved", "available", "processing"]);

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
  const [selected, setSelected] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { mode, toggle: toggleTheme } = useThemeMode();
  const loadGeneration = useRef(0);

  async function load(refresh = false) {
    // Rows arrive one at a time (see streamRequests) — if the filter changes
    // (or Refresh is clicked) mid-stream, this guard drops the stale
    // stream's late-arriving rows instead of mixing them into the new one.
    const generation = ++loadGeneration.current;
    setRequests(null);
    setRequestsSource(null);
    const rows = [];
    const backendFilter = OVERSEERR_FILTERS.has(filter) ? filter : "all";

    await streamRequests(backendFilter, { refresh }, ({ row, source }) => {
      if (loadGeneration.current !== generation) return;
      rows.push(row);
      // Rows resolve in completion order, not Overseerr's "most recently
      // added" order — re-sort by id (descending) on every update so the
      // list settles into the right place as each one streams in, instead
      // of looking shuffled by network timing.
      rows.sort((a, b) => b.id - a.id);
      setRequestsSource(source);
      setRequests([...rows]);
    });

    if (loadGeneration.current === generation && selected) {
      setSelected(rows.find((r) => r.id === selected.id) ?? null);
    }
  }

  useEffect(() => {
    load();
  }, [filter]);

  const displayedRequests =
    requests === null
      ? null
      : filter === "unmatched"
        // Already-available requests don't need a library match — there's
        // nothing left to hunt down, Overseerr already has it covered.
        ? requests.filter((r) => !r.match && Number(r.media_status) !== 5)
        : filter === "matched"
          ? requests.filter((r) => r.match)
          : requests;

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

        {requestsSource && <span className="text-xs text-[var(--text-faint)]">source: {requestsSource}</span>}

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => load(true)}
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

      <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-px bg-[var(--rule)] border-b border-[var(--rule)]">
        <div className="bg-[var(--surface)]">
          <RequestList requests={displayedRequests} selectedId={selected?.id} onSelect={setSelected} />
        </div>
        <div className="bg-[var(--surface)] p-5 lg:sticky lg:top-0 lg:self-start lg:max-h-screen lg:overflow-y-auto">
          {selected ? (
            <MatchPanel request={selected} onMatchSaved={load} />
          ) : (
            <p className="text-sm text-[var(--text-faint)]">Select a request to search the library.</p>
          )}
        </div>
      </div>
    </div>
  );
}
