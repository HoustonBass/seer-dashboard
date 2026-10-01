import { useEffect, useState } from "react";
import { searchMovies } from "../lib/api";

const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;

// Debounced, abortable Overseerr movie search. `results` is null until a
// query long enough to search has resolved; a newer query aborts the older
// one so a slow earlier response can't overwrite a faster later one.
export default function useMovieSearch(query) {
  const [state, setState] = useState({ query: "", results: null, error: "" });
  const trimmed = query.trim();
  const searchable = trimmed.length >= MIN_QUERY_LENGTH;

  useEffect(() => {
    if (!searchable) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchMovies(trimmed, { signal: controller.signal })
        .then((results) => setState({ query: trimmed, results, error: "" }))
        .catch((e) => {
          if (e.name !== "AbortError") setState({ query: trimmed, results: null, error: e.message });
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [trimmed, searchable]);

  // Derived, not stored: results only count while they belong to the
  // current query, which also covers clearing the box.
  const current = searchable && state.query === trimmed;
  return {
    results: current ? state.results : null,
    error: current ? state.error : "",
    loading: searchable && !current,
    searchable,
  };
}
