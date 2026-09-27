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

// A branch might match the saved preference by either its code (what
// LibraryRepo/BiblioCommons actually key branches by, e.g. "MILTON") or its
// display name ("Milton Branch") — the settings input doesn't force the
// user to know which one they typed, so check both, case-insensitively.
// Shared by SearchResultsTable's "Which branches?" list and RequestList's
// "at my branch" indicator — one place to define what "matches" means.
export function isDefaultBranch(branch, defaultBranch) {
  if (!defaultBranch) return false;
  const needle = defaultBranch.trim().toLowerCase();
  return branch.branch_code.toLowerCase() === needle || branch.branch_name.toLowerCase().includes(needle);
}
