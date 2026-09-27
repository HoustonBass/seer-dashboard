import { useEffect, useRef, useState } from "react";
import { fetchBranchBackfillStatus } from "../lib/api";

const POLL_INTERVAL_MS = 1000;
const HIDE_AFTER_DONE_MS = 4000;

// Small fixed floating panel showing in-progress background tasks with a
// progress bar — currently just the branch-availability backfill (see
// SettingsPopover's "Refresh branch cache" button / app/services/
// backfill_service.py), but shaped as a status poll + visibility toggle so
// a second background task later is another entry, not a new panel.
//
// Only ever becomes visible after actually observing `running: true` this
// session (or currently running) — the backend's completed/total persist
// indefinitely after a run finishes, so without this guard, reloading the
// page hours after a completed backfill would incorrectly resurrect a
// stale "207/207 done" panel from a previous session.
export default function BackgroundTasksPanel() {
  const [status, setStatus] = useState(null);
  const [visible, setVisible] = useState(false);
  const hideTimerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    function poll() {
      fetchBranchBackfillStatus()
        .then((s) => {
          if (cancelled) return;
          setStatus(s);
          setVisible((wasVisible) => {
            if (s.running) {
              if (hideTimerRef.current) {
                clearTimeout(hideTimerRef.current);
                hideTimerRef.current = null;
              }
              return true;
            }
            if (wasVisible && !hideTimerRef.current) {
              hideTimerRef.current = setTimeout(() => {
                setVisible(false);
                hideTimerRef.current = null;
              }, HIDE_AFTER_DONE_MS);
            }
            return wasVisible;
          });
        })
        .catch(() => {}); // best-effort — a failed poll just tries again next tick
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, []);

  if (!visible || !status) return null;

  const pct = status.total > 0 ? Math.round((status.completed / status.total) * 100) : 0;

  return (
    <div className="fixed bottom-4 right-4 z-30 w-72 max-w-[calc(100vw-2rem)] rounded-md border border-[var(--rule)] bg-[var(--surface-raised)] p-3 shadow-lg">
      <div className="flex items-center justify-between gap-2 text-xs font-semibold text-[var(--text-muted)]">
        <span>{status.running ? "Refreshing branch cache…" : "Branch cache refresh complete"}</span>
        <span className="mono">
          {status.completed}/{status.total}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 rounded-full bg-[var(--rule-strong)] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${status.running ? "bg-[var(--primary)]" : "bg-[var(--available)]"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
