import { useState } from "react";
import AppHeader from "./components/layout/AppHeader";
import MatchPanel from "./components/MatchPanel";
import QuickAddPanel from "./components/QuickAddPanel";
import MovieSearch from "./components/MovieSearch";
import RequestList from "./components/RequestList";
import { QuickAddProvider } from "./QuickAddContext";
import useIsMobile from "./hooks/useIsMobile";
import useRefreshSignal from "./hooks/useRefreshSignal";
import useRequests from "./hooks/useRequests";
import useRequestSelection from "./hooks/useRequestSelection";
import usePrefetchNextSearch from "./hooks/usePrefetchNextSearch";
import { getCollapseCollections, setCollapseCollections } from "./lib/collectionGrouping";
import { getDefaultBranch } from "./lib/defaultBranch";
import { getDefaultFilter, setDefaultFilter } from "./lib/defaultFilter";
import { filterByStatus, searchRequests } from "./lib/requestFilters";
import { useThemeMode } from "./theme/ThemeModeContext";

// Mock FE — for testing matching strategies against the real Overseerr +
// library APIs before this gets rebuilt as a Jellyfin plugin. Two-pane
// workspace layout at md+ (tablet/desktop) — request queue on the left, the
// active request's match panel sticky on the right — approved direction,
// see the UI-directions artifact this was picked from. Below md there's no
// room for a second column, so the match panel renders inline directly
// under the selected row instead (see useIsMobile/renderInlineMatchPanel).
// Structure (RequestList + MatchPanel, each owning their own concern) is
// meant to be portable to the eventual plugin either way.
//
// This is the composition root — same role as app/main.py on the backend:
// wire hooks (state/orchestration, see hooks/) into layout/view components
// (see components/layout/ and components/*), and stay small. Business logic
// lives in hooks/ and lib/, not here; this file should only ever grow by
// wiring in another hook or another prop, not by growing its own logic.
export default function App() {
  const [filter, setFilter] = useState(getDefaultFilter);
  const [search, setSearch] = useState("");
  // The active filter itself IS the persisted default — whatever you last
  // picked in the header dropdown is what loads next time, no separate
  // "remember to save this as default" step in Settings.
  function handleFilterChange(value) {
    setFilter(value);
    setDefaultFilter(value);
  }
  const [view, setView] = useState("requests");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [collapseCollections, setCollapseCollectionsState] = useState(getCollapseCollections);
  function handleCollapseCollectionsChange(enabled) {
    setCollapseCollectionsState(enabled);
    setCollapseCollections(enabled);
  }
  const [quickAddResult, setQuickAddResult] = useState(null);
  const [dvdCountRefreshKey, bumpDvdCount] = useRefreshSignal();
  const [failedQuickAddsRefreshKey, bumpFailedQuickAdds] = useRefreshSignal();
  const { mode, toggle: toggleTheme } = useThemeMode();
  const isMobile = useIsMobile();

  const { selected, setSelected, findNextUnmatched } = useRequestSelection();

  const { requests, setRequests, requestsSource, load } = useRequests(filter, {
    onStreamSettled: (seenIds) => {
      if (selected && !seenIds.has(selected.id)) setSelected(null);
    },
  });

  // Clicking the already-selected row again deselects it — most useful on
  // mobile, where the match panel expands inline under the row (see
  // renderInlineMatchPanel) and needs a way to collapse back without
  // picking a different request; harmless on desktop too, where it just
  // reverts the side panel to its "select a request" placeholder.
  //
  // The quick-add search only makes sense in the context of whatever request
  // you were matching when you spotted it — switching to a different request
  // (or deselecting) closes it rather than leaving a stale third column open.
  function selectRequest(request) {
    setSelected((prev) => (prev?.id === request.id ? null : request));
    setQuickAddResult(null);
  }

  const displayedRequests = filterByStatus(requests, filter, getDefaultBranch());
  const searchedRequests = searchRequests(displayedRequests, search);

  // Option/Alt+click on "Choose" (see MatchPanel/SearchResultsTable) saves
  // the match and jumps straight to the next request still needing one. No-op
  // if nothing after the current selection still needs a match.
  function advanceToNextUnmatched() {
    const next = findNextUnmatched(searchedRequests);
    if (next) selectRequest(next);
  }

  usePrefetchNextSearch(selected, searchedRequests, findNextUnmatched);

  function handleRefresh() {
    load(true);
    bumpDvdCount();
  }

  // Choosing/clearing a match updates just that one row in place — no
  // re-streaming the whole request list (that used to reset scroll position
  // and flash the loading state for an action that only changed one item).
  // Updates `selected` too, since MatchPanel reads request.match from that
  // snapshot, not from `requests` directly.
  // 3-arg so a single season's decision (TV) can update in place without
  // touching the other seasons — see MatchPanel.jsx's SeasonAccordion.
  // Movies (and any whole-item decision) use WHOLE_ITEM_SEASON, which also
  // keeps r.match in sync since that's still what RequestList/filters read
  // for movies.
  function updateLocalMatch(requestId, seasonNumber, match) {
    function patch(r) {
      if (r.id !== requestId) return r;
      const season_matches = { ...(r.season_matches || {}) };
      if (match === null) delete season_matches[seasonNumber];
      else season_matches[seasonNumber] = match;
      return { ...r, season_matches, match: seasonNumber === 0 ? match : r.match };
    }
    setRequests((prev) => (prev ? prev.map(patch) : prev));
    setSelected((prev) => (prev && prev.id === requestId ? patch(prev) : prev));
  }

  // Mobile (below the md breakpoint the grid switches at) has no "side" to
  // put the match panel in — there's no room for a second column at all, so
  // it renders directly under the selected row instead (see RequestList's
  // renderAfterRow) rather than in a separate, easy-to-scroll-past section
  // below the whole (potentially long) list.
  function renderInlineMatchPanel(request) {
    return (
      <div className="bg-[var(--surface)] p-5 border-t-2 border-[var(--rule-strong)]">
        <MatchPanel request={request} onMatchChange={updateLocalMatch} onAdvance={advanceToNextUnmatched} />
        {quickAddResult && (
          <div className="mt-4 pt-4 border-t border-[var(--rule)]">
            <QuickAddPanel
              libraryResult={quickAddResult}
              onClose={() => setQuickAddResult(null)}
              onAddFailed={bumpFailedQuickAdds}
            />
          </div>
        )}
      </div>
    );
  }

  // overflow-x-hidden deliberately NOT set on the root div below — it lives
  // on body (index.css) instead. Setting it here would make this div its
  // own scroll/clipping container, which breaks position:sticky on the
  // match panel further down (sticky needs to reference the real document
  // scroller; body/html overflow gets applied to the viewport itself rather
  // than creating a nested one, so it doesn't have this problem).
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <AppHeader
        filter={filter}
        onFilterChange={handleFilterChange}
        requestCount={displayedRequests?.length}
        search={search}
        onSearchChange={setSearch}
        requestsSource={requestsSource}
        dvdCountRefreshKey={dvdCountRefreshKey}
        failedQuickAddsRefreshKey={failedQuickAddsRefreshKey}
        onRefresh={handleRefresh}
        mode={mode}
        onToggleTheme={toggleTheme}
        settingsOpen={settingsOpen}
        onToggleSettings={() => setSettingsOpen((o) => !o)}
        onCloseSettings={() => setSettingsOpen(false)}
        view={view}
        onViewChange={setView}
        collapseCollections={collapseCollections}
        onCollapseCollectionsChange={handleCollapseCollectionsChange}
      />

      {view === "find" ? (
        <MovieSearch />
      ) : (
      <QuickAddProvider value={setQuickAddResult}>
        <div
          className={`grid grid-cols-1 gap-px bg-[var(--rule)] border-b border-[var(--rule)] ${
            quickAddResult ? "md:grid-cols-[1.1fr_1fr_1fr]" : "md:grid-cols-[1.1fr_1fr]"
          }`}
        >
          <div className="bg-[var(--surface)]">
            <RequestList
              key={String(collapseCollections)}
              requests={searchedRequests}
              selectedId={selected?.id}
              onSelect={selectRequest}
              searchQuery={search}
              onClearSearch={() => setSearch("")}
              renderAfterRow={isMobile ? renderInlineMatchPanel : undefined}
              collapseCollectionsByDefault={collapseCollections}
            />
          </div>
          {!isMobile && (
            <>
              <div className="bg-[var(--surface)] p-5 md:sticky md:top-0 md:self-start md:max-h-screen md:overflow-y-auto">
                {selected ? (
                  <MatchPanel request={selected} onMatchChange={updateLocalMatch} onAdvance={advanceToNextUnmatched} />
                ) : (
                  <p className="text-sm text-[var(--text-faint)]">Select a request to search the library.</p>
                )}
              </div>
              {quickAddResult && (
                <div className="bg-[var(--surface)] p-5 md:sticky md:top-0 md:self-start md:max-h-screen md:overflow-y-auto">
                  <QuickAddPanel
                    libraryResult={quickAddResult}
                    onClose={() => setQuickAddResult(null)}
                    onAddFailed={bumpFailedQuickAdds}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </QuickAddProvider>
      )}
    </div>
  );
}
