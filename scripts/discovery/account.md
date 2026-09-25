# Account summary (checkouts/holds) — findings

**Status: confirmed live, read-only.** Unlike hold.md, everything here was
verified with real GET calls against the live account — no risk of mutating
anything, per CLAUDE.md's "read-only GETs are fine" allowance. This is what
resolved hold.md's previously-conflicting `accountId` derivation.

## Endpoints

```
GET https://gateway.bibliocommons.com/v2/libraries/fulcolibrary/checkouts?locale=en-US&accountId=<id>&materialType=PHYSICAL&page=<n>
GET https://gateway.bibliocommons.com/v2/libraries/fulcolibrary/holds?locale=en-US&accountId=<id>&materialType=PHYSICAL&page=<n>
```
Headers: `X-Access-Token`, `X-Session-Id` (same as search/auth).

`accountId` is required — omitting it 422s with
`{"error":{"fieldErrors":{"accountId":"Required"}}}`.

## `accountId` derivation

`accountId = int(session_id.rsplit("-", 1)[-1]) + 1` — confirmed by trial:
the bare numeric suffix (no +1) 500s on both endpoints; +1 returns real data.
This directly resolves the open question in hold.md.

## Response shape

Both endpoints share the same shape:

```json
{
  "entities": {
    "bibs": { "<metadataId>": { "briefInfo": { "format": "DVD", "title": "...", ... }, ... } },
    "checkouts": { "<checkoutId>": { "metadataId": "<bib id>", "materialType": "PHYSICAL", "status": "OUT", "dueDate": "...", ... } },
    "holds":     { "<holdsId>":    { "metadataId": "<bib id>", "materialType": "PHYSICAL", "status": "READY_FOR_PICKUP" | "IN_TRANSIT" | "NOT_YET_AVAILABLE" | ..., ... } }
  },
  "borrowing": {
    "checkouts" | "holds": {
      "items": ["<id>", ...],
      "pagination": { "count": <n>, "page": <n>, "limit": 25, "pages": <n> }
    },
    "summaries": { ... aggregate counts by status/materialType, NOT format-specific ... }
  }
}
```

- `entities.<kind>` items key by checkout/hold id; each has a `metadataId`
  pointing into `entities.bibs` for the actual title/format.
- `borrowing.summaries` gives aggregate counts, but only broken down by
  status/materialType (PHYSICAL/DIGITAL) — **not** by format (DVD vs book vs
  audiobook). To count "DVDs specifically" you have to join each
  checkout/hold's `metadataId` against `entities.bibs[...].briefInfo.format`
  yourself — there's no server-side DVD-only filter. `format: "DVD"` is the
  same field/value library search already uses (see search.md), so this
  joins consistently with the rest of the app.
- `materialType=PHYSICAL` as a query param does filter `entities.<kind>`
  itself (digital holds/checkouts are excluded from the list) but does
  **not** filter `borrowing.summaries` — that stays a whole-account
  aggregate regardless of the query param. Don't use `summaries` for a
  DVD-specific count; count `entities.<kind>` items after joining bibs
  instead (see `LibraryRepo.get_dvd_activity_count`).
- Pagination: `borrowing.<kind>.pagination.pages` — loop `page=` until
  `page >= pages`, same pattern as SeerrRepo's request-list pagination.

## What this does NOT confirm

This says nothing new about the hold-placement (POST) or hold-cancellation
(DELETE) endpoints in hold.md — those remain untested, and still require a
live session with the user driving the browser before any code calls them.
