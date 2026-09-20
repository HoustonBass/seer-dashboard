// Persists the user's preferred starting filter for the request list —
// separate from theme (ThemeModeContext) but the same pattern: read once at
// App.jsx's initial state, written from the Settings popover. Purely a
// frontend preference (localStorage), not a backend feature switch — this
// isn't test/debug behavior, it's "which filter should already be selected
// when I open the page."
const STORAGE_KEY = "seerr-dashboard:default-filter";
const FALLBACK = "approved";

// Must match the <option> values in App.jsx's filter dropdown — "unmatched"/
// "matched" are client-side (see App.jsx's OVERSEERR_FILTERS), the rest map
// straight to Overseerr's own filter values.
export const FILTER_OPTIONS = [
  { value: "all", label: "all" },
  { value: "approved", label: "approved" },
  { value: "available", label: "available" },
  { value: "processing", label: "processing" },
  { value: "unmatched", label: "unmatched" },
  { value: "matched", label: "matched" },
];

export function getDefaultFilter() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (FILTER_OPTIONS.some((o) => o.value === stored)) return stored;
  } catch {
    // fall through to fallback
  }
  return FALLBACK;
}

export function setDefaultFilter(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // best-effort persistence only
  }
}
