# --- frontend build ---------------------------------------------------
FROM node:20-alpine AS frontend-build
WORKDIR /app/web

# web/.npmrc pins registry.npmjs.org — this machine's global pnpm config
# points at an internal-only Artifactory mirror with no public packages
# (see CLAUDE.md); copying it in here keeps that override in effect
# even if the image is built somewhere with the same global config.
COPY web/package.json web/pnpm-lock.yaml web/.npmrc ./
RUN corepack enable && corepack prepare pnpm@10 --activate \
    && pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm build

# --- backend -------------------------------------------------------
FROM python:3.12-alpine AS backend
WORKDIR /app

# Same reasoning as web/.npmrc above, for pip (see run.sh/pip.conf).
COPY pip.conf ./pip.conf
ENV PIP_CONFIG_FILE=/app/pip.conf

COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY app/ app/
COPY --from=frontend-build /app/web/dist web/dist

# CONFIG_DIR points app/lib/env.py at one mounted folder instead of the
# local-dev repo-root .env + data/: it holds config.yaml (credentials —
# copy from config.yaml.example), logs.txt (see create_app()'s FileHandler),
# and every *_cache.db/matches.db/library_auth_cache file the repos write.
# Nothing under it is baked into the image (secrets + durable state don't
# belong in a layer) — mount it at run time, e.g.:
#   mkdir -p config && cp config.yaml.example config/config.yaml  # then fill it in
#   docker run -p 5001:5001 -v $(pwd)/config:/config seerr-dashboard
ENV CONFIG_DIR=/config
VOLUME ["/config"]
EXPOSE 5001
CMD ["python3", "-m", "app.main"]
