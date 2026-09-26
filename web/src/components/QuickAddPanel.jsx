import { useEffect, useState } from "react";
import { quickAdd, searchTmdb } from "../lib/api";
import HoverZoomImage from "./HoverZoomImage";

// Third-column content for "I found this in the library and want it in
// Overseerr too" — opened via the hover badge on a SearchResultsTable row
// (see useQuickAdd/QuickAddContext). Deliberately styled like MatchPanel
// (same panel chrome, same poster treatment) since it's doing the same kind
// of job — confirm a title, take an action — just for a brand new request
// instead of an existing one.
// Library records carry the meaningful part in the subtitle as often as not
// (e.g. "Dune" title / "Part Two" subtitle, or a TV bib's "Season One") — the
// title alone is frequently ambiguous, so the default TMDB search seeds with
// both, same as how the row itself is displayed.
function defaultQueryFor(libraryResult) {
  return libraryResult.subtitle ? `${libraryResult.title}: ${libraryResult.subtitle}` : libraryResult.title;
}

export default function QuickAddPanel({ libraryResult, onClose, onAddFailed }) {
  const [query, setQuery] = useState(defaultQueryFor(libraryResult));
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [addingId, setAddingId] = useState(null);
  const [added, setAdded] = useState(null);
  // Distinguishes an add failure (saved for retry, see below) from a plain
  // search failure so the "saved for retry" hint doesn't show for the latter.
  const [addFailed, setAddFailed] = useState(false);

  useEffect(() => {
    const defaultQuery = defaultQueryFor(libraryResult);
    setQuery(defaultQuery);
    setResults([]);
    setError(null);
    setAddFailed(false);
    setAdded(null);
    runSearch(defaultQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libraryResult]);

  async function runSearch(overrideQuery) {
    const q = overrideQuery ?? query;
    setLoading(true);
    setError(null);
    setAddFailed(false);
    try {
      const data = await searchTmdb(q);
      setResults(data.results);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(candidate) {
    setAddingId(candidate.tmdb_id);
    setError(null);
    setAddFailed(false);
    try {
      await quickAdd({
        media_type: candidate.media_type,
        tmdb_id: candidate.tmdb_id,
        title: candidate.title,
        // TV candidates only create the (whole-series) request — see api.js's
        // note on why we don't guess a season_number here.
        ...(candidate.media_type === "movie"
          ? { bib_id: libraryResult.bib_id, bib_title: libraryResult.title, bib_subtitle: libraryResult.subtitle }
          : {}),
      });
      setAdded(candidate);
    } catch (e) {
      setError(e.message);
      setAddFailed(true);
      // Couldn't reach Overseerr — the backend already saved the attempt for
      // retry (see FailedQuickAddRepo); let the header badge know so it
      // shows up without waiting for the popover's own next poll.
      onAddFailed?.();
    } finally {
      setAddingId(null);
    }
  }

  return (
    <div className="rounded border border-[var(--rule)] bg-[var(--surface-raised)] p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-serif text-xl truncate" style={{ fontFamily: "Georgia, 'Iowan Old Style', serif" }}>
            Add "{defaultQueryFor(libraryResult)}"
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Search Overseerr/TMDB to confirm the right title before requesting
          </p>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full border border-[var(--rule-strong)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          ×
        </button>
      </div>

      {added ? (
        <div className="flex items-center gap-2 text-sm mt-4 bg-[var(--available-bg)] border border-[var(--available)]/30 rounded px-3 py-2.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--available)] shrink-0" />
          <span className="text-[var(--text)]">
            Request created{added.media_type === "movie" ? " and matched" : ""} for <strong>{added.title}</strong>
            {added.media_type === "tv" && " — match individual seasons from the request list once it appears."}
          </span>
        </div>
      ) : (
        <>
          <div className="flex gap-2 mt-4">
            <input
              className="flex-1 text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface)] px-2.5 py-1.5"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
            />
            <button
              onClick={() => runSearch()}
              disabled={loading}
              className="text-sm font-semibold px-3 py-1.5 rounded border border-[var(--primary)] text-[var(--primary)] hover:bg-[var(--primary)] hover:text-[var(--primary-contrast)] disabled:opacity-50"
            >
              Search
            </button>
          </div>

          {loading && <p className="text-sm text-[var(--text-faint)] mt-3">Searching…</p>}

          {!loading && error && (
            <p className="text-sm text-[var(--accent)] bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded px-3 py-2.5 mt-3">
              {error}
              {addFailed && " — saved, retry it from the header's failed-adds menu."}
            </p>
          )}

          {!loading && !error && results.length === 0 && (
            <p className="text-sm text-[var(--text-faint)] mt-3">No matches on TMDB for this search.</p>
          )}

          {!loading && !error && results.length > 0 && (
            <div className="mt-3">
              {results.map((c) => (
                <div
                  key={`${c.media_type}-${c.tmdb_id}`}
                  className="flex items-center gap-3 py-2.5 px-2 -mx-2 rounded border-b border-dashed border-[var(--rule)] last:border-none"
                >
                  {c.poster_path ? (
                    <HoverZoomImage
                      src={`https://image.tmdb.org/t/p/w92${c.poster_path}`}
                      zoomSrc={`https://image.tmdb.org/t/p/w500${c.poster_path}`}
                      zoomWidth={320}
                      className="w-10 h-14 object-cover rounded-sm shrink-0 border border-[var(--rule)] bg-[var(--surface)] cursor-zoom-in"
                    />
                  ) : (
                    <div className="w-10 h-14 shrink-0 rounded-sm border border-dashed border-[var(--rule)] bg-[var(--surface)]" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold truncate">
                      {c.title}{" "}
                      <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-faint)]">
                        {c.media_type}
                      </span>
                    </div>
                    <div className="text-xs text-[var(--text-faint)]">{c.release_date?.slice(0, 4)}</div>
                  </div>
                  <button
                    onClick={() => handleAdd(c)}
                    disabled={addingId === c.tmdb_id}
                    className="shrink-0 text-xs font-semibold px-3 py-1.5 rounded border border-[var(--primary)] text-[var(--primary)] hover:bg-[var(--primary)] hover:text-[var(--primary-contrast)] disabled:opacity-50"
                  >
                    {addingId === c.tmdb_id ? "Adding…" : c.media_type === "movie" ? "Request & mark found" : "Request"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
