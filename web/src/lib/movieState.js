// Where a movie stands in Overseerr, for results that aren't (necessarily)
// requests yet — search hits and collection parts carry only Overseerr's own
// media status (5 = available, 2/3/4 = requested in some form), and no status
// at all when nobody has ever requested it.
export function movieState(mediaStatus) {
  const status = Number(mediaStatus);
  if (status === 5) return { key: "available", label: "Available" };
  if (status >= 2 && status <= 4) return { key: "requested", label: "Requested" };
  return { key: "not_requested", label: "Not requested" };
}

export const MOVIE_STATE_PILL = {
  available: "text-[var(--available)] bg-[var(--available-bg)]",
  requested: "text-[var(--pending)] bg-[var(--pending-bg)]",
  not_requested: "text-[var(--unmatched)] bg-[var(--unmatched-bg)]",
};

// "2 available · 1 requested · 1 not requested" for a list of parts.
export function summarizeStates(parts) {
  const counts = new Map();
  for (const p of parts) {
    const { key, label } = movieState(p.media_status);
    counts.set(key, { label: label.toLowerCase(), n: (counts.get(key)?.n ?? 0) + 1 });
  }
  return ["available", "requested", "not_requested"]
    .filter((k) => counts.has(k))
    .map((k) => `${counts.get(k).n} ${counts.get(k).label}`)
    .join(" · ");
}
