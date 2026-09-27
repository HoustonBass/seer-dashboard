import { useState } from "react";
import { isUnmatchedRequest } from "../lib/requestFilters";

// The selected request plus "find the next one still needing a match"
// lookup. `findNextUnmatched` takes `searchedRequests` as an argument
// (rather than this hook holding a reference to it) specifically to avoid a
// call-order dependency between this hook and useRequests in App.jsx —
// useRequests needs `selected` to decide whether to clear it after a
// stream, but `searchedRequests` is derived from useRequests' own output,
// so it can't be known until after both hooks have run.
export default function useRequestSelection() {
  const [selected, setSelected] = useState(null);

  // "Next" means the next row below the current selection in whatever order
  // the left pane is currently showing (respects the active filter/search),
  // not the full unfiltered request list. Shared by App.jsx's
  // advanceToNextUnmatched and usePrefetchNextSearch.
  function findNextUnmatched(searchedRequests) {
    if (!selected || !searchedRequests) return null;
    const idx = searchedRequests.findIndex((r) => r.id === selected.id);
    if (idx === -1) return null;
    return searchedRequests.slice(idx + 1).find(isUnmatchedRequest) ?? null;
  }

  return { selected, setSelected, findNextUnmatched };
}
