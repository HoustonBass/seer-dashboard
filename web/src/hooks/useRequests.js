import { useEffect, useRef, useState } from "react";
import { streamRequests } from "../lib/api";
import { OVERSEERR_FILTERS } from "../lib/requestFilters";

// Streams /api/requests for the given Overseerr-level filter, merging rows
// in as they resolve (see streamRequests) rather than waiting for the whole
// batch. Re-fetches automatically whenever `filter` changes; `load(true)`
// is exposed for a manual bypass-cache refresh (see App.jsx's Refresh
// button). Also exposes `setRequests` directly — optimistic match updates
// (see App.jsx's updateLocalMatch) patch this state in place rather than
// re-streaming the whole list for a single-row change.
//
// `onStreamSettled(seenIds)` fires once a stream completes without being
// superseded — App.jsx uses it to drop the current selection if that
// request didn't come back under the new filter (moved by onStreamSettled
// rather than owned here since "selected" is a different hook's state).
export default function useRequests(filter, { onStreamSettled } = {}) {
  const [requests, setRequests] = useState(null);
  const [requestsSource, setRequestsSource] = useState(null);
  const loadGeneration = useRef(0);
  const loadAbortController = useRef(null);

  async function load(refresh = false) {
    // Abort whatever load is still in flight before starting a new one —
    // otherwise a still-running /api/requests stream (each one re-resolves
    // title/TMDB for every request, ~250 of them) keeps costing real backend
    // work even after its result is discarded client-side. This also means
    // React 18 StrictMode's dev-only double-invoke of this effect (mount,
    // cleanup, remount — see main.jsx) cancels the first mount's request via
    // the effect's cleanup below instead of both actually hitting the
    // backend, which is what made filter=all appear to fire twice on load.
    loadAbortController.current?.abort();
    const controller = new AbortController();
    loadAbortController.current = controller;

    // Rows arrive one at a time (see streamRequests) — if the filter changes
    // (or Refresh is clicked) mid-stream, this guard drops the stale
    // stream's late-arriving rows instead of mixing them into the new one.
    // Kept alongside the abort above as a belt-and-suspenders guard for any
    // row already buffered client-side by the time an abort lands.
    const generation = ++loadGeneration.current;
    setRequests(null);
    setRequestsSource(null);
    const seenIds = new Set();
    const backendFilter = OVERSEERR_FILTERS.has(filter) ? filter : "all";

    try {
      await streamRequests(backendFilter, { refresh, signal: controller.signal }, ({ row, source }) => {
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
          // Rows resolve in completion order, not Overseerr's own request
          // order — re-sort by id (ascending — oldest requested first;
          // Overseerr ids are auto-increment, so id order tracks request
          // date) on every update so the list settles into the right place
          // as each one streams in, instead of looking shuffled by network
          // timing.
          next.sort((a, b) => a.id - b.id);
          return next;
        });
      });
    } catch (e) {
      if (e.name === "AbortError") return; // superseded by a newer load — not a real failure
      throw e;
    }

    if (loadGeneration.current === generation) onStreamSettled?.(seenIds);
  }

  useEffect(() => {
    load();
    return () => loadAbortController.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  return { requests, setRequests, requestsSource, load };
}
