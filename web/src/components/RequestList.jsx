import { Fragment, useEffect, useState } from "react";
import { groupByCollection as buildGroups } from "../lib/collectionGrouping";
import { getDefaultBranch } from "../lib/defaultBranch";
import { STAGE_LABELS, requestStage } from "../lib/requestStage";

// One row per Overseerr request, styled as a scannable list (not a dense
// table) — status as a pill, the library match (if any) as a spine-label
// chip, mirroring how a call number reads on a DVD case. Deliberately
// dumb/presentational — all data fetching lives in App.jsx — so this maps
// cleanly onto a future plugin UI component that just receives props.
//
// `renderAfterRow(request)` is optional — App.jsx uses it on mobile (see
// useIsMobile) to embed the match panel directly under the selected row
// instead of in a separate side panel, since there's no "side" to put it in
// on a single-column layout. Desktop passes nothing, so this component's
// own behavior doesn't change there.
export default function RequestList({
  requests,
  selectedId,
  onSelect,
  searchQuery = "",
  onClearSearch,
  renderAfterRow,
  collapseCollectionsByDefault = false,
}) {
  const isSearching = searchQuery.trim().length > 0;
  const defaultBranch = getDefaultBranch();
  // Per-group open/closed choices made this session; anything not in here
  // follows the "collapse by default" setting.
  const [openOverrides, setOpenOverrides] = useState(() => new Map());
  const isOpen = (key) => openOverrides.get(key) ?? !collapseCollectionsByDefault;

  const entries = requests ? buildGroups(requests) : null;

  // Selecting a request inside a collapsed group (e.g. "next unmatched")
  // re-opens it — otherwise the selection would be hidden in the list.
  useEffect(() => {
    const group = entries?.find((e) => e.kind === "group" && e.requests.some((r) => r.id === selectedId));
    if (group) setOpenOverrides((prev) => (prev.get(group.key) === true ? prev : new Map(prev).set(group.key, true)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  function toggleGroup(key) {
    setOpenOverrides((prev) => new Map(prev).set(key, !(prev.get(key) ?? !collapseCollectionsByDefault)));
  }

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

  function renderRow(r) {
    const stage = requestStage(r, defaultBranch);
    const seasonProgress =
      r.type === "tv" && r.seasons?.length > 0 && stage.key !== "available"
        ? `${r.seasons.filter((n) => r.season_matches?.[n]?.status === "matched").length}/${r.seasons.length} seasons`
        : null;
    return (
      <Fragment key={r.id}>
        <div
          onClick={() => onSelect(r)}
          className={`flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-3 border-b border-[var(--rule)] cursor-pointer hover:bg-[var(--surface-raised)] ${
            selectedId === r.id ? "bg-[var(--surface-raised)] shadow-[inset_3px_0_0_var(--accent)]" : ""
          }`}
        >
          <div className="flex-1 basis-48 min-w-0">
            <div className="font-semibold text-sm truncate">
              {r.title}
              {r.tmdb?.release_date && (
                <span className="text-[var(--text-faint)] font-normal"> ({r.tmdb.release_date.slice(0, 4)})</span>
              )}
            </div>
            <div className="text-xs text-[var(--text-faint)] mt-0.5">
              {r.type}
              {r.tmdb?.director && <> · {r.tmdb.director}</>}
            </div>
          </div>

          {/* One pill for where the request is in the pipeline (Requested ->
              Matched -> Available, see lib/requestStage.js), plus the
              preferred-branch pickup pill. They sit right of the title
              when there's room; the title's flex-basis is what makes the
              row wrap them underneath once a narrow screen can't fit both. */}
          <div className="flex items-center gap-1.5">
            <span
              className={`inline-flex items-center justify-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap sm:min-w-[8.5rem] ${STAGE_PILL[stage.key]}`}
              title={r.match?.bib_title ? `${r.match.bib_title}${r.match.bib_subtitle ? `: ${r.match.bib_subtitle}` : ""}` : undefined}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current" />
              {STAGE_LABELS[stage.key]}
              {seasonProgress && <span className="mono font-normal"> · {seasonProgress}</span>}
            </span>
            {stage.atBranch && (
              <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full text-[var(--primary)] bg-[var(--pending-bg)] whitespace-nowrap">
                ★ at your branch
              </span>
            )}
          </div>
        </div>
        {selectedId === r.id && renderAfterRow?.(r)}
      </Fragment>
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
      {entries.map((e) =>
        e.kind === "row" ? (
          renderRow(e.request)
        ) : (
          <CollectionGroup
            key={`collection-${e.key}`}
            group={e}
            open={isOpen(e.key)}
            onToggle={() => toggleGroup(e.key)}
            renderRow={renderRow}
            defaultBranch={defaultBranch}
          />
        ),
      )}
    </div>
  );
}

const STAGE_PILL = {
  requested: "text-[var(--unmatched)] bg-[var(--unmatched-bg)]",
  matched: "text-[var(--pending)] bg-[var(--pending-bg)]",
  no_match: "text-[var(--accent)] bg-[var(--accent)]/10",
  available: "text-[var(--available)] bg-[var(--available-bg)]",
};
const STAGE_SEGMENT = {
  requested: "bg-[var(--unmatched-bg)] border-[var(--rule-strong)]",
  matched: "bg-[var(--pending)] border-[var(--pending)]",
  no_match: "bg-[var(--accent)] border-[var(--accent)]",
  available: "bg-[var(--available)] border-[var(--available)]",
};

// A collection's requested movies, pulled together into one bordered card:
// the collection name and a matched-progress bar. Rows inside are the same rows as the flat list.
function CollectionGroup({ group, open, onToggle, renderRow, defaultBranch }) {
  const stages = group.requests.map((r) => requestStage(r, defaultBranch).key);
  const summary = ["available", "matched", "no_match", "requested"]
    .map((key) => [stages.filter((k) => k === key).length, key])
    .filter(([n]) => n > 0)
    .map(([n, key]) => `${n} ${STAGE_LABELS[key].toLowerCase()}`)
    .join(" · ");
  return (
    <section className="mx-2 sm:mx-3.5 my-3.5 border border-[var(--rule-strong)] bg-[var(--surface)]">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={`w-full flex flex-wrap items-center gap-x-3.5 gap-y-1 text-left px-5 py-3 ${open ? "border-b border-[var(--rule)]" : ""}`}
      >
        <span className="flex-1 basis-40 min-w-0 text-lg leading-tight text-balance" style={{ fontFamily: "Georgia, 'Iowan Old Style', serif" }}>
          {group.name}
        </span>
        <span className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <span className="flex gap-[3px]" aria-hidden="true">
            {stages.map((key, i) => (
              <i key={group.requests[i].id} className={`w-3.5 h-1.5 border ${STAGE_SEGMENT[key]}`} />
            ))}
          </span>
          <span className="mono">{summary}</span>
        </span>
        <span aria-hidden="true" className={`mono text-[var(--text-faint)] text-xs transition-transform ${open ? "" : "-rotate-90"}`}>
          ▾
        </span>
      </button>
      {open && <div className="[&>*:last-child]:border-b-0">{group.requests.map(renderRow)}</div>}
    </section>
  );
}
