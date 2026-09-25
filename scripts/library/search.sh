#!/usr/bin/env sh
# Searches the library catalog for a title and prints matches as TSV, ranked
# (best match first) but NEVER auto-selected — always a human call:
#   matchScore <TAB> metadataId <TAB> title <TAB> subtitle <TAB> format <TAB> availabilityStatus <TAB> availableCopies/totalCopies <TAB> publicationDate <TAB> callNumber <TAB> authors
#
# matchScore: 2 = "title: subtitle" exactly matches the query (normalized) —
#             e.g. query "terminator dark fate" vs title="Terminator"
#             subtitle="Dark Fate". 1 = bare title exactly matches (catches
#             franchise entries like "Terminator 3" where the query was just
#             "terminator 3"). 0 = anything else the API considered relevant.
# Normalization: lowercase, strip a leading "the ", drop punctuation.
#
# This exists because BiblioCommons splits title/subtitle separately and its
# own relevance ranking does NOT prefer exact title matches — searching
# "terminator" ranks "Terminator: Dark Fate" (title="Terminator",
# subtitle="Dark Fate") above "The Terminator" (title="The Terminator",
# subtitle=""). See scripts/discovery/search.md.
#
# Title/subtitle alone is NOT always enough: e.g. "dune" returns three
# distinct DVDs (1984, 2000 miniseries, 2021) all with bare title "Dune" and
# no subtitle — they tie at the same matchScore. publicationDate, callNumber,
# and authors (cast names for AV media, e.g. "Hurt, William") are the only
# fields that disambiguate those cases, so they're always included in the
# output for a human to judge — there's no reliable way to auto-resolve this
# from title text alone. See scripts/discovery/search.md.
#
# Usage:
#   scripts/library/search.sh "brooklyn nine nine"
#   scripts/library/search.sh "brooklyn nine nine" DVD     # optional format filter, e.g. DVD, BK, BLU-RAY
#
# API: GET https://gateway.bibliocommons.com/v2/libraries/<agency>/bibs/search
# Auth: X-Access-Token / X-Session-Id headers from scripts/library/auth.sh
# See scripts/discovery/search.md for how this was found.
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/../lib/env.sh"

QUERY="${1:?Usage: search.sh <query> [format]}"
FORMAT="${2:-}"

LIBRARY_AGENCY="${LIBRARY_AGENCY:-fulcolibrary}"
LIBRARY_GATEWAY_URL="${LIBRARY_GATEWAY_URL:-https://gateway.bibliocommons.com}"

eval "$("$SCRIPT_DIR/auth.sh")"

# The search backend is Solr-based and treats bare "?"/"*" as wildcard
# operators, not literal punctuation — e.g. a trailing "?" in "O Brother,
# Where Art Thou?" silently zeroes out the result count instead of matching
# the literal title. Escape them so title text is always searched literally.
ESCAPED_QUERY="$(printf '%s' "$QUERY" | sed 's/[?*]/\\&/g')"

if [ -n "$FORMAT" ]; then
  SEARCH_QUERY="formatcode:($FORMAT) $ESCAPED_QUERY"
else
  SEARCH_QUERY="$ESCAPED_QUERY"
fi

RESPONSE="$(curl -sS -G "$LIBRARY_GATEWAY_URL/v2/libraries/$LIBRARY_AGENCY/bibs/search" \
  -H "Accept: application/json" \
  -H "X-Access-Token: $BC_ACCESS_TOKEN" \
  -H "X-Session-Id: $BC_SESSION_ID" \
  --data-urlencode "query=$SEARCH_QUERY" \
  --data-urlencode "searchType=bl" \
  --data-urlencode "locale=en-US")"

printf '%s' "$RESPONSE" | jq -r --arg query "$QUERY" '
  def normalize: ascii_downcase | gsub("^the "; "") | gsub("[^a-z0-9 ]"; "") | gsub(" +"; " ") | ltrimstr(" ") | rtrimstr(" ");

  ($query | normalize) as $normQuery
  | .catalogSearch.results[].representative as $id
  | .entities.bibs[$id]
  | (.briefInfo.subtitle // "") as $subtitle
  | .briefInfo.title as $title
  | (if $subtitle != "" then "\($title): \($subtitle)" else $title end) as $fullTitle
  | (
      if ($fullTitle | normalize) == $normQuery then 2
      elif ($title | normalize) == $normQuery then 1
      else 0
      end
    ) as $score
  | [
      $score,
      .id,
      $title,
      $subtitle,
      .briefInfo.format,
      .availability.status,
      "\(.availability.availableCopies)/\(.availability.totalCopies)",
      (.briefInfo.publicationDate // ""),
      (.briefInfo.callNumber // ""),
      ((.briefInfo.authors // []) | join("; "))
    ]
  | @tsv
' | sort -t "$(printf '\t')" -k1,1rn -k8,8n
