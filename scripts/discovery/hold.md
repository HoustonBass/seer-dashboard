# Hold — findings (unverified, not yet implemented)

**Status: research only.** Nothing here has been tested against the real
Fulton County account. Per plan, live hold-endpoint discovery happens with the
user driving the browser and walking through the network tab together, since a
wrong test call could place a real, uncancelable-by-us hold. Don't fire any of
this against the live API without that session.

## From public prior art

[`luscoma/bibliocommons-mcp`](https://github.com/luscoma/bibliocommons-mcp)
documents (for other library systems, not confirmed for Fulton County):

**Place a hold:**
```
POST https://gateway.bibliocommons.com/v2/libraries/{library}/holds?locale=en-US
Headers: X-Access-Token, X-Session-Id (same as search)
Body:
{
  "metadataId": "<bib id, e.g. S171C1045545>",
  "materialType": "PHYSICAL",
  "accountId": <int>,
  "enableSingleClickHolds": false,
  "materialParams": {
    "branchId": "<pickup branch id>",
    "expiryDate": "<date>",
    "errorMessageLocale": "en-US"
  }
}
```
Their docs specifically flag that `errorMessageLocale` must be nested inside
`materialParams`, not top-level, or the downstream ILS call fails.

**Cancel a hold:**
```
DELETE https://gateway.bibliocommons.com/v2/libraries/{library}/holds?locale=en-US
Body: { "accountId": <int>, "metadataIds": [...], "holdIds": [...], "errorMessageLocale": "en-US" }
```

**`accountId` derivation — conflicting info, needs live verification:**
- Their docs say: `accountId = int(session_id.split("-")[-1]) + 1`
- Our own capture of `GET /header/state` returned `user.id: 3006586697`, which
  matches the numeric suffix of our `session_id` **directly, with no +1**.
- Don't trust either blindly — check `/header/state`'s `user.id` against
  whatever `accountId` the real hold UI sends when we capture it live.

## Open questions for the live session

- Exact hold-listing endpoint (path unconfirmed).
- Whether `branchId` is required, and what Fulton County's branch IDs are —
  probably enumerable from `/header/state`'s `preferred_locations` field
  (already seen: `MILTON` = Milton Branch) or a branches endpoint.
- Whether `expiryDate` is required or has a sane default if omitted.
- Real request/response for a successful hold, captured via the user's own
  browser session, not ours.
