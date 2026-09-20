#!/usr/bin/env sh
# Logs into the BiblioCommons library site and prints the two cookie values
# needed for gateway.bibliocommons.com API calls:
#   BC_ACCESS_TOKEN=...
#   BC_SESSION_ID=...
#
# Usage:
#   . scripts/library/auth.sh            # sources BC_ACCESS_TOKEN/BC_SESSION_ID into your shell
#   scripts/library/auth.sh              # run standalone, prints KEY=VALUE lines to stdout
#
# How this works (see scripts/discovery/auth.md for how it was found):
#   1. GET /user/login to pick up a session cookie + CSRF token (authenticity_token)
#   2. POST credentials + CSRF token as form-urlencoded, with XHR-style headers
#      (X-Requested-With / Accept: application/json). With those headers the
#      server responds 200 with a JSON body instead of a 302 — and sets
#      bc_access_token/session_id cookies directly, no extra hop needed.
#      (A real browser instead gets a 302 to /sso/web?token=<JWT> whose payload
#      carries the same two values, for full-page navigation to work.)
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/../lib/env.sh"

LIBRARY_BASE_URL="${LIBRARY_BASE_URL:-https://fulcolibrary.bibliocommons.com}"
: "${LIBRARY_USERNAME:?LIBRARY_USERNAME not set in .env}"
: "${LIBRARY_PASSWORD:?LIBRARY_PASSWORD not set in .env}"

COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"' EXIT

# Step 1: GET the login page (following the redirect it 302s to itself with a
# default destination param) and grab the CSRF token out of the hidden form field.
LOGIN_PAGE_URL="$LIBRARY_BASE_URL/user/login"
LOGIN_HTML="$(curl -sS -L -c "$COOKIE_JAR" "$LOGIN_PAGE_URL")"
CSRF_TOKEN="$(printf '%s' "$LOGIN_HTML" | grep -o 'name="authenticity_token" type="hidden" value="[^"]*"' | head -1 | sed 's/.*value="//;s/"$//')"

if [ -z "$CSRF_TOKEN" ]; then
  echo "Could not find authenticity_token on login page — page markup may have changed." >&2
  exit 1
fi

# Step 2: POST credentials with XHR-style headers so we get JSON + cookies
# back directly, no redirect to follow.
LOGIN_RESPONSE="$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -X POST "$LOGIN_PAGE_URL" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -H "Accept: application/json, text/javascript, */*; q=0.01" \
  -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
  --data-urlencode "utf8=✓" \
  --data-urlencode "authenticity_token=$CSRF_TOKEN" \
  --data-urlencode "name=$LIBRARY_USERNAME" \
  --data-urlencode "user_pin=$LIBRARY_PASSWORD" \
  --data-urlencode "local=false")"

if ! printf '%s' "$LOGIN_RESPONSE" | grep -q '"logged_in":true'; then
  echo "Login failed — check LIBRARY_USERNAME/LIBRARY_PASSWORD. Response: $LOGIN_RESPONSE" >&2
  exit 1
fi

BC_ACCESS_TOKEN="$(awk '$6 == "bc_access_token" {print $7}' "$COOKIE_JAR")"
BC_SESSION_ID="$(awk '$6 == "session_id" {print $7}' "$COOKIE_JAR")"

if [ -z "$BC_ACCESS_TOKEN" ] || [ -z "$BC_SESSION_ID" ]; then
  echo "Login succeeded but bc_access_token/session_id cookies were not set." >&2
  exit 1
fi

echo "BC_ACCESS_TOKEN=$BC_ACCESS_TOKEN"
echo "BC_SESSION_ID=$BC_SESSION_ID"
