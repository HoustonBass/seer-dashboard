// Whether collection groups start collapsed — purely a frontend preference
// (localStorage), same pattern as defaultBranch.js. Grouping itself is always
// on; the backend sends tmdb.collection_id / collection_name (TmdbRepo).
const STORAGE_KEY = "seerr-dashboard:collapse-collections";

export function getCollapseCollections() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setCollapseCollections(enabled) {
  try {
    if (enabled) localStorage.setItem(STORAGE_KEY, "1");
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // best-effort persistence only
  }
}

// Turns an ordered request list into render entries: plain rows, plus a
// group wherever 2+ movies in the list share a TMDB collection. A group sits
// where its first member sits, so the list's own order (oldest request
// first) is preserved and the group doesn't jump around as rows stream in.
// Counts only what's in `requests` — after a search/filter, a collection
// left with one visible movie falls back to a plain row.
export function groupByCollection(requests) {
  const members = new Map();
  for (const r of requests) {
    const id = r.type === "movie" ? r.tmdb?.collection_id : null;
    if (id) members.set(id, [...(members.get(id) ?? []), r]);
  }

  const entries = [];
  const placed = new Set();
  for (const r of requests) {
    const id = r.type === "movie" ? r.tmdb?.collection_id : null;
    const group = id && members.get(id);
    if (!group || group.length < 2) {
      entries.push({ kind: "row", request: r });
    } else if (!placed.has(id)) {
      placed.add(id);
      entries.push({ kind: "group", key: id, name: r.tmdb.collection_name, requests: group });
    }
  }
  return entries;
}
