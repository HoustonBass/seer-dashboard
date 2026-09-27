#!/usr/bin/env sh
# Pulls the latest main onto the homelab's clone, rebuilds the image, and
# restarts the container via its compose file — see CLAUDE.md/the
# "project-seerr-dashboard-deployment" memory for the full layout. Skips the
# rebuild/restart entirely if the pull brought in nothing new (compares
# HEAD before/after) — no point recreating a container, however briefly,
# for a no-op deploy.
#
# Requires a `homelab` entry in ~/.ssh/config (key-only auth — password auth
# is disabled on that box) pointing at 192.168.1.93. Run from anywhere; this
# doesn't need repo-root .env, it's SSH-only.
#
# Deliberately does NOT touch the `data` submodule (the SQLite caches the
# live container is continuously writing to) — that's a separate, deliberate
# sync (sqlite .backup snapshot -> amend the dbs branch -> force-push ->
# `git submodule update --remote` on the homelab), not something a routine
# code deploy should silently overwrite. A `git pull` here only moves the
# submodule's *pointer* if some other commit deliberately bumped it, which
# doesn't touch the homelab's already-checked-out data/ files by itself.
set -eu

ssh homelab '
  set -eu
  cd ~/repos/seerr-dashboard
  before="$(git rev-parse HEAD)"
  git pull origin main
  after="$(git rev-parse HEAD)"
  if [ "$before" = "$after" ]; then
    echo "Already up to date at $before — skipping rebuild/restart."
    exit 0
  fi
  echo "Updated $before -> $after — rebuilding and restarting."
  cd ~/compose
  docker compose -f seerr-dashboard-compose.yaml up -d --build
'
