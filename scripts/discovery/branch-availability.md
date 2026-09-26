# Branch-level availability

Search (`v2/libraries/{agency}/bibs/search`) and catalogBibs
(`v2/libraries/{agency}/catalogBibs/{bibId}`) only ever expose *aggregate*
availability — `availableCopies`/`totalCopies` system-wide, no per-branch
breakdown. Neither endpoint's response includes a branches/holdings list (both
checked directly — catalogBibs' `entities.catalogBibs.{bibId}` has only
`brief`/`fields`/`editions`, and its `entities` has no `bibItems`/`holdings`
key at all).

## The real endpoint

User captured this directly from the live site's network tab (not derived
via Playwright — no discovery session was needed since we already had a
working curl):

```
GET https://gateway.bibliocommons.com/v2/libraries/fulcolibrary/bibs/{bibId}/availability?locale=en-US
```

The captured curl used the site's raw cookie jar (`_live_bcui_session_id`,
`SRV`, etc.) — reduced and confirmed this instead works with the exact same
`X-Access-Token`/`X-Session-Id` header pair every other endpoint here already
uses (`auth.md`), so no new auth flow needed:

```sh
curl 'https://gateway.bibliocommons.com/v2/libraries/fulcolibrary/bibs/S171C1370130/availability?locale=en-US' \
  -H 'Accept: application/json' \
  -H "X-Access-Token: $BC_ACCESS_TOKEN" \
  -H "X-Session-Id: $BC_SESSION_ID"
```

## Response shape

```jsonc
{
  "availability": {
    "metadataId": "S171C1370130",
    "items": ["1370130|39|1", "1370130|29|1", ...],  // keys into entities.bibItems
    "holdings": [],
    "subscriptions": []
  },
  "entities": {
    "availabilities": {
      "<bibId>": {
        "status": "AVAILABLE",
        "availableCopies": 4,
        "totalCopies": 4,
        "heldCopies": 0,
        "singleBranch": false
        // same aggregate fields the search response already gives us
      }
    },
    "bibItems": {
      "<itemId>": {
        "callNumber": "FLO DVD 791.43 GODZILLA",
        "collection": "Floating collection",
        "branch": { "name": "Adamsville-Collier Heights Branch", "code": "A-COLL" },
        "availability": { "status": "AVAILABLE", "statusType": "AVAILABLE", "libraryUseOnly": false }
      }
      // one entry per physical copy — this is the per-branch breakdown
    }
  }
}
```

Confirmed live against `S171C1370130` (Godzilla Vs. Kong, 4/4 available) —
copies at Adamsville-Collier Heights, Alpharetta, East Roswell, and Kirkwood,
all `AVAILABLE`.

## Notes

- `entities.bibItems` values are keyed by `itemId` (`"{numericBibId}|{branchSeq}|{copy}"`),
  not by branch code — iterate `.values()`, don't assume a stable key shape.
- `singleBranch` in `availabilities` presumably flags bibs held at only one
  branch (untested — every bib checked so far has copies at multiple
  branches).
- Read-only GET, same as `/search` and `/catalogBibs` — no hold-placement
  risk, so this didn't need the human-driven Playwright session `hold.md`
  requires.
