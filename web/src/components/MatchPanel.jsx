import { useEffect, useState } from "react";
import { clearMatch, saveMatch, searchLibrary } from "../lib/api";
import SearchResultsTable from "./SearchResultsTable";

// Detail/action panel for one selected Overseerr request, styled as a
// library "catalog slip" — search the library catalog, inspect ranked
// candidates, persist a chosen match. Owns its own search state so
// RequestList stays a dumb list.
export default function MatchPanel({ request, onMatchSaved }) {
  const [query, setQuery] = useState(request.title);
  const [format, setFormat] = useState("DVD");
  const [results, setResults] = useState([]);
  const [source, setSource] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setQuery(request.title);
    setResults([]);
    setSource(null);
  }, [request.id]);

  async function runSearch(refresh = false) {
    setLoading(true);
    setError(null);
    try {
      const data = await searchLibrary(query, format, { refresh });
      setResults(data.results);
      setSource(data.source);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
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
    onMatchSaved();
  }

  async function handleClear() {
    await clearMatch(request.id);
    onMatchSaved();
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
            <img
              src={`https://image.tmdb.org/t/p/w92${request.tmdb.poster_path}`}
              alt=""
              className="w-14 rounded border border-[var(--rule)] shrink-0"
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

      {request.match && (
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

      {source && <p className="mono text-xs text-[var(--text-faint)] mt-2">source: {source}</p>}
      {error && <p className="text-sm text-[var(--accent)] mt-2">{error}</p>}

      <SearchResultsTable results={results} onChoose={handleChoose} chosenBibId={request.match?.bib_id} />
    </div>
  );
}
