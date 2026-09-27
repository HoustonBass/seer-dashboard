import BackgroundTasksPanel from "../BackgroundTasksPanel";
import DvdActivityBadge from "../DvdActivityBadge";
import FailedQuickAddsButton from "../FailedQuickAddsButton";
import SettingsPopover from "../SettingsPopover";
import { FILTER_OPTIONS } from "../../lib/defaultFilter";

// Mobile gets a deliberate 3-line layout — identity+icons, then search, then
// a secondary toolbar — via explicit `order` per element rather than just
// letting flex-wrap dump things wherever they land (that read as cramped/
// accidental). `sm:order-N` restores the exact original left-to-right
// sequence at desktop, so nothing there changes.
//
// Presentational only — App.jsx (the composition root) owns all the state/
// hooks this just renders, same contract as app/controllers/*.py: parse
// input (props), call exactly what's handed in, no business logic here.
export default function AppHeader({
  filter,
  onFilterChange,
  requestCount,
  search,
  onSearchChange,
  requestsSource,
  dvdCountRefreshKey,
  failedQuickAddsRefreshKey,
  onRefresh,
  mode,
  onToggleTheme,
  settingsOpen,
  onToggleSettings,
  onCloseSettings,
}) {
  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 sm:px-6 py-3 border-b border-[var(--rule)] bg-[var(--surface)]">
      <div className="order-1 flex items-center gap-1.5 min-w-0">
        <h1
          className="font-serif text-lg tracking-tight shrink-0"
          style={{ fontFamily: "Georgia, 'Iowan Old Style', serif" }}
        >
          seerr-dashboard
        </h1>

        <div className="flex items-center gap-1.5 sm:ml-4">
          <span
            className="mono w-6 h-6 shrink-0 rounded-full flex items-center justify-center text-xs font-bold text-[var(--text-muted)] bg-[var(--unmatched-bg)]"
            title={`${requestCount ?? 0} requests match this filter`}
          >
            {requestCount ?? "–"}
          </span>
          <select
            className="text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface-raised)] px-2 py-1"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
          >
            {FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Row 1's right side on mobile (icons only — Refresh moves to the
          secondary toolbar row so row 1 stays compact); at sm+ this sits in
          its original spot via sm:order-8/9 + sm:ml-auto on Refresh below. */}
      <button
        onClick={onToggleTheme}
        aria-label={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        className="order-2 sm:order-8 w-8 h-8 flex items-center justify-center rounded hover:bg-[var(--surface-raised)] text-base"
      >
        {mode === "dark" ? "☾" : "☀"}
      </button>
      <div className="relative order-3 sm:order-9">
        <button
          onClick={onToggleSettings}
          aria-label="Settings"
          aria-expanded={settingsOpen}
          title="Settings"
          className="w-8 h-8 flex items-center justify-center rounded hover:bg-[var(--surface-raised)] text-base"
        >
          ⚙
        </button>
        {settingsOpen && <SettingsPopover onClose={onCloseSettings} onRefresh={onRefresh} />}
      </div>

      {/* Row 2 on mobile — full width, its own line. */}
      <div className="relative order-4 sm:order-2 w-full sm:w-52 sm:ml-2">
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
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search title, requester, or director…"
          className="w-full rounded border border-[var(--rule-strong)] bg-[var(--surface-raised)] pl-7 pr-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        />
      </div>

      {/* Row 3 on mobile — secondary toolbar: status text, badges, and
          Refresh, wrapping together as one cohesive group. */}
      {requestsSource && (
        <span className="order-5 sm:order-3 text-xs text-[var(--text-faint)]">source: {requestsSource}</span>
      )}

      <div className="order-6 sm:order-4">
        <DvdActivityBadge refreshKey={dvdCountRefreshKey} />
      </div>
      <div className="order-7 sm:order-5">
        <FailedQuickAddsButton refreshKey={failedQuickAddsRefreshKey} />
      </div>

      {/* Invisible unless a background task (currently just the branch
          backfill) is actually running or just finished — see
          BackgroundTasksPanel.jsx. */}
      <div className="order-8 sm:order-6">
        <BackgroundTasksPanel />
      </div>

      <button
        onClick={onRefresh}
        className="order-9 sm:order-7 sm:ml-auto px-2.5 py-1.5 text-xs rounded border border-[var(--rule-strong)] hover:bg-[var(--surface-raised)]"
        title="Bypass cache and re-fetch live from Overseerr"
      >
        Refresh
      </button>
    </header>
  );
}
