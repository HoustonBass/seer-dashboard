#!/usr/bin/env sh
# Lists Overseerr media requests as TSV:
#   requestId <TAB> type <TAB> tmdbId <TAB> title <TAB> requestStatus <TAB> mediaStatus <TAB> requestedBy
#
# Usage:
#   scripts/seerr/requests.sh                # all requests
#   scripts/seerr/requests.sh pending         # filter: all|approved|available|pending|processing|unavailable|failed
#
# API: GET {SEERR_BASE_URL}/api/v1/request  (paginated via take/skip)
# Title isn't included in the request list itself, so for each result we look
# it up via GET /api/v1/movie/{tmdbId} or /api/v1/tv/{tmdbId}.
# Auth: X-Api-Key header (SEERR_API_KEY from .env).
# See scripts/discovery/seerr.md for status code meanings and findings.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/../lib/env.sh"

: "${SEERR_API_KEY:?SEERR_API_KEY not set in .env}"
: "${SEERR_BASE_URL:?SEERR_BASE_URL not set in .env}"
BASE_URL="${SEERR_BASE_URL%/}"

FILTER="${1:-all}"
TAKE=50
SKIP=0

seerr_get() {
  curl -sS -m 15 "$BASE_URL$1" -H "X-Api-Key: $SEERR_API_KEY" -H "Accept: application/json"
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

while :; do
  PAGE="$(seerr_get "/api/v1/request?take=$TAKE&skip=$SKIP&filter=$FILTER&sort=added")"
  printf '%s\n' "$PAGE" | jq -c '.results[]' >> "$TMP"

  RESULT_COUNT="$(printf '%s' "$PAGE" | jq '.results | length')"
  TOTAL="$(printf '%s' "$PAGE" | jq '.pageInfo.results')"
  SKIP=$((SKIP + RESULT_COUNT))

  [ "$RESULT_COUNT" -eq 0 ] && break
  [ "$SKIP" -ge "$TOTAL" ] && break
done

while IFS= read -r REQUEST; do
  TYPE="$(printf '%s' "$REQUEST" | jq -r '.type')"
  TMDB_ID="$(printf '%s' "$REQUEST" | jq -r '.media.tmdbId')"
  REQUEST_ID="$(printf '%s' "$REQUEST" | jq -r '.id')"
  REQUEST_STATUS="$(printf '%s' "$REQUEST" | jq -r '.status')"
  MEDIA_STATUS="$(printf '%s' "$REQUEST" | jq -r '.media.status')"
  REQUESTED_BY="$(printf '%s' "$REQUEST" | jq -r '.requestedBy.displayName')"

  if [ "$TYPE" = "movie" ]; then
    TITLE="$(seerr_get "/api/v1/movie/$TMDB_ID" | jq -r '.title // "?"')"
  else
    TITLE="$(seerr_get "/api/v1/tv/$TMDB_ID" | jq -r '.name // "?"')"
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$REQUEST_ID" "$TYPE" "$TMDB_ID" "$TITLE" "$REQUEST_STATUS" "$MEDIA_STATUS" "$REQUESTED_BY"
done < "$TMP"
