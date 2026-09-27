import { useEffect, useRef, useState } from "react";
import { fetchBranchBackfillStatus } from "../lib/api";

const POLL_INTERVAL_MS = 1000;
const HIDE_AFTER_DONE_MS = 4000;

// One queue-ordered widget (rendered in AppHeader's secondary toolbar row)
// for in-progress background tasks — currently the branch-availability
// backfill and/or any number of concurrent simulated "Test progress bar"
// runs (see SettingsPopover.jsx / app/services/backfill_service.py).
// Always shows just the oldest/first-started task's progress bar in the
// header itself (FIFO — whichever's been running longest stays in that one
// slot until it finishes, then the next in line takes its place); a
// chevron only appears once there's more than one, opening a dropdown
// (same click-outside/Escape-to-close pattern as SettingsPopover) listing
// every task. Renders nothing (not even an empty gap) unless at least one
// task is actually running or just finished.
//
// A task only ever becomes visible after actually observing it `running`
// this session (or currently running) — the backend keeps completed/total
// around indefinitely after a task finishes, so without this guard,
// reloading the page long after everything's done would incorrectly
// resurrect stale "20/20 done" chips from a previous session. Object key
// insertion order (preserved by JS for non-numeric string keys, which
// every task id here is) is what keeps the queue FIFO — the backend's own
// `status()` already returns tasks in creation order, and each task's
// first appearance is the only time its key gets added to `visibleTasks`.
export default function BackgroundTasksPanel() {
  const [visibleTasks, setVisibleTasks] = useState({}); // id -> task, insertion order = queue order
  const [expanded, setExpanded] = useState(false);
  const hideTimersRef = useRef({}); // id -> timeout handle
  const ref = useRef(null);

  useEffect(() => {
    let cancelled = false;

    function poll() {
      fetchBranchBackfillStatus()
        .then(({ tasks }) => {
          if (cancelled) return;
          setVisibleTasks((prev) => {
            const next = { ...prev };
            for (const task of tasks) {
              if (task.running) {
                if (hideTimersRef.current[task.id]) {
                  clearTimeout(hideTimersRef.current[task.id]);
                  delete hideTimersRef.current[task.id];
                }
                next[task.id] = task;
              } else if (prev[task.id]) {
                // Was visible, just finished — keep showing "done" for a
                // beat before the timer below drops it.
                next[task.id] = task;
                if (!hideTimersRef.current[task.id]) {
                  const id = task.id;
                  hideTimersRef.current[id] = setTimeout(() => {
                    setVisibleTasks((p) => {
                      const n = { ...p };
                      delete n[id];
                      return n;
                    });
                    delete hideTimersRef.current[id];
                  }, HIDE_AFTER_DONE_MS);
                }
              }
              // else: never observed running and not previously visible —
              // stale historical data, ignore.
            }
            return next;
          });
        })
        .catch(() => {}); // best-effort — a failed poll just tries again next tick
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
      Object.values(hideTimersRef.current).forEach(clearTimeout);
    };
  }, []);

  useEffect(() => {
    if (!expanded) return;
    function onPointerDown(e) {
      if (ref.current && !ref.current.contains(e.target)) setExpanded(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setExpanded(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [expanded]);

  const tasks = Object.values(visibleTasks);
  if (tasks.length === 0) return null;

  const [first, ...rest] = tasks;

  return (
    <div className="relative" ref={ref}>
      <div className="inline-flex items-center gap-1">
        <TaskChip task={first} />
        {rest.length > 0 && (
          <button
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            aria-label={`${rest.length} more background task${rest.length === 1 ? "" : "s"}`}
            title={`${rest.length} more background task${rest.length === 1 ? "" : "s"}`}
            className="w-5 h-5 flex items-center justify-center rounded-full bg-[var(--unmatched-bg)] text-[var(--text-muted)] hover:text-[var(--text)]"
          >
            <span className={`mono text-[10px] transition-transform ${expanded ? "rotate-90" : ""}`}>▸</span>
          </button>
        )}
      </div>

      {expanded && rest.length > 0 && (
        <div
          role="menu"
          className="absolute left-0 top-[calc(100%+8px)] z-20 w-64 max-w-[calc(100vw-2rem)] rounded-md border border-[var(--rule)] bg-[var(--surface-raised)] p-2 shadow-lg flex flex-col gap-1.5"
        >
          {rest.map((task) => (
            <TaskChip key={task.id} task={task} className="w-full" />
          ))}
        </div>
      )}
    </div>
  );
}

function TaskChip({ task, className = "" }) {
  const pct = task.total > 0 ? Math.round((task.completed / task.total) * 100) : 0;
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-[var(--unmatched-bg)] text-[var(--text-muted)] whitespace-nowrap ${className}`}
      title={`${task.label}${task.running ? "…" : " — complete"}`}
    >
      <span className="w-12 h-1.5 rounded-full bg-[var(--rule-strong)] overflow-hidden shrink-0">
        <span
          className={`block h-full rounded-full transition-all ${task.running ? "bg-[var(--primary)]" : "bg-[var(--available)]"}`}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="truncate max-w-[9rem]">{task.label}</span>
      <span className="mono">
        {task.completed}/{task.total}
      </span>
    </span>
  );
}
