# discovery/

Not scripts to run — this is where API reverse-engineering notes live.

The Fulton County Library System website has no public/documented API. Before writing
`scripts/library/*.sh`, we need to capture the real network calls the site makes for:

1. Login (auth) — produces whatever token/cookie/session the site uses
2. Search — query params, response shape, how to extract title/id/availability/branch
3. Placing a hold — the exact endpoint + payload the "Place Hold" button triggers

## Process

1. Use Playwright (headless=false) to open the library site and log in with
   `LIBRARY_USERNAME` / `LIBRARY_PASSWORD` from `.env`.
2. Capture the network traffic (Playwright's `page.on('request')` /
   `page.on('response')`, or the browser's Network tab exported as a HAR).
3. Convert the relevant request(s) to a minimal `curl` command.
4. Strip the curl down to the smallest set of headers/params that still works
   (drop tracking headers, unnecessary cookies, etc.).
5. Save the final minimal curl + notes here as `auth.md`, `search.md`, `hold.md`.
6. Port the minimal curl into the corresponding `scripts/library/*.sh` script.

Nothing here is committed as working code — just findings, sample payloads, and the
pared-down curl commands that the real scripts are built from. Redact cookies/tokens
before committing anything captured from a live session.
