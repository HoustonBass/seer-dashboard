# CLAUDE.md

Context for any agent picking up this repo.

## What this is

Connects Overseerr (media requests) to a physical library account (Fulton County
Library System) so requested movies/shows can be checked against library
availability and held automatically. Eventual target is a Jellyfin plugin; near-term
target is standalone POSIX `sh` scripts, each testable on its own before anything
gets wired together.

## The four pieces, in order

1. `scripts/library/auth.sh` — **done.** Pure `curl`, no browser needed at
   runtime: scrapes a CSRF token from `GET /user/login`, POSTs
   `LIBRARY_USERNAME`/`LIBRARY_PASSWORD` with XHR-style headers, reads
   `bc_access_token`/`session_id` straight out of `Set-Cookie` on the 200
   JSON response. Prints `BC_ACCESS_TOKEN=`/`BC_SESSION_ID=` lines; other
   scripts do `eval "$(auth.sh)"` to pull them in. See
   `scripts/discovery/auth.md`.
2. `scripts/library/search.sh` — **done.** `GET
   gateway.bibliocommons.com/v2/libraries/fulcolibrary/bibs/search` with
   `X-Access-Token`/`X-Session-Id` headers. Takes a query + optional format
   filter, prints TSV ranked by a `matchScore` column (2 = exact `title:
   subtitle` match, 1 = exact bare-title match, 0 = other — see
   `scripts/discovery/search.md`) plus `publicationDate`/`callNumber`/`authors`
   columns, because title text alone is provably insufficient (e.g. "dune"
   returns three different films all titled bare "Dune" with no subtitle).
   Never auto-picks — always prints every candidate, ranked, for a human or
   caller to decide. `scripts/library/search_cached.py` is the same logic
   fronted by a SQLite cache (`scripts/lib/cache.py` → `data/cache.db`); the
   mock frontend (see below) uses this version. Note the 25-results-per-page
   cap on the API itself (use `page=N`, not a size param, if that ever
   matters).
3. `scripts/seerr/requests.sh` — **done.** Paginates `GET
   {SEERR_BASE_URL}/api/v1/request`, resolves each result's title via `GET
   /api/v1/movie/{tmdbId}` or `/api/v1/tv/{tmdbId}` (titles aren't in the
   request list itself), prints TSV. Auth is `X-Api-Key`. This API is
   publicly documented (Overseerr ships Swagger UI) — no reverse engineering
   needed, see `scripts/discovery/seerr.md` for status-code meanings.
4. **In progress: `app/` (Flask JSON API, Controller->Service->Repo) + `web/`
   (React/Vite/Tailwind).** A mock frontend for testing matching strategies
   interactively — see "Mock frontend" below for how it's structured and why.
   `scripts/library/hold.sh` (actually placing a hold) is not started —
   hold-endpoint discovery is deliberately parked, see below.

## The library has no public API — discovery process

Fulton County Library System's website is the only interface; there's no
documented API. Before writing any `scripts/library/*.sh` logic:

1. Drive the real site with Playwright (non-headless) using the credentials in
   `.env`.
2. Capture network traffic for the specific action (login, search, or hold).
3. Reduce the captured request to a minimal `curl` — strip tracking/analytics
   headers and any cookies/params that turn out not to matter, by trial and
   error.
4. Record the minimal curl + notes in `scripts/discovery/` (e.g. `auth.md`).
5. Port that curl into the actual `.sh` script.

Do not commit raw HAR captures or full cookie/session values to the repo —
redact before saving discovery notes. `.env` (not `.env.example`) holds real
credentials and must stay gitignored.

Treat the library's endpoints as unstable/undocumented: they can change without
notice, may be rate-limited or bot-protected, and reverse-engineered behavior
should be re-verified if a script starts failing rather than assumed broken on
this end.

Where useful, cross-check findings against public reverse-engineering of the
same platform (BiblioCommons is used by many library systems, so prior art
exists — e.g. `luscoma/bibliocommons-mcp`,
`williamjacksn/python-bibliocommons`) rather than assuming Fulton County is
unique. Don't blindly trust those sources either — verify against what our own
capture actually shows before relying on something we haven't tested
ourselves. See `scripts/discovery/auth.md`/`search.md`/`hold.md` for specific
places this already caught a discrepancy (e.g. the `accountId` derivation for
holds).

**Hold-endpoint discovery is intentionally deferred and NOT to be tested
live by an agent alone.** A wrong test call could place a real, physical hold
on the user's library card that we can't cancel remotely. The user will drive
a real browser session themselves and walk through the network tab together
when this work starts — don't fire speculative POST/DELETE requests at
`.../holds` against the live account outside of that session. Read-only
GETs (e.g. checking `/header/state` for account info) are fine.

### `data/` is a git submodule, not a gitignored scratch dir

`data/` (the 6 `*_cache.db`/`matches.db` SQLite files) is a submodule pointing
at this same repo's own `dbs` branch. That branch is deliberately kept to a
single, force-pushed commit — it's a data drop, not history worth preserving;
only add a second commit if a real point-in-time backup is actually wanted.
To refresh it: take a consistent snapshot with `sqlite3 <file> ".backup ..."`
(don't just `cp` a live db a running process is writing to), commit inside
the submodule checkout, `git commit --amend`, force-push `dbs`, then `git add
data` in the main repo to bump the submodule pointer. The containerized
deployment mounts this submodule checkout at `/data` with `DATA_DIR=/data`
(separately from `/config`'s `CONFIG_DIR`) — see the Dockerfile and
`app/lib/env.py`'s `data_dir()`. Local dev needs no extra env vars since
`data/` at repo root is already `data_dir()`'s no-CONFIG_DIR/no-DATA_DIR
default. `library_auth_cache` and `backend.log` are not part of this
submodule — they stay plain gitignored local-dev scratch files.

## Mock frontend (`app/` + `web/`)

Purpose: test matching strategies (the "which library item is this Overseerr
request actually referring to" problem — see `scripts/discovery/search.md`
and `hold.md`) against the *real* APIs interactively, before committing to a
Jellyfin plugin design. This is explicitly throwaway/prototype UI, not the
final product.

### Backend layering: Controller -> Service -> Repo

This was an explicit user architecture decision, not something to
"simplify" back into a flat `main.py`:

- **Controllers** (`app/controllers/*.py`) — Flask blueprints. Parse the HTTP
  request, call exactly one service method, `jsonify` the result. No business
  logic, no direct repo/DB access, no HTTP calls to external services.
- **Services** (`app/services/*.py`) — business logic, orchestrate repos
  (e.g. `RequestsService` joins `SeerrRepo` output with `MatchRepo` output).
  No HTTP framework code, no SQL, no `requests` calls of their own.
- **Repos** (`app/repos/*.py`) — **one per external system**: `SeerrRepo`
  (Overseerr), `LibraryRepo` (BiblioCommons), `TmdbRepo` (TMDB directly — see
  below), plus `MatchRepo` for our own persisted decisions (no external API,
  just SQLite). Each repo owns everything about that system: the actual HTTP
  calls, its own SQLite cache/db file, and (for the ones hitting real APIs)
  fetch deduplication via `SingleFlightCache`. If an IMDB connector is ever
  needed, it gets its own repo following this same shape — don't bolt it onto
  an existing one.
- `app/main.py` is the composition root only — instantiates repos, wires them
  into services, registers controller blueprints. It should stay small; if
  you're adding logic there, it probably belongs in a service or repo instead.

**`app/` is a native Python reimplementation of `scripts/*.sh`, not a wrapper
around them.** Explicit user decision: the `.sh`/`search_cached.py` scripts
stay as-is, standalone and separately testable from the CLI; `app/repos/`
independently re-implements the same auth/search/request-list logic in
Python. This means real duplication between e.g.
`scripts/library/auth.sh`/`search.sh` and `app/repos/library_repo.py` — that
is intentional, not drift to fix. If the reverse-engineered API behavior
changes, both sides need updating; check both.

- `app/repos/seerr_repo.py` — ports `scripts/seerr/requests.sh`. Own cache:
  `data/seerr_cache.db` (5 min TTL — request/media status changes often).
  Title resolution (one Overseerr call per request, since neither Overseerr
  nor TMDB expose a bulk lookup) runs via a `ThreadPoolExecutor` — this used
  to be sequential and took ~16s for ~250 requests; parallelized it's ~2-3s.
- `app/repos/library_repo.py` — ports `scripts/library/auth.sh` +
  `search.sh`. Own cache: `data/library_cache.db` (6h TTL). Auth is also
  cached (in-memory only, `AUTH_TTL_SECONDS` = 10 min, never written to
  disk since it's a live session credential) and shared across searches
  rather than re-logging in per search — self-heals on a 401/403 by forcing
  one re-login+retry rather than trusting the TTL guess exactly.
- `app/repos/tmdb_repo.py` — hits TMDB directly (not through Overseerr's
  proxy) for `release_date`/`overview`/`genres`/`director`/`cast`/`runtime` —
  data `SeerrRepo` doesn't capture (it only pulls the bare title out of
  Overseerr's TMDB passthrough). Needs `TMDB_API_KEY` in `.env` — **must be
  the "API Key (v3 auth)" field specifically** from
  themoviedb.org/settings/api, sent as an `api_key` query param; the v4
  "Read Access Token" (a JWT) and OMDb (a different, unrelated service at
  omdbapi.com) will both look plausible but fail — confirm with a real call
  before assuming a new key is wired correctly, don't just trust the format.
  Own cache: `data/tmdb_cache.db` (24h TTL). `get(media_type, tmdb_id)` /
  `get_many(items)` where `media_type` is `"movie"` or `"tv"`, matching
  Overseerr's own values. `get_many` parallelizes via `ThreadPoolExecutor`
  (same reasoning as `SeerrRepo`'s title lookups — no bulk endpoint exists)
  and isolates per-item failures (returns `None` for that item, doesn't fail
  the batch) since TMDB rate limits or a bad id shouldn't break the whole
  request list. Wired into `RequestsService` — every row from `/api/requests`
  has a `tmdb` field (the record, or `None` on a failed lookup) alongside
  `match`. Rendered in `RequestList` (release year + director, inline) and
  `MatchPanel` (poster/genres/overview) on the frontend.

### `/api/requests` streams NDJSON — don't revert to one big JSON array

`RequestsService.stream_requests()` (not `get_requests()`, which still
exists but blocks until the whole batch resolves — kept for callers that
want a single response) yields `(row, source)` pairs as each request's title
+ TMDB data resolves, using `as_completed()` instead of `pool.map()` so rows
arrive in *completion* order, not submission order. The controller
(`app/controllers/requests_controller.py`) streams this as newline-delimited
JSON (`application/x-ndjson`, one `{"row": ..., "source": ...}` per line) via
a Flask generator response — this was a deliberate user ask ("stream results
instead of waiting for alllll of them"), not incidental. Before this, a cold
cache meant the UI showed nothing until all ~250 requests finished
resolving; now the first rows appear within ~1s and the list fills in.

Consequences worth knowing before touching this:
- **Bypasses `SingleFlightCache` entirely.** A stream can't be replayed to a
  second concurrent caller mid-flight the way a completed value can — two
  concurrent live fetches for the same filter will each just do their own
  work. Accepted tradeoff for a single-user tool; revisit if this ever needs
  to support concurrent users.
- **Cache-hit rows already carry their `tmdb` data** (baked in when they
  were cached from a prior live fetch) and are replayed directly with no
  re-fetch — don't add a redundant `tmdb_repo.get()` call in the cache-hit
  path, that data's already there.
- **Rows arrive out of Overseerr's "most recently added" order** (since
  `as_completed()` yields whichever row's title+TMDB resolve fastest, not
  request order) — `web/src/App.jsx`'s `load()` re-sorts by `id` descending
  on every incremental update to compensate. If this ever moves off `id` as
  the sort key, keep that re-sort in mind or the list will look shuffled.
- Frontend reads the stream via `res.body.getReader()` in
  `web/src/lib/api.js`'s `streamRequests()` — a plain NDJSON line-buffer
  parser, not `EventSource`/SSE (which can't do the query-param-based GET we
  already use as cleanly, and NDJSON needed no new dependency).
- `app/repos/match_repo.py` — persistence for **chosen matches**
  (`data/matches.db`). Separate from the two caches above: those are
  disposable and safe to delete/rebuild from the API; `matches.db` holds
  actual decisions made while testing and should be treated as durable state,
  not a cache.
- `app/lib/singleflight.py` — `SingleFlightCache`: ensures concurrent callers
  for the same cache key (e.g. two requests for `filter=all` at once) share
  one in-flight fetch instead of each re-fetching. Both `SeerrRepo` and
  `LibraryRepo` use this. **Gotcha already hit and fixed**: a shared
  `sqlite3.Connection` is NOT safe for concurrent use from multiple threads
  even with `check_same_thread=False` (that flag only disables Python's
  guard, not actual thread-safety) — this surfaced as
  `sqlite3.InterfaceError: bad parameter or other API misuse` under real
  concurrent load. Every repo now has a `self._db_lock =
  threading.Lock()` guarding all `self._conn` access. If you add a new repo
  or a new query method, use this lock too — don't assume a single
  `sqlite3.connect(..., check_same_thread=False)` is enough on its own.
- `app/lib/env.py` — loads `.env` into `os.environ` (Python equivalent of
  `scripts/lib/env.sh`), since `app/` doesn't shell out anymore and so
  doesn't get `.env` sourced for free.
- `app/lib/feature_switch.py` — `REGISTRY` is the single source of truth for
  every feature switch; `delay_switch(env_var)` sleeps if the given env var
  is set to a number (lets a repo's live-fetch path be forced slow on demand
  so single-flight/concurrency behavior can be reproduced reliably instead of
  needing a naturally slow call to create a wide enough race window).
  `list_switches()`/`set_switch()` back the `/api/settings` endpoint
  (`app/controllers/settings_controller.py` +
  `app/services/settings_service.py`) — **adding a switch means adding a
  `REGISTRY` entry, nothing else; it shows up in the settings UI
  automatically.** Switches are process-only (mutate `os.environ` at
  runtime, never persisted) — that's deliberate, not a gap: these are
  debug/test knobs, resetting to off on restart is correct.
- `web/` — React + Vite + Tailwind v4. Components are scoped by concern
  (`RequestList`, `MatchPanel`, `SearchResultsTable`, `SettingsPopover`,
  `Toggle`) specifically so that when this gets rewritten in C# for the real
  plugin, each component can be ported one at a time rather than untangling
  a monolith — explicit user decision, not incidental structure. Keep that
  shape when extending this: one concern per component, dumb/presentational
  components fed by props from a container (currently `App.jsx`), not
  fetching their own data ad hoc.
- **Theming**: `web/src/theme/ThemeModeContext.jsx` — light/dark, defaults to
  `prefers-color-scheme`, manually overridable and persisted to
  `localStorage` (key `seerr-dashboard:theme-mode`), sets a `data-theme`
  attribute on `<html>`. Colors are CSS custom properties in
  `web/src/index.css` (`:root`, overridden under
  `@media (prefers-color-scheme: dark)` **and** under
  `:root[data-theme="dark"]`/`[data-theme="light"]` so the manual toggle wins
  over the OS preference in both directions). Components consume tokens via
  Tailwind arbitrary values (`bg-[var(--surface)]`, `text-[var(--accent)]`,
  etc.) rather than Tailwind's `dark:` variant, specifically because theme
  here is a manual attribute toggle, not just a media query. The palette
  itself (library card-catalog aesthetic — spine-label chips for call
  numbers, pills for availability/status, serif headings) was picked from a
  UI-directions mockup the user approved ("two pane is a good approach") —
  don't casually restyle away from it without checking first, it was a
  deliberate choice, not a placeholder.
- Pattern for `SettingsPopover.jsx`/`Toggle.jsx` was adapted from
  `/Users/Shared/repos/claude/todo`'s `SettingsPopover`/`Header` — but
  **without** that repo's `@one-thd/sui-atomic-components` dependency (a
  Home Depot-internal package, not available/appropriate here); `Toggle.jsx`
  is hand-rolled instead.
- `web/src/lib/defaultFilter.js` — separate from feature switches:
  localStorage-only UI preference ("which filter is selected on page load"),
  not a backend concern. Rendered inside `SettingsPopover` alongside feature
  switches (same popover, different section) since that's where UI
  preferences live, but don't confuse the two when extending either —
  feature switches round-trip through `/api/settings`, this doesn't.
- **"Matched" state is always green (`--available` token), everywhere** —
  the request-list chip, the "Chosen" search-result button, the MatchPanel
  banner. Explicit user ask ("I want to be proud I've found the match"), not
  incidental — don't drift this back to a neutral/grey "just metadata" style.
- **Cover art**: `LibraryRepo` extracts `briefInfo.jacket.medium` (falling
  back to `.small`) as `jacket_url` per search result — BiblioCommons/
  Syndetics cover images, not from TMDB. Often `None` (sparse catalog
  records don't all have jacket art) — `SearchResultsTable` renders a dashed
  placeholder box in that case rather than nothing, so rows stay aligned.
  Persisted in the `bibs` cache table; existing `data/library_cache.db`
  files get migrated with an `ALTER TABLE` on open (see `LibraryRepo._connect`)
  rather than needing a manual delete. `record_url`
  (`{base_url}/v2/record/{bib_id}`) rides the same migration path — the
  public record detail page on the library's own site, no auth needed to
  view, linked from each search result's title so "see the real listing"
  is one click. Cache staleness note: rows cached before either column
  existed replay as `None` for it until that (query, format) naturally
  re-fetches — not a bug, just how the migration interacts with already-
  cached data; `--refresh`/force-refresh gets fresh values immediately.
  `jacket_url_large` (Syndetics `.large`, same migration path) is a
  separate, bigger image used only by the hover-zoom preview — using
  `jacket_url` (`.medium`) there too looked visibly blurry once scaled up;
  confirmed `.large` is a real ~3x bigger file, not just a same-size
  re-encode. Same split for the TMDB poster: `MatchPanel` renders `w92` but
  zooms to `w500` (`HoverZoomImage`'s `src` vs `zoomSrc` props) — don't
  collapse these back to one size "to simplify," the whole point was fixing
  visibly low-quality zoomed images.
- **`MatchPanel` auto-searches on selection** — same call the Search button
  makes (respects cache, only goes live if actually uncached), not a
  separate "peek cache" endpoint (tried that first, unnecessarily complex —
  reverted; the actual ask was just "always search," cached or not).
- **`filter` dropdown**: "unmatched"/"matched" are client-side (App.jsx's
  `OVERSEERR_FILTERS` set decides what's a real Overseerr filter vs. what
  needs `"all"` as the backend query + local `.filter()`). "unmatched"
  additionally excludes already-`AVAILABLE` requests — nothing to hunt down
  at the library if Overseerr already has it. Default filter is not
  hardcoded; it reads from `defaultFilter.js` (see above).
- **Right panel (`MatchPanel`) is sticky** (`lg:sticky lg:top-0
  lg:self-start`, App.jsx) — explicit user ask so switching between requests
  in a long list doesn't require re-scrolling to see it.

### A note on live-reload disruption during backend edits

Flask's `debug=True` reloader watches every `.py` file under `app/` and
restarts the whole process on any change. If the user has their own instance
running while you're editing `app/repos/`, `app/services/`, etc., **every
save bounces their live server** — this looks like connection-refused/502
errors on their end that have nothing to do with the code being wrong. This
is separate from (and in addition to) the "don't `pkill`, use `APP_PORT` for
your own testing" rule elsewhere in this file: even without ever touching
their process directly, editing backend source while it's running under
`debug=True` will restart it out from under them. Nothing to fix
code-side — just don't be surprised by a transient error report that
coincides with an edit, and mention the reload as the likely cause before
assuming a real regression.
- `web/vite.config.js` proxies `/api/*` to `:5001` in dev — components call
  `fetch("/api/...")` with no hardcoded host (see `web/src/lib/api.js`).
- `web/.npmrc` pins `registry.npmjs.org` — **required**, don't remove it. This
  machine's global npm/pnpm config points at an internal-only Artifactory
  registry that doesn't mirror public packages; without this override,
  `pnpm install`/`pnpm add` 404 on everything. If you add packages from a
  fresh shell and hit `ERR_PNPM_FETCH_404`, this is why — check the override
  is actually in `web/.npmrc`, not just passed as a one-off flag.

Run: `python3 -m app.main` (backend — **note: `-m app.main`, not `python3
app/main.py`**, since `app` is now a real package and needs repo root on
`sys.path`) and `cd web && pnpm dev` (frontend), two terminals. Set
`APP_PORT` to run a second instance on a different port instead of killing
one that's already running — e.g. `APP_PORT=5099 python3 -m app.main` for
ad hoc testing while a real session is up on `:5001`. Don't `pkill -f
app.main` as a matter of course; that kills every instance including the
user's.

### Tests (`tests/`)

`python3 -m pip install -r app/requirements-dev.txt && python3 -m pytest`
(needs `pytest.ini`'s `pythonpath = .` to resolve `from app...` imports — run
from repo root). All mocked — patch `app.repos.seerr_repo.http.get` /
`app.repos.library_repo.http.get` (and `.Session` for auth), never hit the
real network or need real credentials. `test_seerr_repo.py`'s and
`test_library_repo.py`'s concurrency tests are regression tests for the
sqlite3 thread-safety bug above — if you touch `_db_lock` or the caching
logic, run these first. When adding a new repo method or service, add tests
in the corresponding `tests/test_*.py` rather than only hand-verifying via
`curl`/browser.

## Conventions

- Scripts are POSIX `sh`, not bash — no bashisms (`[[ ]]`, arrays, `local`,
  etc.). User explicitly wants portability/simplicity over bash features.
- Every script sources `scripts/lib/env.sh` first to load `.env` from repo root.
- One script per concern (auth / search / seerr-pull / hold) — no monolith
  script. This mirrors how the pieces will later be re-assembled into a Jellyfin
  plugin, where each concern maps to a separate module/call.
- Prefer scripts that are runnable and testable standalone from the CLI over
  anything requiring the full pipeline to be wired up first.
- `scripts/discovery/` is documentation of API reverse-engineering, not
  executable code — don't try to run anything in there.
- `app/` follows Controller -> Service -> Repo layering (see "Mock frontend"
  below) — don't put business logic in a controller or HTTP/SQL in a service.
  New logic that touches an external system belongs in that system's repo.
- New behavior in `app/` gets a test in `tests/` (mocked HTTP, see "Tests"
  below) — this isn't optional busywork, it's how the sqlite3 thread-safety
  bug below was caught and how it'll stay caught.

## Known unknowns (do not assume — ask or investigate)

- Exact library hold endpoint payload shape (`accountId` derivation
  specifically has conflicting info between public prior art and our own
  capture) — unknown until live discovery work is done, see
  `scripts/discovery/hold.md`.
- Whether Overseerr requests need any additional Overseerr-side auth beyond
  `SEERR_API_KEY` (e.g. per-user auth) — not yet confirmed.
- Full matching-strategy design (task 4) is still exploratory — the mock
  frontend exists to figure this out interactively, not to ship a finished
  algorithm. Known signals so far: exact `title: subtitle` text match (cheap,
  implemented), and a per-candidate "Originally released as a motion picture
  in `<year>`" note available via `GET
  gateway.bibliocommons.com/v2/libraries/fulcolibrary/catalogBibs/{bibId}`
  (`entities.catalogBibs.{bibId}.fields[] where category=="NOTES"`) that can
  be regexed and compared numerically against Overseerr's `releaseDate` year
  — not yet wired into any script, would need `catalogBibs` fetched per
  ambiguous candidate (costly to do for every result, fine for a
  human-triggered "disambiguate this one" action).

## Environment gotchas (this machine specifically)

- `zsh` treats `$path` (lowercase) as a synonym for `$PATH` — a shell loop
  variable named `path` silently breaks command resolution for the rest of
  that scope (symptom: `command not found: curl` mid-script for no apparent
  reason). Don't name loop variables `path`.
- Global npm/pnpm config here points at an internal Artifactory registry with
  no public package mirror — see the `web/.npmrc` note above for the fix
  pattern (project-local `.npmrc` pointing at `registry.npmjs.org`, or
  `npm_config_registry=https://registry.npmjs.org` as a one-off env override).
