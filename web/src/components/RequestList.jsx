import { mediaStatusLabel, requestStatusLabel } from "../lib/labels";

// One row per Overseerr request, styled as a scannable list (not a dense
// table) — status as a pill, the library match (if any) as a spine-label
// chip, mirroring how a call number reads on a DVD case. Deliberately
// dumb/presentational — all data fetching lives in App.jsx — so this maps
// cleanly onto a future plugin UI component that just receives props.
export default function RequestList({ requests, selectedId, onSelect, searchQuery = "", onClearSearch }) {
  const isSearching = searchQuery.trim().length > 0;

  if (requests === null) {
    return <p className="p-5 text-sm text-[var(--text-faint)]">Loading requests…</p>;
  }
  if (requests.length === 0) {
    return isSearching ? (
      <div className="p-8 text-center text-sm text-[var(--text-faint)]">
        No requests match <span className="font-semibold text-[var(--text)]">"{searchQuery.trim()}"</span>.
        <button onClick={onClearSearch} className="block mx-auto mt-2 text-xs font-semibold text-[var(--accent)] hover:underline">
          Clear search
        </button>
      </div>
    ) : (
      <p className="p-5 text-sm text-[var(--text-faint)]">No requests found.</p>
    );
  }

  return (
    <div>
      <div className="px-5 py-3 border-b border-[var(--rule)] text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)] flex items-center justify-between">
        <span>Overseerr requests</span>
        {isSearching && (
          <span className="font-semibold normal-case tracking-normal text-[var(--text-faint)]">
            {requests.length} match{requests.length === 1 ? "" : "es"}
          </span>
        )}
      </div>
      {isSearching && (
        <div className="flex items-center gap-1.5 px-5 py-2 border-b border-[var(--rule)] bg-[var(--surface-raised)] text-[11px] text-[var(--text-faint)]">
          <span>matching</span>
          {["title", "requested by", "director"].map((field) => (
            <span
              key={field}
              className="text-[10.5px] font-semibold text-[var(--text-muted)] bg-[var(--bg)] border border-[var(--rule-strong)] rounded px-1.5 py-0.5"
            >
              {field}
            </span>
          ))}
        </div>
      )}
      {requests.map((r) => {
        const available = Number(r.media_status) === 5;
        return (
          <div
            key={r.id}
            onClick={() => onSelect(r)}
            className={`flex items-center gap-3 px-5 py-3 border-b border-[var(--rule)] cursor-pointer hover:bg-[var(--surface-raised)] ${
              selectedId === r.id ? "bg-[var(--surface-raised)] shadow-[inset_3px_0_0_var(--accent)]" : ""
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-sm truncate">
                {r.title}
                {r.tmdb?.release_date && (
                  <span className="text-[var(--text-faint)] font-normal"> ({r.tmdb.release_date.slice(0, 4)})</span>
                )}
              </div>
              <div className="text-xs text-[var(--text-faint)] mt-0.5">
                {r.type} · {requestStatusLabel(Number(r.request_status))} · requested by {r.requested_by}
                {r.tmdb?.director && <> · {r.tmdb.director}</>}
              </div>
            </div>

            <span
              className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${
                available
                  ? "text-[var(--available)] bg-[var(--available-bg)]"
                  : "text-[var(--pending)] bg-[var(--pending-bg)]"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current" />
              {mediaStatusLabel(Number(r.media_status))}
            </span>

            {r.type === "tv" && r.seasons?.length > 0 ? (
              <SeasonProgressBadge seasons={r.seasons} seasonMatches={r.season_matches} />
            ) : r.match?.status === "matched" ? (
              <span className="mono inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--available)] bg-[var(--available-bg)] whitespace-nowrap">
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                {r.match.bib_title}
                {r.match.bib_subtitle ? `: ${r.match.bib_subtitle}` : ""}
              </span>
            ) : r.match?.status === "unavailable" ? (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--accent)] bg-[var(--accent)]/10 whitespace-nowrap">
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                not in library
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--unmatched)] bg-[var(--unmatched-bg)] whitespace-nowrap">
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                unmatched
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Compact "x of y requested seasons matched" pill for TV rows — the season
// accordion itself lives in MatchPanel; this list only needs the summary.
// Green only once every requested season is matched; amber-ish "unmatched"
// tone otherwise so a partially-matched show still reads as needing attention.
function SeasonProgressBadge({ seasons, seasonMatches }) {
  const matchedCount = seasons.filter((s) => seasonMatches?.[s]?.status === "matched").length;
  const allMatched = seasons.length > 0 && matchedCount === seasons.length;
  return (
    <span
      className={`mono inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${
        allMatched ? "text-[var(--available)] bg-[var(--available-bg)]" : "text-[var(--unmatched)] bg-[var(--unmatched-bg)]"
      }`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {matchedCount}/{seasons.length} seasons
    </span>
  );
}
