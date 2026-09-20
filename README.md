# seerr-dashboard

Glue between an Overseerr instance and a physical public library account (Fulton
County Library System), so requested movies/shows can be cross-referenced against
what's actually available to place on hold at the library — and eventually holds can
be placed automatically.

End goal: a Jellyfin plugin. For now, everything is built and tested as standalone
shell scripts so each piece can be verified independently before it gets wired into
a plugin.

## Why

Overseerr tracks what people requested. The library has its own catalog, its own
search, and its own hold system, entirely separate from Overseerr/Jellyfin. There's
no API integration between them. This project builds one.

## Pieces (in build order)

1. **Library auth** (`scripts/library/auth.sh`, done) — logs into the Fulton
   County Library (BiblioCommons) site with `LIBRARY_USERNAME` /
   `LIBRARY_PASSWORD`, prints `BC_ACCESS_TOKEN` / `BC_SESSION_ID`.
2. **Library search** (`scripts/library/search.sh`, done) — given a title (and
   optional format filter), hits the library's catalog search API and returns
   candidate matches as TSV: bib id, title, subtitle, format, availability.
3. **Seerr data pull** (`scripts/seerr/requests.sh`, done) — calls the
   Overseerr API to list requested movies/shows with resolved titles and
   status, as TSV.
4. **Combine + act** (`app/` + `web/`, in progress) — a mock frontend for
   testing matching strategies against the real APIs before committing to a
   Jellyfin plugin design. See "Mock frontend" below. Hold placement isn't
   wired in yet — hold-endpoint discovery is deliberately deferred, see
   `scripts/discovery/hold.md`.

The library has no public API. Auth/search were reverse-engineered by driving
the real site with Playwright and reading network traffic, then paring each
captured request down to a minimal curl — and cross-checked against public
BiblioCommons client projects for confidence. See `scripts/discovery/` for the
full findings and methodology. The hold endpoint is scoped from public prior
art only so far; live verification is intentionally deferred until it can be
done with the user driving the browser directly, since a wrong test call could
place a real, uncancelable-by-us hold.

## Layout

```
scripts/
  lib/         shared helpers: env.sh (env loading), cache.py (SQLite cache API)
  library/     auth.sh, search.sh, search_cached.py (done); hold.sh (not started)
  seerr/       requests.sh — pulls requested media + titles from Overseerr
  discovery/   findings, minimal curl commands, and Playwright capture tooling
               used to reverse-engineer the library API (auth.md, search.md,
               hold.md, seerr.md, capture-login.mjs)
data/
  cache.db           scripts/library/search_cached.py's cache (gitignored)
  seerr_cache.db      SeerrRepo's own cache (gitignored)
  library_cache.db    LibraryRepo's own cache (gitignored)
  matches.db          chosen request<->library matches (gitignored, but durable —
                       not a cache, don't casually delete)
app/
  main.py            composition root: wires repos -> services -> controllers
  controllers/       Flask blueprints — HTTP in, service call, JSON out. No business logic.
  services/          business logic, orchestrates repos. No HTTP, no SQL.
  repos/             one per external system (seerr_repo.py, library_repo.py),
                     plus match_repo.py for our own persisted decisions. Each repo
                     owns its API calls, its own SQLite cache/db, and (for the two
                     that hit real APIs) single-flight fetch-locking.
  lib/               env.py (loads .env), singleflight.py (cache concurrency
                     control), testing.py (artificial-delay switch for tests)
web/
  React + Vite + Tailwind mock frontend — see "Mock frontend" below
tests/
  pytest suite for app/ — mocked HTTP, no real credentials or network needed
```

`app/` is a **native Python reimplementation** of the same Overseerr/library API
calls `scripts/` makes — not a wrapper that shells out to those scripts. Both
exist deliberately: `scripts/*.sh` stay as standalone, individually-runnable
CLI reference tools; `app/repos/` is the product-facing implementation with
proper caching/concurrency control. Expect some duplicated logic between the
two — that's intentional, not drift to "fix".

## Setup

```sh
cp .env.example .env
# fill in LIBRARY_USERNAME, LIBRARY_PASSWORD, LIBRARY_BASE_URL,
# SEERR_BASE_URL, SEERR_API_KEY
```

All scripts are POSIX `sh` (not bash-specific) so they run anywhere without
assumptions about the shell, and can be run manually one at a time while each piece
is being built.

## Mock frontend

A throwaway UI for testing matching strategies interactively before this
becomes a real Jellyfin plugin — a Flask JSON API backend (Python + SQLite, so
state survives restarts trivially) and a React + Vite + Tailwind frontend.
Components are named/scoped by concern (`RequestList`, `MatchPanel`,
`SearchResultsTable`) so that when this gets rewritten in C#, each one can be
ported one at a time rather than untangling a monolith. Backend follows
Controller -> Service -> Repo layering — see Layout above.

Run both (two terminals):

```sh
python3 -m app.main          # backend on :5001 (or $APP_PORT if set)
cd web && pnpm install && pnpm dev   # frontend on :5173 (proxies /api to :5001)
```

Use `APP_PORT` to run a second instance on a different port — handy for
testing/experimenting without taking down one you're actively using:

```sh
APP_PORT=5099 python3 -m app.main
```

`/api/requests` and `/api/search` both return `{"source": "cache"|"live",
"results": [...]}` so it's visible whether a given response came from a
repo's SQLite cache or an actual API call — the FE shows this next to each
list. Concurrent requests for the same thing (same filter, or same
query+format) share one in-flight fetch rather than each re-fetching — see
`app/lib/singleflight.py`.

### UI

Two-pane workspace (request queue left, active request's match panel right),
styled around a library card-catalog look — call numbers as spine-label
chips, availability/status as pills, a serif heading. Light/dark theme
follows your OS preference by default, overridable via the toggle in the
header (persisted per-browser). The gear icon opens a settings panel listing
every feature switch in `app/lib/feature_switch.py`'s `REGISTRY` — flipping
one mutates the backend process's env vars live, no restart needed.

`web/.npmrc` pins the public npm registry for this project — the machine's
global npm config here points at an internal-only registry that doesn't mirror
public packages, so without it `pnpm install` 404s on everything.

### Testing

```sh
python3 -m pip install -r app/requirements-dev.txt
python3 -m pytest
```

All mocked (no real credentials, no network) — covers `SingleFlightCache`
concurrency, both repos' caching/ranking/auth logic, `MatchRepo` persistence,
and service-layer orchestration. `SEERR_TEST_FETCH_DELAY_SECONDS` /
`LIBRARY_TEST_FETCH_DELAY_SECONDS` env vars (see `app/lib/feature_switch.py`) inject
an artificial delay into a repo's live-fetch path, so concurrency races can be
reproduced reliably in a test instead of needing a naturally slow call.

## Status

- `scripts/library/auth.sh` — working, pure curl, no browser needed at runtime.
- `scripts/library/search.sh` — working, returns title/format/availability as TSV,
  ranked by exact-title-match score (see `scripts/discovery/search.md`).
- `scripts/library/search_cached.py` — same search, backed by a SQLite cache
  (`scripts/lib/cache.py`, `data/cache.db`) so repeated lookups don't re-hit
  the API; `--refresh` bypasses it, `--ttl` controls freshness (default 6h).
- `scripts/seerr/requests.sh` — working, returns title/status/requester as TSV
  for all Overseerr requests (paginated, resolves titles via TMDB passthrough).
- Mock frontend (`app/`, `web/`) — working end-to-end: two-pane UI (light/dark
  theme, feature-switch settings panel), lists Overseerr requests (cached,
  single-flight, auth-token-cached + parallelized title lookups — first cold
  load of ~250 requests takes ~2-3s, was ~16s before parallelizing), searches
  the library per-request, lets you pick a candidate and persists the choice
  (`data/matches.db`) across restarts.
- `app/repos/tmdb_repo.py` — hits TMDB directly for richer per-title data
  (release year, overview, genres, director/cast, runtime, poster) that
  Overseerr's own title lookup doesn't expose. Needs `TMDB_API_KEY` in
  `.env` (the v3 "API Key" specifically, not the v4 Read Access Token or
  OMDb). Wired into `RequestsService` and rendered in both `RequestList`
  and `MatchPanel`.
- 50 passing tests in `tests/` (all mocked, no real credentials/network).
- Hold placement (`scripts/library/hold.sh`) is not started.

See `CLAUDE.md` for the plan and conventions any agent picking this up should
follow, and `scripts/discovery/` for the full API reverse-engineering findings.
