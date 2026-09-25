#!/usr/bin/env sh
# Rebuilds deps and starts the backend (Flask) server.
# Usage: ./run.sh          (port 5001, default)
#        APP_PORT=5099 ./run.sh   (second instance alongside a running one)
set -eu

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

python3 -m pip install -q -r app/requirements.txt

exec python3 -m app.main
