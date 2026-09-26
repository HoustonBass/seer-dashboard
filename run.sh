#!/usr/bin/env sh
# Rebuilds deps and starts the backend (Flask) server.
# Usage: ./run.sh          (port 5001, default)
#        APP_PORT=5099 ./run.sh   (second instance alongside a running one)
#
# Deliberately uses /usr/bin/python3 (Apple-signed system Python), not
# whatever pyenv/PATH python3 resolves to. Netskope (this machine's
# endpoint security agent) blocks outbound connections at the socket level
# from the ad-hoc-signed pyenv python3 binary but allows Apple-signed
# binaries — that's why hitting the library/Overseerr hosts from this app
# was failing with "No route to host" while curl worked fine.
PYTHON3=/usr/bin/python3

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

PIP_CONFIG_FILE="$REPO_ROOT/pip.conf" "$PYTHON3" -m pip install -q --user -r app/requirements.txt

exec "$PYTHON3" -m app.main
