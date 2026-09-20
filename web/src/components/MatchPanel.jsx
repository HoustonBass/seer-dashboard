import { useEffect, useRef, useState } from "react";
import { clearMatch, markUnavailable, saveMatch, searchLibrary } from "../lib/api";
import HoverZoomImage from "./HoverZoomImage";
import SearchResultsTable from "./SearchResultsTable";

const DEFAULT_FORMAT = "DVD";

// Detail/action panel for one selected Overseerr request, styled as a
// library "catalog slip" — search the library catalog, inspect ranked
// candidates, persist a chosen match. Owns its own search state so
// RequestList stays a dumb list.
export default function MatchPanel({ request, onMatchChange }) {
  const [query, setQuery] = useState(request.title);
  const [format, setFormat] = useState(DEFAULT_FORMAT);
  const [results, setResults] = useState([]);
  const [source, setSource] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const searchGeneration = useRef(0);

  useEffect(() => {
    setQuery(request.title);
    setFormat(DEFAULT_FORMAT);
    setResults([]);
    setSource(null);
    setError(null);
    // Auto-search on selection — same call the Search button makes, so a
    // prior cached search shows instantly and a never-searched title just
    // runs live, same as clicking Search yourself would. runSearch reads
    // `query`/`format` state, which the setters above haven't committed yet
    // in this render, so pass the new values explicitly instead of relying
    // on the (still-stale) closure.
    runSearch(false, request.title, DEFAULT_FORMAT);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request.id]);

  async function runSearch(refresh = false, overrideQuery, overrideFormat) {
    // Guards against a race if the user clicks through requests faster than
    // a search resolves — a slow, stale search landing after a newer
    // selection shouldn't clobber that newer selection's results.
    const generation = ++searchGeneration.current;
    const q = overrideQuery ?? query;
    const f = overrideFormat ?? format;
    setLoading(true);
    setError(null);
    try {
      const data = await searchLibrary(q, f, { refresh });
      if (searchGeneration.current !== generation) return;
      setResults(data.results);
      setSource(data.source);
    } catch (e) {
      if (searchGeneration.current !== generation) return;
      setError(e.message);
    } finally {
      if (searchGeneration.current === generation) setLoading(false);
    }
  }

  async function handleChoose(candidate) {
    await saveMatch({
      request_id: request.id,
      tmdb_id: request.tmdb_id,
      media_type: request.type,
      seerr_title: request.title,
      bib_id: candidate.bib_id,
      bib_title: candidate.title,
      bib_subtitle: candidate.subtitle,
    });
    onMatchChange(request.id, {
      status: "matched",
      bib_id: candidate.bib_id,
      bib_title: candidate.title,
      bib_subtitle: candidate.subtitle,
    });
  }

  async function handleMarkUnavailable() {
    await markUnavailable({
      request_id: request.id,
      tmdb_id: request.tmdb_id,
      media_type: request.type,
      seerr_title: request.title,
    });
    onMatchChange(request.id, { status: "unavailable", bib_id: null, bib_title: null, bib_subtitle: null });
  }

  async function handleClear() {
    await clearMatch(request.id);
    onMatchChange(request.id, null);
  }

  return (
    <div className="rounded border border-[var(--rule)] bg-[var(--surface-raised)] p-5">
      <h2 className="font-serif text-xl" style={{ fontFamily: "Georgia, 'Iowan Old Style', serif" }}>
        {request.title}
      </h2>
      <p className="mono text-xs text-[var(--text-muted)] mt-0.5">
        request #{request.id} · tmdbId {request.tmdb_id} · {request.type}
      </p>

      {request.tmdb && (
        <div className="mt-3 flex gap-3 text-sm">
          {request.tmdb.poster_path && (
            <HoverZoomImage
              src={`https://image.tmdb.org/t/p/w92${request.tmdb.poster_path}`}
              zoomSrc={`https://image.tmdb.org/t/p/w500${request.tmdb.poster_path}`}
              zoomWidth={320}
              className="w-14 rounded border border-[var(--rule)] shrink-0 cursor-zoom-in"
            />
          )}
          <div className="min-w-0">
            <p className="text-[var(--text-muted)]">
              {request.tmdb.release_date?.slice(0, 4)}
              {request.tmdb.director && <> · directed by {request.tmdb.director}</>}
              {request.tmdb.runtime && <> · {request.tmdb.runtime} min</>}
            </p>
            {request.tmdb.genres?.length > 0 && (
              <p className="text-xs text-[var(--text-faint)] mt-0.5">{request.tmdb.genres.join(", ")}</p>
            )}
            {request.tmdb.overview && (
              <p className="text-xs text-[var(--text-faint)] mt-1.5 line-clamp-2">{request.tmdb.overview}</p>
            )}
          </div>
        </div>
      )}

      {request.match?.status === "matched" && (
        <div className="flex items-center gap-2 text-sm mt-4 bg-[var(--available-bg)] border border-[var(--available)]/30 rounded px-3 py-2">
          <span className="text-[var(--text)]">
            Matched to <strong>{request.match.bib_title}</strong>
            {request.match.bib_subtitle ? `: ${request.match.bib_subtitle}` : ""}{" "}
            <span className="mono text-[var(--text-faint)]">({request.match.bib_id})</span>
          </span>
          <button onClick={handleClear} className="ml-auto text-xs font-semibold text-[var(--accent)] hover:underline">
            Clear
          </button>
        </div>
      )}

      {request.match?.status === "unavailable" && (
        <div className="flex items-center gap-2 text-sm mt-4 bg-[var(--unmatched-bg)] border border-[var(--text-faint)]/30 rounded px-3 py-2">
          <span className="text-[var(--text)]">Confirmed not in the library catalog.</span>
          <button onClick={handleClear} className="ml-auto text-xs font-semibold text-[var(--accent)] hover:underline">
            Clear
          </button>
        </div>
      )}

      <div className="flex gap-2 items-center mt-4">
        <input
          className="flex-1 text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface)] px-2.5 py-1.5"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
        />
        <select
          className="text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface)] px-2 py-1.5"
          value={format}
          onChange={(e) => setFormat(e.target.value)}
        >
          <option value="">any format</option>
          <option value="DVD">DVD</option>
          <option value="BLU-RAY">Blu-ray</option>
          <option value="BK">Book</option>
          <option value="AB">Audiobook</option>
        </select>
        <button
          onClick={() => runSearch(false)}
          disabled={loading}
          className="text-sm font-semibold px-3 py-1.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-contrast)] disabled:opacity-50"
        >
          Search
        </button>
        <button
          onClick={() => runSearch(true)}
          disabled={loading}
          className="text-sm font-semibold px-3 py-1.5 rounded border border-[var(--rule-strong)] text-[var(--text-muted)] hover:bg-[var(--surface)] disabled:opacity-50"
          title="Bypass cache and re-fetch live"
        >
          Refresh
        </button>
      </div>

      <div className="flex items-center gap-3 mt-2">
        {source && <p className="mono text-xs text-[var(--text-faint)]">source: {source}</p>}
        {error && <p className="text-sm text-[var(--accent)]">{error}</p>}
        {request.match?.status !== "unavailable" && (
          <button
            onClick={handleMarkUnavailable}
            className="ml-auto text-xs font-semibold text-[var(--text-faint)] hover:text-[var(--accent)] hover:underline"
            title="Confirm the library doesn't have this, so it stops showing as unmatched"
          >
            Not in the library
          </button>
        )}
      </div>

      <SearchResultsTable results={results} onChoose={handleChoose} chosenBibId={request.match?.bib_id} />
    </div>
  );
}
