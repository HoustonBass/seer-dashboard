import { useEffect, useRef, useState } from "react";
import { searchLibrary } from "../lib/api";
import SearchResultsTable from "./SearchResultsTable";

export const DEFAULT_FORMAT = "DVD";

// The actual "search the library, pick a candidate, or mark it not in
// library" unit — extracted out of MatchPanel so it can be reused once per
// movie (the whole item) or once per season for a TV show (see
// MatchPanel.jsx's SeasonAccordion). Doesn't know about request_id/seasons/
// tmdb/etc. at all — the parent owns identity and persistence (onChoose/
// onMarkUnavailable/onClear are handed the decision, not asked to save it).
export default function MatchSearchBox({ defaultQuery, match, autoSearchKey, onChoose, onMarkUnavailable, onClear, onPlaceHold }) {
  const [query, setQuery] = useState(defaultQuery);
  const [format, setFormat] = useState(DEFAULT_FORMAT);
  const [results, setResults] = useState([]);
  const [source, setSource] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [holding, setHolding] = useState(false);
  const [holdError, setHoldError] = useState(null);
  const searchGeneration = useRef(0);

  // The stored match.availability_status is only a snapshot from whenever
  // the match was made — it's null for anything matched before this feature
  // existed (i.e. most real matches), and can go stale either direction
  // after that (checked back in, or someone else grabbed the last copy).
  // This panel already auto-searches on every open, so prefer that live
  // result for the matched bib when we have it; fall back to the stored
  // snapshot only if the live search didn't happen to include it.
  const liveAvailabilityStatus = results.find((r) => r.bib_id === match?.bib_id)?.availability_status;
  const availabilityStatus = liveAvailabilityStatus ?? match?.availability_status;

  async function handlePlaceHold() {
    setHolding(true);
    setHoldError(null);
    try {
      await onPlaceHold(match);
    } catch (e) {
      setHoldError(e.message);
    } finally {
      setHolding(false);
    }
  }

  useEffect(() => {
    setQuery(defaultQuery);
    setFormat(DEFAULT_FORMAT);
    setResults([]);
    setSource(null);
    setError(null);
    // Auto-search whenever autoSearchKey changes (a new request, or a new
    // season within the same request) — same call the Search button makes,
    // so a prior cached search shows instantly and a never-searched title
    // just runs live. runSearch reads `query`/`format` state, which the
    // setters above haven't committed yet in this render, so pass the new
    // values explicitly instead of relying on the (still-stale) closure.
    runSearch(false, defaultQuery, DEFAULT_FORMAT);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSearchKey]);

  async function runSearch(refresh = false, overrideQuery, overrideFormat) {
    // Guards against a race if the user switches away faster than a search
    // resolves — a slow, stale search landing after a newer selection
    // shouldn't clobber that newer selection's results.
    const generation = ++searchGeneration.current;
    const q = overrideQuery ?? query;
    const f = overrideFormat ?? format;
    setLoading(true);
    setError(null);
    // Clear the previous attempt's results/source immediately, not just on
    // success — otherwise a slow or failed search leaves stale "success"
    // state on screen (e.g. an old empty result set) that reads as current
    // when it isn't, which is exactly what looked like a false "no results".
    setResults([]);
    setSource(null);
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

  return (
    <div>
      {match?.status === "matched" && (
        <div className="mb-3">
          <div className="flex flex-wrap items-center gap-2 text-sm bg-[var(--available-bg)] border border-[var(--available)]/30 rounded px-3 py-2">
            <span className="text-[var(--text)] min-w-0">
              Matched to <strong>{match.bib_title}</strong>
              {match.bib_subtitle ? `: ${match.bib_subtitle}` : ""}{" "}
              <span className="mono text-[var(--text-faint)]">({match.bib_id})</span>
            </span>

            {match.hold_id ? (
              <span className="mono text-xs font-semibold text-[var(--available)] whitespace-nowrap">
                On hold ({match.hold_id})
              </span>
            ) : (
              availabilityStatus && availabilityStatus !== "AVAILABLE" && onPlaceHold && (
                <button
                  onClick={handlePlaceHold}
                  disabled={holding}
                  title="Places a real hold on your Fulton County library account"
                  className="shrink-0 text-xs font-semibold px-3 py-1.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-contrast)] disabled:opacity-50 whitespace-nowrap"
                >
                  {holding ? "Placing hold…" : "Place a hold"}
                </button>
              )
            )}

            <button onClick={onClear} className="ml-auto text-xs font-semibold text-[var(--accent)] hover:underline">
              Clear
            </button>
          </div>
          {holdError && (
            <p className="text-xs text-[var(--accent)] mt-1.5">Hold failed — {holdError}. Try again in a moment.</p>
          )}
        </div>
      )}

      {match?.status === "unavailable" && (
        <div className="flex items-center gap-2 text-sm mb-3 bg-[var(--unmatched-bg)] border border-[var(--text-faint)]/30 rounded px-3 py-2">
          <span className="text-[var(--text)]">Confirmed not in the library catalog.</span>
          <button onClick={onClear} className="ml-auto text-xs font-semibold text-[var(--accent)] hover:underline">
            Clear
          </button>
        </div>
      )}

      {/* flex-wrap, not a rigid single row — this panel's width isn't fixed
          (it shrinks from ~half the page to ~a third when the quick-add
          third column opens, see App.jsx's grid-cols toggle), and a
          non-wrapping row silently overflowed/got clipped at the narrower
          width instead of just wrapping to a second line. */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="flex-1 min-w-[140px] text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface)] px-2.5 py-1.5"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
        />
        <select
          className="shrink-0 text-sm rounded border border-[var(--rule-strong)] bg-[var(--surface)] px-2 py-1.5"
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
          className="shrink-0 text-sm font-semibold px-3 py-1.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-contrast)] disabled:opacity-50"
        >
          Search
        </button>
        <button
          onClick={() => runSearch(true)}
          disabled={loading}
          className="shrink-0 text-sm font-semibold px-3 py-1.5 rounded border border-[var(--rule-strong)] text-[var(--text-muted)] hover:bg-[var(--surface)] disabled:opacity-50"
          title="Bypass cache and re-fetch live"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="text-sm text-[var(--text-faint)] mt-3">Searching the library…</p>}

      {!loading && error && (
        <div className="flex items-center gap-2 text-sm mt-3 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded px-3 py-2.5">
          <span className="text-[var(--accent)]">
            Search failed — {error}. That's not the same as "not found"; try Search again rather than marking
            it unavailable.
          </span>
        </div>
      )}

      {!loading && !error && source && (
        <p className="mono text-xs text-[var(--text-faint)] mt-2">source: {source}</p>
      )}

      {!loading && !error && source && match?.status !== "unavailable" && (
        <div className="flex items-center gap-3 text-sm mt-2 bg-[var(--unmatched-bg)] border border-[var(--text-faint)]/30 rounded px-3 py-2.5">
          <span className="text-[var(--text)]">
            {results.length === 0
              ? "No results in the library catalog for this search."
              : "Not the right title? Confirm the library doesn't have this one."}
          </span>
          <button
            onClick={(e) => onMarkUnavailable(e.altKey)}
            className="ml-auto shrink-0 text-xs font-semibold px-3 py-1.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-contrast)]"
            title="Mark not in library (Option/Alt+click to advance — next season if TV, otherwise the next unmatched request)"
          >
            Mark not in library
          </button>
        </div>
      )}

      <SearchResultsTable results={results} onChoose={onChoose} chosenBibId={match?.bib_id} />
    </div>
  );
}
