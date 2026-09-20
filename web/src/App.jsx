import { useEffect, useState } from "react";
import MatchPanel from "./components/MatchPanel";
import RequestList from "./components/RequestList";
import SettingsPopover from "./components/SettingsPopover";
import { fetchRequests } from "./lib/api";
import { useThemeMode } from "./theme/ThemeModeContext";

// Mock FE — for testing matching strategies against the real Overseerr +
// library APIs before this gets rebuilt as a Jellyfin plugin. Two-pane
// workspace layout: request queue on the left, the active request's match
// panel open on the right — approved direction, see the UI-directions
// artifact this was picked from. Structure (RequestList + MatchPanel, each
// owning their own concern) is meant to be portable to the eventual plugin.
export default function App() {
  const [requests, setRequests] = useState(null);
  const [requestsSource, setRequestsSource] = useState(null);
  const [filter, setFilter] = useState("approved");
  const [selected, setSelected] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { mode, toggle: toggleTheme } = useThemeMode();

  async function load(refresh = false) {
    const { source, results } = await fetchRequests(filter, { refresh });
    setRequests(results);
    setRequestsSource(source);
    if (selected) {
      setSelected(results.find((r) => r.id === selected.id) ?? null);
    }
  }

  useEffect(() => {
    setRequests(null);
    load();
  }, [filter]);

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
          <option value="all">all</option>
          <option value="approved">approved</option>
          <option value="pending">pending</option>
          <option value="available">available</option>
          <option value="processing">processing</option>
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
          <RequestList requests={requests} selectedId={selected?.id} onSelect={setSelected} />
        </div>
        <div className="bg-[var(--surface)] p-5">
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
