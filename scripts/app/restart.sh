#!/usr/bin/env sh
# Rebuilds web/dist and restarts the standalone Flask backend that serves it
# (app/main.py's catch-all static route) — the "build the FE, restart the BE"
# workflow used while testing app/ standalone, outside the pnpm-dev + Vite
# proxy dev loop.
#
# Only touches the process bound to APP_PORT (default 5001), never a blanket
# `pkill -f app.main` — this can kill a server on a non-default port that a
# concurrent dev session started deliberately (see APP_PORT usage in
# CLAUDE.md); this script only ever manages its own default port unless told
# otherwise.
#
# Usage:
#   scripts/app/restart.sh              # rebuild FE, restart BE on :5001
#   APP_PORT=5099 scripts/app/restart.sh
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_PORT="${APP_PORT:-5001}"
LOG_FILE="${LOG_FILE:-$REPO_ROOT/data/backend.log}"

echo "Building frontend..."
( cd "$REPO_ROOT/web" && pnpm build )

EXISTING_PID="$(lsof -ti "tcp:$APP_PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$EXISTING_PID" ]; then
  echo "Stopping existing server on :$APP_PORT ($EXISTING_PID)..."
  kill $EXISTING_PID
  sleep 1
fi

echo "Starting backend on :$APP_PORT..."
mkdir -p "$(dirname "$LOG_FILE")"
( cd "$REPO_ROOT" && APP_PORT="$APP_PORT" python3 -m app.main > "$LOG_FILE" 2>&1 & )

sleep 1.5
if lsof -i "tcp:$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Backend up on http://127.0.0.1:$APP_PORT (log: $LOG_FILE)"
else
  echo "Backend failed to start — check $LOG_FILE" >&2
  exit 1
fi
