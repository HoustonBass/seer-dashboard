# Seerr (Overseerr) — findings

Confirmed via `GET /api/v1/status` (no auth needed): running Overseerr v3.4.1.
This is the *actual* Overseerr, not Jellyseerr — Overseerr is still maintained,
contrary to the assumption it was deprecated.

Unlike the library, this API is publicly documented (Overseerr ships an
interactive Swagger UI at `/api-docs` on any running instance). No reverse
engineering needed here — just confirmed the docs by exercising the live
instance.

## Auth

Header: `X-Api-Key: <SEERR_API_KEY>`. Key is generated in Overseerr's own
Settings → General UI, not derived from a login flow.

## Listing requests

```
GET {SEERR_BASE_URL}/api/v1/request?take=<n>&skip=<n>&filter=<filter>&sort=added
```

- `filter`: `all | approved | available | pending | processing | unavailable | failed`
- Paginated — response has `pageInfo.results` (total count) and `pageInfo.pages`;
  loop incrementing `skip` by however many results came back until you've
  covered `pageInfo.results`.
- Each result has `media.tmdbId` but **no title** — titles aren't embedded in
  the request list.

## Getting a title

```
GET {SEERR_BASE_URL}/api/v1/movie/{tmdbId}   -> .title
GET {SEERR_BASE_URL}/api/v1/tv/{tmdbId}      -> .name
```

`type` on the request (`movie` or `tv`) tells you which endpoint to use.
These are Overseerr's own passthrough of TMDB metadata, not TMDB directly —
no separate TMDB key needed.

## Status enums (from Overseerr's own source/behavior, not guessed)

`request.status` (`MediaRequestStatus`):
| value | meaning |
|---|---|
| 1 | PENDING |
| 2 | APPROVED |
| 3 | DECLINED |

`media.status` (`MediaStatus` — availability, not request approval):
| value | meaning |
|---|---|
| 1 | UNKNOWN |
| 2 | PENDING |
| 3 | PROCESSING (approved, being fetched by Radarr/Sonarr) |
| 4 | PARTIALLY_AVAILABLE |
| 5 | AVAILABLE |

Observed live: most of this account's requests sit at `request.status=2`
(approved) with `media.status=3` (processing) — meaning they're approved in
Overseerr but not yet fully downloaded, which is exactly the population we'd
want to cross-reference against library availability (task 4 use case).

Implemented as `scripts/seerr/requests.sh`.
