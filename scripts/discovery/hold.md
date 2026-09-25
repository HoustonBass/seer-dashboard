# Hold — findings

**Status: CONFIRMED live for hold placement.** Captured 2026-09-20 via
`scripts/discovery/capture-hold.mjs` — the user drove the actual click on a
real, visible (non-headless) browser window; the script only logged in,
navigated to search results, and listened to network traffic. It never
clicked anything itself. This is the live-session process CLAUDE.md calls
for; do not skip it for future undocumented write endpoints.

Cancel-a-hold is still **unconfirmed** — see below.

## Place a hold — CONFIRMED

```
POST https://gateway.bibliocommons.com/v2/libraries/fulcolibrary/holds?locale=en-US
Headers: Accept: application/json, Content-Type: application/json,
         X-Access-Token, X-Session-Id (same as search/auth)
Body:
{
  "metadataId": "S171C852280",
  "materialType": "PHYSICAL",
  "accountId": 3006586698,
  "enableSingleClickHolds": false,
  "materialParams": {
    "branchId": "MILTON",
    "expiryDate": null,
    "errorMessageLocale": "en-US"
  }
}
```

Real response (200):
```json
{
  "id": "S171C852280",
  "entities": {
    "holds": {
      "11939290": {
        "actions": ["cancel", "suspend", "updateLocation", "updateExpiry"],
        "metadataId": "S171C852280",
        "itemId": "852280|74|1",
        "holdsId": "11939290",
        "bibTitle": "Pirates of the Caribbean, on stranger tides",
        "holdsPosition": 1,
        "status": "NOT_YET_AVAILABLE",
        "materialType": "PHYSICAL",
        "pickupLocation": { "code": "MILTON", "name": "Milton Branch", "ips": [] },
        "holdPlacedDate": "2026-09-20",
        "expiryDate": "2027-07-17"
      }
    }
  },
  "successCount": 1
}
```

Confirmed facts, live (not prior-art guesses anymore):
- The public prior-art body shape (see below) is exactly right, including
  `errorMessageLocale` nested inside `materialParams`.
- **`accountId` = `int(session_id.rsplit("-", 1)[-1]) + 1`** — reconfirmed a
  third time (account.md's checkouts/holds GETs were the first two) via the
  actual write endpoint. This is now solid, not "very likely."
- `expiryDate: null` is accepted — the server picks a sane default itself
  (~10 months out from `holdPlacedDate` in this case). Don't feel obligated
  to compute one client-side.
- `branchId: "MILTON"` worked as the pickup location — this account's home
  branch. Real per-account branch codes should come from `/header/state`'s
  `preferred_locations` (see `account.md`) or wherever the user picks a
  pickup branch in the UI — don't hardcode `"MILTON"` for other accounts.
- `holdsId` in the response (`"11939290"` here) is what a future cancel call
  needs — see MatchRepo/hold storage design when this gets wired up.
- **A real hold now exists** on the account for this title (Pirates of the
  Caribbean: On Stranger Tides, Milton Branch pickup) as a direct result of
  this capture session — not cleaned up automatically, since cancel is still
  unconfirmed (see below). The user placed it deliberately as the test case.

## Cancel a hold — still UNCONFIRMED

From public prior art only, not yet captured live:
```
DELETE https://gateway.bibliocommons.com/v2/libraries/{library}/holds?locale=en-US
Body: { "accountId": <int>, "metadataIds": [...], "holdIds": [...], "errorMessageLocale": "en-US" }
```
Same live-capture process (`capture-hold.mjs`, human clicks "Cancel hold"
themselves) should be used before this is ever called from code — don't
assume it's right just because place-hold's shape matched prior art.

## Still open

- Exact hold-listing endpoint (`GET .../holds` from account.md covers listing
  *existing* holds — that's confirmed; this note is stale, kept for history).
- Cancel-a-hold's real shape (see above).
- Whether `branchId` must be a real pickup-eligible branch per bib (some
  items may not be holdable at every branch) — not tested, only one branch
  tried.
