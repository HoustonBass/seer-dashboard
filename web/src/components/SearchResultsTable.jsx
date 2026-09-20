import HoverZoomImage from "./HoverZoomImage";

// Renders the ranked candidates from /api/search (same ranking as
// scripts/library/search.sh — see scripts/discovery/search.md), as "index
// cards" — a score mark, availability pill, call number as a spine-label
// chip. Never auto-picks; every row gets an explicit "Choose" action, per
// the decision that matching stays a human call until proven reliable.
export default function SearchResultsTable({ results, onChoose, chosenBibId }) {
  if (results.length === 0) {
    return <p className="text-sm text-[var(--text-faint)] mt-3">No results.</p>;
  }

  return (
    <div className="mt-3">
      {results.map((r) => {
        const scoreStyle =
          r.match_score === 2
            ? "text-[var(--available)] bg-[var(--available-bg)]"
            : r.match_score === 1
              ? "text-[var(--pending)] bg-[var(--pending-bg)]"
              : "text-[var(--text-faint)] bg-[var(--unmatched-bg)]";
        const chosen = chosenBibId === r.bib_id;

        return (
          <div
            key={r.bib_id}
            className={`flex items-center gap-3 py-2.5 px-2 -mx-2 rounded border-b border-dashed border-[var(--rule)] last:border-none ${
              chosen ? "bg-[var(--available-bg)]" : ""
            }`}
          >
            <span className={`mono w-6 h-6 shrink-0 rounded-full flex items-center justify-center text-xs font-bold ${scoreStyle}`}>
              {r.match_score}
            </span>

            {r.jacket_url ? (
              <HoverZoomImage
                src={r.jacket_url}
                zoomWidth={320}
                className="w-10 h-14 object-cover rounded-sm shrink-0 border border-[var(--rule)] bg-[var(--surface)] cursor-zoom-in"
                onError={(e) => {
                  e.currentTarget.style.visibility = "hidden";
                }}
              />
            ) : (
              <div className="w-10 h-14 shrink-0 rounded-sm border border-dashed border-[var(--rule)] bg-[var(--surface)]" />
            )}

            <div className="flex-1 min-w-0">
              <div className="font-semibold text-sm truncate">
                {r.record_url ? (
                  <a
                    href={r.record_url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:underline hover:text-[var(--accent)]"
                    title="View the real listing on the library website"
                  >
                    {r.title}
                  </a>
                ) : (
                  r.title
                )}
                {r.subtitle && <span className="text-[var(--text-faint)] font-normal"> — {r.subtitle}</span>}
              </div>
              <div className="flex items-center gap-2 flex-wrap mt-1 text-xs text-[var(--text-faint)]">
                <span
                  className={`inline-flex items-center gap-1 font-semibold px-2 py-0.5 rounded-full ${
                    r.availability_status === "AVAILABLE"
                      ? "text-[var(--available)] bg-[var(--available-bg)]"
                      : "text-[var(--unmatched)] bg-[var(--unmatched-bg)]"
                  }`}
                >
                  {r.availability_status.toLowerCase()} ({r.available_copies}/{r.total_copies})
                </span>
                <span className="mono px-1.5 py-0.5 rounded border border-[var(--rule-strong)] bg-[var(--surface)]">
                  {r.call_number}
                </span>
                {r.publication_date && <span>{r.publication_date}</span>}
                {r.authors && <span>{r.authors}</span>}
              </div>
            </div>

            <button
              onClick={() => onChoose(r)}
              className={`shrink-0 inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded border transition-colors ${
                chosen
                  ? "border-[var(--available)] text-[var(--available)] bg-[var(--available-bg)]"
                  : "border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-contrast)]"
              }`}
            >
              {chosen && "✓"} {chosen ? "Chosen" : "Choose"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
