import { useEffect, useRef, useState } from "react";
import { dismissFailedQuickAdd, listFailedQuickAdds, retryFailedQuickAdd } from "../lib/api";

// Header button + popover for quick-add attempts that couldn't reach
// Overseerr (see app/repos/failed_quick_add_repo.py) — lets a failed attempt
// be retried once the connection's back instead of being lost. Same
// button-toggles-absolute-popover pattern as SettingsPopover/the gear icon.
// `refreshKey` bumps on every failed add (see QuickAddPanel's onAddFailed)
// so the badge count updates immediately, not just on next open.
export default function FailedQuickAddsButton({ refreshKey }) {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const ref = useRef(null);

  function refresh() {
    listFailedQuickAdds()
      .then((body) => setFailed(body.failed))
      .catch((e) => setError(e.message));
  }

  useEffect(refresh, [refreshKey]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function handleRetry(id) {
    setBusyId(id);
    setError("");
    try {
      await retryFailedQuickAdd(id);
      setFailed((prev) => prev.filter((f) => f.id !== id));
    } catch (e) {
      setError(e.message);
      refresh(); // attempts/error on the row may have changed even though it's still failed
    } finally {
      setBusyId(null);
    }
  }

  async function handleDismiss(id) {
    setBusyId(id);
    setError("");
    try {
      await dismissFailedQuickAdd(id);
      setFailed((prev) => prev.filter((f) => f.id !== id));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  if (failed.length === 0 && !open) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Failed quick-adds"
        aria-expanded={open}
        title="Quick-adds that couldn't reach Overseerr"
        className="relative w-8 h-8 flex items-center justify-center rounded hover:bg-[var(--surface-raised)] text-base"
      >
        ⚠
        {failed.length > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full text-[10px] font-semibold bg-[var(--accent)] text-[var(--accent-contrast)]">
            {failed.length}
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+8px)] z-20 w-96 max-w-[calc(100vw-2rem)] rounded-md border border-[var(--rule)] bg-[var(--surface-raised)] p-4 shadow-lg flex flex-col gap-3"
        >
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            Failed quick-adds
          </div>
          <p className="text-[11px] leading-snug text-[var(--text-faint)]">
            Overseerr couldn't be reached when these were added — retry once it's back, or dismiss to give up on it.
          </p>

          {error && <p className="text-xs text-[var(--accent)]">{error}</p>}

          {failed.length === 0 ? (
            <p className="text-sm text-[var(--text-faint)]">Nothing waiting to retry.</p>
          ) : (
            <div className="flex flex-col gap-2 max-h-80 overflow-y-auto">
              {failed.map((f) => (
                <div
                  key={f.id}
                  className="flex items-start justify-between gap-2 border-b border-dashed border-[var(--rule)] last:border-none pb-2 last:pb-0"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-semibold truncate">{f.payload.title || `tmdb ${f.payload.tmdb_id}`}</div>
                    <div className="text-[11px] text-[var(--text-faint)] truncate" title={f.error}>
                      {f.error}
                    </div>
                    {f.attempts > 1 && (
                      <div className="text-[11px] text-[var(--text-faint)]">{f.attempts} attempts</div>
                    )}
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => handleRetry(f.id)}
                      disabled={busyId === f.id}
                      className="text-xs font-semibold px-2.5 py-1 rounded border border-[var(--primary)] text-[var(--primary)] hover:bg-[var(--primary)] hover:text-[var(--primary-contrast)] disabled:opacity-50"
                    >
                      {busyId === f.id ? "…" : "Retry"}
                    </button>
                    <button
                      onClick={() => handleDismiss(f.id)}
                      disabled={busyId === f.id}
                      className="text-xs px-2.5 py-1 rounded border border-[var(--rule-strong)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
