// Persists the user's preferred/home library branch — purely a frontend
// preference (localStorage), same pattern as defaultFilter.js. Used to
// highlight that branch's pill in SearchResultsTable's "Which branches?"
// list so it's obvious at a glance whether your own branch has a copy,
// without needing a canonical branch-list endpoint (none is discovered —
// see scripts/discovery/branch-availability.md) to build a dropdown from.
// Stored as a branch_code (e.g. "MILTON"), matched case-insensitively
// against LibraryRepo.get_bib_branches' branch_code field.
const STORAGE_KEY = "seerr-dashboard:default-branch";

export function getDefaultBranch() {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setDefaultBranch(value) {
  try {
    if (value) localStorage.setItem(STORAGE_KEY, value);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // best-effort persistence only
  }
}
