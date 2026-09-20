# Auth — findings

Library: Fulton County Library System, running BiblioCommons ("BiblioCore" app,
v9.37.2). Base URL: `https://fulcolibrary.bibliocommons.com`.

Login form asks for "Username or Library Card Number" + "PIN/Password". No public
API docs exist; this was reverse-engineered via Playwright (`capture-login.mjs`)
driving a real login and reading the network tab.

## Flow

1. `GET /user/login` — sets a session cookie and returns HTML containing a Rails
   CSRF token in a hidden field: `name="authenticity_token" type="hidden"
   value="..."`. Note: hitting `/user/login` bare 302s to itself with a default
   `?destination=...` query param first — follow redirects (`curl -L`).
2. `POST /user/login` as `application/x-www-form-urlencoded`, body:
   - `utf8=✓`
   - `authenticity_token=<from step 1>`
   - `name=<library card number / username>`
   - `user_pin=<PIN/password>`
   - `local=false`

   With browser-XHR-style headers (`X-Requested-With: XMLHttpRequest`,
   `Accept: application/json, text/javascript, */*; q=0.01`, and
   `X-CSRF-Token: <authenticity_token>`), the server responds **200** with a
   JSON body (`{"logged_in":true,"success":true,...}`) and sets the real
   session cookies directly via `Set-Cookie` — no further requests needed:
   - `bc_access_token` — used as the `X-Access-Token` header on all
     `gateway.bibliocommons.com` API calls
   - `session_id` — used as the `X-Session-Id` header on those same calls

   Without those XHR headers (i.e. a normal browser form submit), the server
   instead responds with a `302` to `/sso/web?token=<JWT>`. That JWT's payload
   (HS256, server-signed, NOT verifiable/forgeable by us) is
   `{"cookies":{"bc_access_token":"...","session_id":"..."},"destination":"...","exp":...}`
   — `GET`-ing that URL is what actually sets the cookies for a real browser
   session before redirecting on to `destination`. We don't need this path for
   scripting; it exists purely to hand the tokens to a full-page navigation.

3. Done. `bc_access_token` / `session_id` are the only two values a script
   needs for any subsequent `gateway.bibliocommons.com` call.

## Gotchas

- The login page occasionally serves a transient failure under rapid repeated
  requests (looked like light rate limiting/bot protection during testing) —
  worth a retry rather than assuming credentials are wrong on the first
  failure.
- Password/PIN is restricted to letters and numbers per the UI copy on the
  login page.
- `bc_access_token` and `session_id` are opaque UUID-like strings, not JWTs
  themselves — no expiry is visible client-side. Treat them as short-lived and
  just re-run `auth.sh` per script invocation rather than trying to cache/reuse
  them across long periods.

## Cross-checked against public prior art

This flow (login → CSRF scrape → POST → `bc_access_token`/`session_id` cookies
→ `X-Access-Token`/`X-Session-Id` headers) matches, independently, two public
open-source BiblioCommons clients:
[`luscoma/bibliocommons-mcp`](https://github.com/luscoma/bibliocommons-mcp) and
[`williamjacksn/python-bibliocommons`](https://github.com/williamjacksn/python-bibliocommons).
Good confidence this is the real, stable mechanism rather than something
Fulton County-specific.

Note: `api.bibliocommons.com` (Mashery/Swagger, API-key based) is a **different,
older partner API** — unrelated to the patron-session gateway API documented
here. Don't confuse the two if searching further.

## Minimal curl

```sh
# 1. get CSRF token
curl -sS -L -c cj.txt https://fulcolibrary.bibliocommons.com/user/login \
  | grep -o 'name="authenticity_token" type="hidden" value="[^"]*"'

# 2. log in
curl -sS -b cj.txt -c cj.txt -X POST https://fulcolibrary.bibliocommons.com/user/login \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'X-CSRF-Token: <token from step 1>' \
  -H 'Accept: application/json' \
  --data-urlencode 'utf8=✓' \
  --data-urlencode 'authenticity_token=<token from step 1>' \
  --data-urlencode 'name=<library card number>' \
  --data-urlencode 'user_pin=<pin>' \
  --data-urlencode 'local=false'

# bc_access_token / session_id are now in cj.txt
```

Implemented as `scripts/library/auth.sh`.
