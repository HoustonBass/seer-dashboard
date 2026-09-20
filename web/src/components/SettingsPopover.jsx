import { useEffect, useRef, useState } from "react";
import { fetchSettings, setSetting } from "../lib/api";
import { FILTER_OPTIONS, getDefaultFilter, setDefaultFilter } from "../lib/defaultFilter";
import Toggle from "./Toggle";

// Feature-switch panel: lists everything in app/lib/feature_switch.py's
// REGISTRY and lets you flip it live (mutates the backend process's env vars
// directly, no restart needed) — see app/controllers/settings_controller.py.
// A new switch just needs a REGISTRY entry to show up here automatically.
//
// Also holds the "default filter" preference — purely client-side
// (localStorage, see lib/defaultFilter.js), not a backend feature switch,
// but this popover is where UI preferences live so it's grouped here rather
// than adding a second settings surface.
export default function SettingsPopover({ onClose }) {
  const [switches, setSwitches] = useState(null);
  const [error, setError] = useState("");
  const [defaultFilter, setDefaultFilterState] = useState(getDefaultFilter);
  const ref = useRef(null);

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
      className="absolute right-0 top-[calc(100%+8px)] z-20 w-80 rounded-md border border-[var(--rule)] bg-[var(--surface-raised)] p-4 shadow-lg flex flex-col gap-3"
    >
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)] mb-1.5">
          Default filter
        </div>
        <select
          className="w-full text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface)] px-2 py-1.5"
          value={defaultFilter}
          onChange={(e) => {
            setDefaultFilterState(e.target.value);
            setDefaultFilter(e.target.value);
          }}
        >
          {FILTER_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <p className="text-[11px] leading-snug text-[var(--text-faint)] mt-1">
          Which filter is selected when the page loads. Doesn't change what's showing right now.
        </p>
      </div>

      <div className="border-t border-[var(--rule)] pt-3 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Feature switches
      </div>

      {switches === null && !error && <p className="text-sm text-[var(--text-faint)]">Loading…</p>}
      {error && <p className="text-xs text-[var(--accent)]">{error}</p>}

      {switches?.map((s) => (
        <div key={s.key} className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm">{s.label}</span>
            <Toggle checked={s.enabled} onChange={(next) => handleToggle(s.key, next)} title={s.description} />
          </div>
          <p className="text-[11px] leading-snug text-[var(--text-faint)]">
            {s.description}
            {s.enabled ? ` (${s.seconds}s)` : ""}
          </p>
        </div>
      ))}
    </div>
  );
}
