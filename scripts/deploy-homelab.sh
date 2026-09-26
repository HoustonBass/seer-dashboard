#!/usr/bin/env sh
# Pulls the latest main onto the homelab's clone, rebuilds the image, and
# restarts the container via its compose file — see CLAUDE.md/the
# "project-seerr-dashboard-deployment" memory for the full layout.
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
  git pull origin main
  cd ~/compose
  docker compose -f seerr-dashboard-compose.yaml up -d --build
'
