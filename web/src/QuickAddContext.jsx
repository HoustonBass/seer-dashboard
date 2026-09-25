import { createContext, useContext } from "react";

// Lets SearchResultsTable (nested inside MatchPanel/MatchSearchBox, several
// layers below App.jsx) open the quick-add third column without prop-drilling
// a callback down through every intermediate component. App.jsx is the only
// provider — it owns the column's open/closed state since it's the one
// deciding the page's grid layout.
const QuickAddContext = createContext(() => {});

export const QuickAddProvider = QuickAddContext.Provider;

export function useQuickAdd() {
  return useContext(QuickAddContext);
}
