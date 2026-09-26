import { useState } from "react";
import HoverZoomImage from "./HoverZoomImage";
import { useQuickAdd } from "../QuickAddContext";
import { fetchBibEdition } from "../lib/api";

// Renders the ranked candidates from /api/search (same ranking as
// scripts/library/search.sh — see scripts/discovery/search.md), as "index
// cards" — a score mark, availability pill, call number as a spine-label
// chip. Never auto-picks; every row gets an explicit "Choose" action, per
// the decision that matching stays a human call until proven reliable.
export default function SearchResultsTable({ results, onChoose, chosenBibId }) {
  // Opens the quick-add third column at the App.jsx level — a completely
  // different title from the one being matched here (see QuickAddPanel),
  // not part of the match/onChoose flow.
  const openQuickAdd = useQuickAdd();

  if (results.length === 0) {
    return <p className="text-sm text-[var(--text-faint)] mt-3">No results.</p>;
  }

  return (
    <div className="mt-3">
      {results.map((r) => (
        <ResultRow
          key={r.bib_id}
          r={r}
          chosen={chosenBibId === r.bib_id}
          onChoose={onChoose}
          openQuickAdd={openQuickAdd}
        />
      ))}
    </div>
  );
}

// Extracted from SearchResultsTable's map body so each row can own its own
// on-demand "what edition is this?" fetch state (see below) — hooks can't
// live inside a .map() callback.
function ResultRow({ r, chosen, onChoose, openQuickAdd }) {
  // Same-title/same-year search results (e.g. three "Pacific Rim" DVDs) look
  // identical from briefInfo alone — the only thing that actually tells them
  // apart (rental vs. two-disc special edition vs. anamorphic widescreen) is
  // catalogBibs' brief.edition, which costs an extra live call per bib_id.
  // Fetched lazily on click, not for every result up front — see
  // LibraryRepo.get_bib_edition.
  const [edition, setEdition] = useState(null);
  const [editionLoading, setEditionLoading] = useState(false);
  const [editionError, setEditionError] = useState(null);

  async function handleShowEdition() {
    setEditionLoading(true);
    setEditionError(null);
    try {
      const data = await fetchBibEdition(r.bib_id);
      setEdition(data.edition);
    } catch (e) {
      setEditionError(e.message);
    } finally {
      setEditionLoading(false);
    }
  }

  const scoreStyle =
    r.match_score === 2
      ? "text-[var(--available)] bg-[var(--available-bg)]"
      : r.match_score === 1
        ? "text-[var(--pending)] bg-[var(--pending-bg)]"
        : "text-[var(--text-faint)] bg-[var(--unmatched-bg)]";

  return (
    <div
      className={`group py-2.5 px-2 -mx-2 rounded border-b border-dashed border-[var(--rule)] last:border-none ${
        chosen ? "bg-[var(--available-bg)]" : ""
      }`}
    >
      <div className="flex items-center gap-3">
        <span className={`mono w-6 h-6 shrink-0 rounded-full flex items-center justify-center text-xs font-bold ${scoreStyle}`}>
          {r.match_score}
        </span>

        <div className="relative w-10 h-14 shrink-0">
          {r.jacket_url ? (
            <HoverZoomImage
              src={r.jacket_url}
              zoomSrc={r.jacket_url_large}
              zoomWidth={320}
              className="w-10 h-14 object-cover rounded-sm border border-[var(--rule)] bg-[var(--surface)] cursor-zoom-in"
              onError={(e) => {
                e.currentTarget.style.visibility = "hidden";
              }}
            />
          ) : (
            <div className="w-10 h-14 rounded-sm border border-dashed border-[var(--rule)] bg-[var(--surface)]" />
          )}
          {r.existing_match ? (
            // Already matched to some (possibly different) request —
            // e.g. this bib is "Despicable Me 4" and it's already
            // matched to that request, even though this result surfaced
            // while searching "Despicable Me 2". Quick-add would create
            // a duplicate Overseerr request, so it doesn't get offered
            // here — this badge explains why instead of just vanishing.
            <span
              title={`Already requested as "${r.existing_match.seerr_title}" — quick-add is disabled to avoid a duplicate request`}
              className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full border border-[var(--available)]/40 bg-[var(--available-bg)] text-[var(--available)] text-xs leading-none flex items-center justify-center shadow opacity-0 scale-90 transition-all group-hover:opacity-100 group-hover:scale-100"
            >
              ✓
            </span>
          ) : (
            <button
              onClick={() => openQuickAdd(r)}
              title="Not what you were searching for? Add this to Overseerr and mark it found"
              className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full border border-[var(--rule-strong)] bg-[var(--surface-raised)] text-[var(--text-muted)] text-xs leading-none flex items-center justify-center shadow opacity-0 scale-90 transition-all group-hover:opacity-100 group-hover:scale-100 hover:border-[var(--accent)] hover:text-[var(--accent)]"
            >
              +
            </button>
          )}
        </div>

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
            {!edition && (
              <button
                onClick={handleShowEdition}
                disabled={editionLoading}
                className="font-semibold text-[var(--accent)] hover:underline disabled:opacity-50"
                title="Same title as another result? See what edition this specific copy is"
              >
                {editionLoading ? "Checking edition…" : "What edition is this?"}
              </button>
            )}
          </div>
          {editionError && (
            <p className="text-xs text-[var(--accent)] mt-1">Couldn't load edition info — {editionError}.</p>
          )}
          {edition && (
            <p className="text-xs text-[var(--text-muted)] mt-1">
              {edition.edition && <span className="font-semibold text-[var(--text)]">{edition.edition}</span>}
              {edition.edition && edition.publication_note && " — "}
              {edition.publication_note}
              {!edition.edition && !edition.publication_note && "No edition detail on file for this copy."}
            </p>
          )}
        </div>

        <button
          onClick={(e) => onChoose(r, e.altKey)}
          title={chosen ? undefined : "Option/Alt+click to choose and advance — next season if TV, otherwise the next unmatched request"}
          className={`shrink-0 inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded border transition-colors ${
            chosen
              ? "border-[var(--available)] text-[var(--available)] bg-[var(--available-bg)]"
              : "border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-contrast)]"
          }`}
        >
          {chosen && "✓"} {chosen ? "Chosen" : "Choose"}
        </button>
      </div>
    </div>
  );
}
