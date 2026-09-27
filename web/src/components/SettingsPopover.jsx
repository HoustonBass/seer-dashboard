import { useEffect, useRef, useState } from "react";
import { fetchSettings, setSetting, startBranchBackfill } from "../lib/api";
import { getDefaultBranch, setDefaultBranch } from "../lib/defaultBranch";
import Toggle from "./Toggle";

// Feature-switch panel: lists everything in app/lib/feature_switch.py's
// REGISTRY and lets you flip it live (mutates the backend process's env vars
// directly, no restart needed) — see app/controllers/settings_controller.py.
// A new switch just needs a REGISTRY entry to show up here automatically.
//
// Also holds the "default branch" preference — purely client-side
// (localStorage, see lib/defaultBranch.js), not a backend feature switch,
// but this popover is where UI preferences live so it's grouped here rather
// than adding a second settings surface. The default *filter* preference
// (lib/defaultFilter.js) isn't set here — the header's filter dropdown
// itself persists whatever you pick directly (see App.jsx's
// handleFilterChange), so there's nothing left for this popover to do.
export default function SettingsPopover({ onClose, onRefresh }) {
  const [switches, setSwitches] = useState(null);
  const [error, setError] = useState("");
  const [defaultBranch, setDefaultBranchState] = useState(getDefaultBranch);
  const [backfillMessage, setBackfillMessage] = useState("");
  const [expandedSwitches, setExpandedSwitches] = useState(() => new Set());
  const ref = useRef(null);

  function toggleExpanded(key) {
    setExpandedSwitches((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  useEffect(() => {
    fetchSettings()
      .then((body) => setSwitches(body.switches))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    function onPointerDown(e) {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    }
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  // Alt/Option+click hard-refreshes every matched movie's cached branches
  // (not just the ones missing entirely) — see BackfillService.start_backfill's
  // `force` param. Progress shows as a chip in the header (BackgroundTasksPanel),
  // not here — this popover closes long before a ~1/sec, multi-minute run
  // finishes, so it can't own that state itself.
  async function handleBackfillClick(e) {
    const force = e.altKey;
    setBackfillMessage("");
    try {
      const result = await startBranchBackfill({ force });
      if (result.already_running) {
        setBackfillMessage("Already running — check the header's progress chip.");
      } else {
        setBackfillMessage(force ? "Hard refresh started." : "Backfill started (missing entries only).");
      }
    } catch (err) {
      setBackfillMessage(`Failed to start — ${err.message}`);
    }
  }

  // Once everything's already cached, a real (non-force) backfill finds
  // nothing to fetch and finishes in milliseconds — faster than the header
  // chip's first poll can ever catch it running. This runs a fake ~10s
  // progression instead, purely to exercise/demo that same chip on demand.
  // Never deduped against itself (unlike the real backfill) — every click
  // (Option/Alt or not, doesn't matter, both just click the button) starts
  // another concurrent test task, so clicking it a couple of times is how
  // you demo BackgroundTasksPanel tracking more than one task at once.
  async function handleTestProgressClick() {
    setBackfillMessage("");
    try {
      await startBranchBackfill({ test: true });
      setBackfillMessage("Test run started — click again for another one alongside it.");
    } catch (err) {
      setBackfillMessage(`Failed to start — ${err.message}`);
    }
  }

  async function handleToggle(key, enabled) {
    const previous = switches;
    setSwitches((prev) => prev.map((s) => (s.key === key ? { ...s, enabled } : s))); // optimistic
    setError("");
    try {
      const body = await setSetting(key, enabled);
      setSwitches(body.switches);
    } catch (e) {
      setSwitches(previous);
      setError(e.message);
    }
  }

  return (
    <div
      ref={ref}
      role="menu"
      className="absolute right-0 top-[calc(100%+8px)] z-20 w-80 max-w-[calc(100vw-2rem)] rounded-md border border-[var(--rule)] bg-[var(--surface-raised)] p-4 shadow-lg flex flex-col gap-3"
    >
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-1.5">
          Default branch
        </div>
        <input
          type="text"
          value={defaultBranch}
          onChange={(e) => {
            setDefaultBranchState(e.target.value);
            setDefaultBranch(e.target.value);
          }}
          placeholder="e.g. Milton or MILTON"
          className="w-full text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface)] px-2 py-1.5"
        />
        <p className="text-[11px] leading-snug text-[var(--text-faint)] mt-1">
          Branch name or code (hover a "Which branches?" pill to see a result's code). Highlights that
          branch's pill when it has a copy.
        </p>
      </div>

      <div className="border-t border-[var(--rule)] pt-3">
        <div className="flex gap-1.5">
          <button
            onClick={handleBackfillClick}
            className="flex-1 text-sm rounded border border-[var(--rule-strong)] px-2 py-1.5 hover:bg-[var(--surface)]"
            title="Fills in branch availability for matched movies missing it. Option/Alt+click to hard-refresh every matched movie's branches instead, not just the missing ones."
          >
            Refresh branch cache
          </button>
          <button
            onClick={handleTestProgressClick}
            className="shrink-0 text-sm rounded border border-[var(--rule-strong)] px-2 py-1.5 text-[var(--text-muted)] hover:bg-[var(--surface)]"
            title="Runs a fake ~10s progression to exercise the header's progress chip on demand — real runs usually finish too fast to see once everything's cached. Click more than once to run several concurrently."
          >
            Test progress bar
          </button>
        </div>
        {backfillMessage && <p className="text-[11px] leading-snug text-[var(--text-faint)] mt-1">{backfillMessage}</p>}
      </div>

      <div className="border-t border-[var(--rule)] pt-3">
        <button
          onClick={() => {
            onRefresh?.();
            onClose();
          }}
          className="w-full text-sm rounded border border-[var(--rule-strong)] px-2 py-1.5 hover:bg-[var(--surface)]"
          title="Bypass cache and re-fetch live from Overseerr"
        >
          Refresh data
        </button>
      </div>

      <div className="border-t border-[var(--rule)] pt-3 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Feature switches
      </div>

      {switches === null && !error && <p className="text-sm text-[var(--text-faint)]">Loading…</p>}
      {error && <p className="text-xs text-[var(--accent)]">{error}</p>}

      {switches?.map((s) => {
        const expanded = expandedSwitches.has(s.key);
        return (
          <div key={s.key} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-3">
              <button
                onClick={() => toggleExpanded(s.key)}
                className="flex items-center gap-1 text-sm hover:text-[var(--text)] text-left min-w-0"
                aria-expanded={expanded}
                title={expanded ? "Hide description" : "Show description"}
              >
                <span
                  className={`mono text-[var(--text-faint)] text-[10px] transition-transform shrink-0 ${expanded ? "rotate-90" : ""}`}
                >
                  ▸
                </span>
                <span className="truncate">{s.label}</span>
              </button>
              <Toggle checked={s.enabled} onChange={(next) => handleToggle(s.key, next)} title={s.description} />
            </div>
            {expanded && (
              <p className="text-[11px] leading-snug text-[var(--text-faint)] pl-4">
                {s.description}
                {s.enabled ? ` (${s.seconds}s)` : ""}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
