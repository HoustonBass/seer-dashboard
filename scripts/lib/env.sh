#!/usr/bin/env sh
# Loads .env from repo root into the current shell. Source this at the top of every script:
#   . "$(dirname "$0")/../lib/env.sh"
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
else
  echo "Missing .env at $ENV_FILE (copy .env.example)" >&2
  exit 1
fi
