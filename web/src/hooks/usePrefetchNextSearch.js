import { useEffect, useRef } from "react";
import { DEFAULT_FORMAT } from "../components/MatchSearchBox";
import { searchLibrary } from "../lib/api";
import { defaultSearchQueryFor } from "../lib/requestFilters";

// Selecting a request already triggers its own auto-search (MatchSearchBox's
// autoSearchKey effect) — this warms the *next* unmatched request's search a
// beat later, so LibraryRepo's cache is already populated by the time you
// actually get there (Option/Alt+click or a manual click). Delayed instead
// of immediate so it doesn't compete with the just-selected request's own
// (higher-priority) search for the same backend.
export default function usePrefetchNextSearch(selected, searchedRequests, findNextUnmatched) {
  // Keyed by (selected, next, query) via a ref rather than firing straight
  // from a dependency array — searchedRequests is a fresh array reference on
  // every render, so without the ref this would refire (though harmlessly,
  // since a cache hit is cheap) on any unrelated re-render, not just an
  // actual change.
  const prefetchedForRef = useRef(null);

  useEffect(() => {
    const next = findNextUnmatched(searchedRequests);
    if (!next) return;
    const query = defaultSearchQueryFor(next);
    if (!query) return;
    const key = `${selected?.id}:${next.id}:${query}`;
    if (prefetchedForRef.current === key) return;
    const timer = setTimeout(() => {
      prefetchedForRef.current = key;
      searchLibrary(query, DEFAULT_FORMAT).catch(() => {});
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, searchedRequests]);
}
