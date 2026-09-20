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

from flask import Flask

from app.controllers.matches_controller import create_matches_blueprint
from app.controllers.requests_controller import create_requests_blueprint
from app.controllers.search_controller import create_search_blueprint
from app.controllers.settings_controller import create_settings_blueprint
from app.lib.env import load_env
from app.repos.library_repo import LibraryRepo
from app.repos.match_repo import MatchRepo
from app.repos.seerr_repo import SeerrRepo
from app.repos.tmdb_repo import TmdbRepo
from app.services.match_service import MatchService
from app.services.requests_service import RequestsService
from app.services.search_service import SearchService
from app.services.settings_service import SettingsService


def create_app():
    load_env()
    app = Flask(__name__)

    seerr_repo = SeerrRepo()
    library_repo = LibraryRepo()
    match_repo = MatchRepo()
    tmdb_repo = TmdbRepo()

    requests_service = RequestsService(seerr_repo, match_repo, tmdb_repo)
    search_service = SearchService(library_repo)
    match_service = MatchService(match_repo)
    settings_service = SettingsService()

    app.register_blueprint(create_requests_blueprint(requests_service))
    app.register_blueprint(create_search_blueprint(search_service))
    app.register_blueprint(create_matches_blueprint(match_service))
    app.register_blueprint(create_settings_blueprint(settings_service))

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
    port = int(os.environ.get("APP_PORT", 5001))
    create_app().run(port=port, debug=True, threaded=True)
