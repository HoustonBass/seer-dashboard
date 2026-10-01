"""Composition root for the mock frontend's backend.

Layering: Controller (HTTP <-> service calls) -> Service (business logic,
orchestrates repos) -> Repo (one per external system: SeerrRepo,
LibraryRepo, TmdbRepo, plus MatchRepo for our own persisted decisions — each
owns its own API calls, SQLite cache/db, and caching/locking strategy).

Run: python3 -m app.main  (from repo root; serves on :5001, or $APP_PORT if
set — use a different port for test/dev runs so they don't collide with a
server you already have running, e.g. `APP_PORT=5099 python3 -m app.main`)
"""
import os

from flask import Flask, send_from_directory

from app.controllers.account_controller import create_account_blueprint
from app.controllers.backfill_controller import create_backfill_blueprint
from app.controllers.hold_controller import create_hold_blueprint
from app.controllers.matches_controller import create_matches_blueprint
from app.controllers.movies_controller import create_movies_blueprint
from app.controllers.quick_add_controller import create_quick_add_blueprint
from app.controllers.requests_controller import create_requests_blueprint
from app.controllers.search_controller import create_search_blueprint
from app.controllers.settings_controller import create_settings_blueprint
from app.lib.env import load_env
from app.repos.failed_quick_add_repo import FailedQuickAddRepo
from app.repos.library_repo import LibraryRepo
from app.repos.match_repo import MatchRepo
from app.repos.seerr_repo import SeerrRepo
from app.repos.tmdb_repo import TmdbRepo
from app.services.account_service import AccountService
from app.services.backfill_service import BackfillService
from app.services.hold_service import HoldService
from app.services.match_service import MatchService
from app.services.movie_search_service import MovieSearchService
from app.services.quick_add_service import QuickAddService
from app.services.requests_service import RequestsService
from app.services.search_service import SearchService
from app.services.settings_service import SettingsService


WEB_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "dist")


def create_app():
    load_env()
    app = Flask(__name__, static_folder=WEB_DIST, static_url_path="")

    seerr_repo = SeerrRepo()
    library_repo = LibraryRepo()
    match_repo = MatchRepo()
    tmdb_repo = TmdbRepo()
    failed_quick_add_repo = FailedQuickAddRepo()

    requests_service = RequestsService(seerr_repo, match_repo, tmdb_repo, library_repo)
    search_service = SearchService(library_repo, match_repo)
    match_service = MatchService(match_repo, library_repo)
    movie_search_service = MovieSearchService(seerr_repo, tmdb_repo)
    settings_service = SettingsService()
    quick_add_service = QuickAddService(tmdb_repo, seerr_repo, match_repo, failed_quick_add_repo, library_repo)
    account_service = AccountService(library_repo)
    hold_service = HoldService(library_repo, match_repo)
    backfill_service = BackfillService(library_repo, match_repo)

    app.register_blueprint(create_requests_blueprint(requests_service))
    app.register_blueprint(create_search_blueprint(search_service))
    app.register_blueprint(create_matches_blueprint(match_service))
    app.register_blueprint(create_movies_blueprint(movie_search_service))
    app.register_blueprint(create_settings_blueprint(settings_service))
    app.register_blueprint(create_quick_add_blueprint(quick_add_service))
    app.register_blueprint(create_account_blueprint(account_service))
    app.register_blueprint(create_hold_blueprint(hold_service))
    app.register_blueprint(create_backfill_blueprint(backfill_service))

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        # Only kicks in for a built web/dist — dev workflow (pnpm dev + Vite
        # proxy) doesn't touch this route at all. Lets `web/dist` be served
        # standalone (e.g. behind a reverse proxy) without a separate Vite process.
        if path and os.path.exists(os.path.join(WEB_DIST, path)):
            return send_from_directory(WEB_DIST, path)
        return send_from_directory(WEB_DIST, "index.html")

    @app.after_request
    def add_cors_headers(response):
        # Mock FE only — Vite dev server on a different port needs this to call us.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    return app


if __name__ == "__main__":
    # threaded=True matters here: without it, Werkzeug's dev server handles
    # one request at a time anyway, which would make it impossible to
    # actually observe the single-flight locking behavior in the repos.
    # host="0.0.0.0" (not Flask's 127.0.0.1 default) so the container's
    # published port can actually reach this process — loopback-only binds
    # are invisible from outside the container's network namespace even
    # with `-p` mapped. Harmless for local dev too (still reachable via
    # localhost).
    port = int(os.environ.get("APP_PORT", 5001))
    create_app().run(host="0.0.0.0", port=port, debug=True, threaded=True)
