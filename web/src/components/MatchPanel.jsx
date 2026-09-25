import { useState } from "react";
import { WHOLE_ITEM_SEASON, clearMatch, markUnavailable, placeHold, saveMatch } from "../lib/api";
import HoverZoomImage from "./HoverZoomImage";
import MatchSearchBox from "./MatchSearchBox";

// Detail/action panel for one selected Overseerr request, styled as a
// library "catalog slip". Movies get one MatchSearchBox for the whole item;
// TV shows get a per-season accordion (see SeasonAccordion below) — the
// library has one DVD per season, not per show, so "match" has to be
// per-(request, season) for TV. See CLAUDE.md's TV-matching section.
export default function MatchPanel({ request, onMatchChange, onAdvance }) {
  const isTv = request.type === "tv" && request.seasons?.length > 0;

  // `advance` comes from Option/Alt+click on the "Choose" button (see
  // SearchResultsTable) — saves the match same as a plain click, then jumps
  // to the next request that still needs one (App.jsx's advanceToNextUnmatched).
  async function handleChoose(seasonNumber, candidate, advance) {
    await saveMatch({
      request_id: request.id,
      season_number: seasonNumber,
      tmdb_id: request.tmdb_id,
      media_type: request.type,
      seerr_title: request.title,
      bib_id: candidate.bib_id,
      bib_title: candidate.title,
      bib_subtitle: candidate.subtitle,
      availability_status: candidate.availability_status,
    });
    onMatchChange(request.id, seasonNumber, {
      status: "matched",
      bib_id: candidate.bib_id,
      bib_title: candidate.title,
      bib_subtitle: candidate.subtitle,
      availability_status: candidate.availability_status,
      hold_id: null,
    });
    if (advance) onAdvance?.();
  }

  // Places a REAL hold on the live account — see app/repos/library_repo.py's
  // place_hold / scripts/discovery/hold.md. Only offered by MatchSearchBox
  // when the matched item's last-known availability wasn't AVAILABLE and no
  // hold has been placed yet for this match.
  async function handlePlaceHold(seasonNumber, match) {
    const result = await placeHold({ request_id: request.id, season_number: seasonNumber, bib_id: match.bib_id });
    onMatchChange(request.id, seasonNumber, { ...match, hold_id: result.hold_id });
    return result;
  }

  async function handleMarkUnavailable(seasonNumber) {
    await markUnavailable({
      request_id: request.id,
      season_number: seasonNumber,
      tmdb_id: request.tmdb_id,
      media_type: request.type,
      seerr_title: request.title,
    });
    onMatchChange(request.id, seasonNumber, { status: "unavailable", bib_id: null, bib_title: null, bib_subtitle: null });
  }

  // Bulk "give up on whatever's left" action for TV (see SeasonAccordion's
  // header button) — marks every still-undecided requested season
  // unavailable in one click instead of opening each one individually.
  // Reuses handleMarkUnavailable per season (same persistence + local-state
  // update path as the single-season button), fired concurrently since each
  // season is an independent (request_id, season_number) row.
  async function handleMarkAllUnavailable(seasonNumbers) {
    await Promise.all(seasonNumbers.map((seasonNumber) => handleMarkUnavailable(seasonNumber)));
  }

  async function handleClear(seasonNumber) {
    await clearMatch(request.id, seasonNumber === WHOLE_ITEM_SEASON ? undefined : seasonNumber);
    onMatchChange(request.id, seasonNumber, null);
  }

  return (
    <div className="rounded border border-[var(--rule)] bg-[var(--surface-raised)] p-5">
      <h2 className="font-serif text-xl" style={{ fontFamily: "Georgia, 'Iowan Old Style', serif" }}>
        {request.title}
      </h2>
      <p className="mono text-xs text-[var(--text-muted)] mt-0.5">
        request #{request.id} · tmdbId {request.tmdb_id} · {request.type}
        {isTv && ` · ${request.seasons.length} season${request.seasons.length === 1 ? "" : "s"} requested`}
      </p>

      {request.tmdb && (
        <div className="mt-3 flex gap-3 text-sm">
          {request.tmdb.poster_path && (
            <HoverZoomImage
              src={`https://image.tmdb.org/t/p/w92${request.tmdb.poster_path}`}
              zoomSrc={`https://image.tmdb.org/t/p/w500${request.tmdb.poster_path}`}
              zoomWidth={320}
              className="w-14 aspect-[2/3] rounded border border-[var(--rule)] shrink-0 cursor-zoom-in"
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

      <div className="mt-4">
        {isTv ? (
          <SeasonAccordion
            request={request}
            onChoose={handleChoose}
            onMarkUnavailable={handleMarkUnavailable}
            onMarkAllUnavailable={handleMarkAllUnavailable}
            onClear={handleClear}
            onPlaceHold={handlePlaceHold}
          />
        ) : (
          <MatchSearchBox
            key={request.id}
            defaultQuery={request.title}
            match={request.match}
            autoSearchKey={request.id}
            onChoose={(candidate, advance) => handleChoose(WHOLE_ITEM_SEASON, candidate, advance)}
            onMarkUnavailable={() => handleMarkUnavailable(WHOLE_ITEM_SEASON)}
            onClear={() => handleClear(WHOLE_ITEM_SEASON)}
            onPlaceHold={(match) => handlePlaceHold(WHOLE_ITEM_SEASON, match)}
          />
        )}
      </div>
    </div>
  );
}

function seasonStatusPill(match) {
  if (match?.status === "matched") {
    return (
      <span className="mono inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--available)] bg-[var(--available-bg)] whitespace-nowrap">
        <span className="w-1.5 h-1.5 rounded-full bg-current" />
        {match.bib_title}
        {match.bib_subtitle ? `: ${match.bib_subtitle}` : ""}
      </span>
    );
  }
  if (match?.status === "unavailable") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--accent)] bg-[var(--accent)]/10 whitespace-nowrap">
        <span className="w-1.5 h-1.5 rounded-full bg-current" />
        not in library
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--unmatched)] bg-[var(--unmatched-bg)] whitespace-nowrap">
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      unmatched
    </span>
  );
}

// One accordion row per *requested* season (Overseerr's own seasons array —
// not every season the show has, see CLAUDE.md). Only the expanded season's
// MatchSearchBox is mounted, so selecting a show doesn't fire off N
// concurrent library searches for every season at once — just the one
// you're actually looking at.
function SeasonAccordion({ request, onChoose, onMarkUnavailable, onMarkAllUnavailable, onClear, onPlaceHold }) {
  const [expanded, setExpanded] = useState(null);
  const [markingAll, setMarkingAll] = useState(false);
  const [markAllError, setMarkAllError] = useState(null);
  const seasons = [...request.seasons].sort((a, b) => a - b);
  const matchedCount = seasons.filter((s) => request.season_matches?.[s]?.status === "matched").length;
  // "Unset" = no decision at all yet — neither matched nor already confirmed
  // unavailable (re-marking those would be a no-op but there's no reason to
  // re-send them).
  const unsetSeasons = seasons.filter((s) => !request.season_matches?.[s]);

  async function handleMarkAllUnavailable() {
    setMarkingAll(true);
    setMarkAllError(null);
    try {
      await onMarkAllUnavailable(unsetSeasons);
    } catch (e) {
      setMarkAllError(e.message);
    } finally {
      setMarkingAll(false);
    }
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-3 px-3 py-2.5 bg-[var(--surface)] border border-[var(--rule)] rounded text-sm">
        <span className="whitespace-nowrap">
          {matchedCount} of {seasons.length} requested season{seasons.length === 1 ? "" : "s"} matched
        </span>
        <div className="flex-1 h-1.5 rounded-full bg-[var(--rule-strong)] overflow-hidden">
          <div
            className="h-full bg-[var(--available)] rounded-full"
            style={{ width: `${seasons.length ? (matchedCount / seasons.length) * 100 : 0}%` }}
          />
        </div>
        {unsetSeasons.length > 0 && (
          <button
            onClick={handleMarkAllUnavailable}
            disabled={markingAll}
            title={`Mark all ${unsetSeasons.length} undecided season${unsetSeasons.length === 1 ? "" : "s"} not in library`}
            className="shrink-0 text-xs font-semibold px-3 py-1.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-contrast)] disabled:opacity-50 whitespace-nowrap"
          >
            {markingAll ? "Marking…" : `Mark remaining ${unsetSeasons.length} not in library`}
          </button>
        )}
      </div>
      {markAllError && <p className="text-xs text-[var(--accent)] mb-3">Failed to mark all — {markAllError}.</p>}

      {seasons.map((seasonNumber) => {
        const match = request.season_matches?.[seasonNumber] ?? null;
        const isOpen = expanded === seasonNumber;
        return (
          // Plain button + conditional div, not <details>/<summary> — a
          // native <details>'s open state is uncontrolled DOM state that
          // only that one element's browser-driven toggle updates, so
          // "close the others when one opens" required React to fight the
          // DOM after the fact and was unreliable. Driving isOpen from a
          // single `expanded` state value and nothing else makes exactly
          // one section open, deterministically, every time.
          <div key={seasonNumber} className="border-b border-[var(--rule)] last:border-none">
            <button
              type="button"
              onClick={() => setExpanded(isOpen ? null : seasonNumber)}
              className="w-full flex items-center gap-3 py-2.5 cursor-pointer hover:bg-[var(--surface)] text-left"
            >
              <span className="mono text-xs text-[var(--text-muted)] w-8">S{seasonNumber}</span>
              <span className="text-sm flex-1">Season {seasonNumber}</span>
              {seasonStatusPill(match)}
              <span className={`mono text-xs text-[var(--text-faint)] transition-transform ${isOpen ? "rotate-90 text-[var(--accent)]" : ""}`}>
                ▸
              </span>
            </button>
            {isOpen && (
              <div className="pb-4 pl-11">
                <MatchSearchBox
                  key={`${request.id}-${seasonNumber}`}
                  defaultQuery={`${request.title} season ${seasonNumber}`}
                  match={match}
                  autoSearchKey={`${request.id}-${seasonNumber}`}
                  onChoose={(candidate, advance) => onChoose(seasonNumber, candidate, advance)}
                  onMarkUnavailable={() => onMarkUnavailable(seasonNumber)}
                  onClear={() => onClear(seasonNumber)}
                  onPlaceHold={(m) => onPlaceHold(seasonNumber, m)}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
