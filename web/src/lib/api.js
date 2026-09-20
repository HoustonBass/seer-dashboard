// Thin wrapper over app/main.py's JSON API. Kept separate from components so
// swapping the backend later (e.g. for the real Jellyfin plugin's API) means
// changing this file, not every component that calls it.

// Both /api/requests and /api/search return { source: "cache"|"live", results }
// so the FE can show whether a given response came from the repo's SQLite
// cache or a live API call — see app/repos/*_repo.py.

export async function fetchRequests(filter = "all", { refresh = false } = {}) {
  const params = new URLSearchParams({ filter });
  if (refresh) params.set("refresh", "1");
  const res = await fetch(`/api/requests?${params}`);
  if (!res.ok) throw new Error(`fetchRequests failed: ${res.status}`);
  return res.json();
}

export async function searchLibrary(query, format = "", { refresh = false } = {}) {
  const params = new URLSearchParams({ query, format });
  if (refresh) params.set("refresh", "1");
  const res = await fetch(`/api/search?${params}`);
  if (!res.ok) throw new Error(`searchLibrary failed: ${res.status}`);
  return res.json();
}

export async function saveMatch(match) {
  const res = await fetch("/api/matches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(match),
  });
  if (!res.ok) throw new Error(`saveMatch failed: ${res.status}`);
  return res.json();
}

export async function clearMatch(requestId) {
  const res = await fetch(`/api/matches/${requestId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`clearMatch failed: ${res.status}`);
  return res.json();
}

export async function fetchSettings() {
  const res = await fetch("/api/settings");
  if (!res.ok) throw new Error(`fetchSettings failed: ${res.status}`);
  return res.json();
}

export async function setSetting(key, enabled, seconds) {
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, enabled, seconds }),
  });
  if (!res.ok) throw new Error(`setSetting failed: ${res.status}`);
  return res.json();
}
