// Thin wrapper over app/main.py's JSON API. Kept separate from components so
// swapping the backend later (e.g. for the real Jellyfin plugin's API) means
// changing this file, not every component that calls it.

// /api/search returns { source: "cache"|"live", results } so the FE can show
// whether a response came from the repo's SQLite cache or a live API call —
// see app/repos/*_repo.py.

// /api/requests streams newline-delimited JSON — one `{"row": ..., "source":
// "cache"|"live"}` object per line — instead of one big array, so rows can
// render as each request's title/TMDB data resolves rather than waiting for
// the whole batch (a cold cache used to mean ~250 requests before anything
// appeared). `onRow` is called once per line as it arrives.
export async function streamRequests(filter = "all", { refresh = false } = {}, onRow) {
  const params = new URLSearchParams({ filter });
  if (refresh) params.set("refresh", "1");
  const res = await fetch(`/api/requests?${params}`);
  if (!res.ok) throw new Error(`fetchRequests failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex;
    while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newlineIndex);
      buffer = buffer.slice(newlineIndex + 1);
      if (line.trim()) onRow(JSON.parse(line));
    }
  }
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

export async function markUnavailable(match) {
  const res = await fetch("/api/matches/unavailable", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(match),
  });
  if (!res.ok) throw new Error(`markUnavailable failed: ${res.status}`);
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
