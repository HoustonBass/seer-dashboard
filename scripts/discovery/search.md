# Search — findings

## Real endpoint

```
GET https://gateway.bibliocommons.com/v2/libraries/<agency>/bibs/search
    ?query=<text>&searchType=bl&locale=en-US
Headers:
  Accept: application/json
  X-Access-Token: <bc_access_token cookie value>
  X-Session-Id: <session_id cookie value>
```

`<agency>` for Fulton County is `fulcolibrary`.

`query` supports BiblioCommons' field-search syntax, e.g. the original login
URL's destination was `formatcode:(DVD ) brooklyn` — combine a free-text query
with `formatcode:(DVD)` to filter by format (`DVD`, `BK`, `PAPERBACK`, `EBOOK`,
`AB` audiobook, `BOOK_CD`, `BLU-RAY`, etc — the `catalogSearch.fields` array in
the response enumerates every format present in a given result set with counts).

## Dead ends (don't retry these)

- `POST /v2/libraries/<agency>/cards/search` — looks like a search endpoint by
  name but is actually the "recommended items" promo-card widget; it takes a
  `metadataIds` array and returns unrelated cross-sell content, not search
  results.
- `GET /v2/libraries/<agency>/bibs/search/probes?query=...` — returns 200 with
  an empty body; purpose unclear (possibly an analytics/typeahead probe), not
  useful for us.
- `fulcolibrary.bibliocommons.com/v2/search?query=...` (the page itself) —
  returns full server-rendered HTML even when requested with XHR-style headers
  (`X-Responsive-Page: true` etc., which *does* work for `/user/login`). No
  JSON short-circuit available here; use the gateway endpoint above instead.
- `GET/POST /v2/libraries/<agency>/bibs?query=...` → 422
- `GET /v2/libraries/<agency>/search?query=...` → 404

## Response shape

```jsonc
{
  "catalogSearch": {
    "results": [ { "representative": "<bibId>", "manifestations": ["<bibId>"] }, ... ],
    "pagination": { "count": 25, "page": 1, "pages": 1 },
    "fields": [ /* facets incl. FORMAT with per-format counts */ ]
  },
  "entities": {
    "bibs": {
      "<bibId>": {
        "id": "<bibId>",
        "briefInfo": {
          "title": "...", "subtitle": "...", "format": "DVD",
          "authors": [...], "publicationDate": "...", "jacket": {...}
        },
        "availability": {
          "status": "AVAILABLE",        // or UNAVAILABLE, etc.
          "availableCopies": 7,
          "totalCopies": 7,
          "circulationType": "REQUEST"  // relevant later for hold.sh
        }
      }
    }
  }
}
```

`catalogSearch.results[].representative` is the bib ID to look up in
`entities.bibs`. Each result can have multiple `manifestations` (editions) —
for now we only surface the representative one; if hold placement later needs
a specific edition, revisit this.

## Cross-checked against public prior art

[`luscoma/bibliocommons-mcp`](https://github.com/luscoma/bibliocommons-mcp)
confirms the same `gateway.bibliocommons.com/v2/libraries/{library}/...`
routing, and flags a gotcha we haven't hit yet ourselves: **pagination is
fixed at 25 results/page — a `size`/`limit` param is silently ignored; use
`page=N` (1-indexed) to get more results instead.** Worth handling in
`search.sh` if a query can return more than 25 matches.

## Matching strategy (implemented)

Real example that surfaced the problem: searching `terminator` ranks
`title="Terminator", subtitle="Dark Fate"` (i.e. *Terminator: Dark Fate*,
2019) above `title="The Terminator", subtitle=""` (the actual 1984 film) in
BiblioCommons' own relevance order. The API's ranking does not prefer exact
title matches, and `title`/`subtitle` are separate fields — reading `title`
alone is misleading, not because catalog data is wrong but because it's only
half the real title.

There's no shared ID between Overseerr (TMDB-based) and the library catalog
(ISBN/UPC, not TMDB) to resolve this definitively, and `briefInfo.publicationDate`
is the **DVD/media release year, not the film's release year** (e.g. "The
Terminator" DVD shows `2004`, "Terminator 2" DVD shows `2003`) — useless for
matching against TMDB release years directly.

Given that, `search.sh` computes a `matchScore` column (2 = `title: subtitle`
exactly equals the normalized query, 1 = bare `title` exactly equals it, 0 =
otherwise) and sorts by it, but **never auto-selects** — every candidate is
still printed, ranked, for a human (or a calling script) to confirm. Per user
decision: this repo always surfaces ranked candidates rather than silently
picking one, because the "almost-right" cases (franchise entries, prefix
mismatches) are common enough that full automation isn't trustworthy here.

Implemented as `scripts/library/search.sh`.
