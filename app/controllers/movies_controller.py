"""HTTP layer for /api/movies/search and /api/collections/<id>. Parses the
request, calls the service, serializes the response — no business logic."""
from flask import Blueprint, jsonify, request

from app.services.movie_search_service import MovieRequestError


def create_movies_blueprint(movie_search_service):
    bp = Blueprint("movies", __name__)

    @bp.route("/api/movies/search")
    def search():
        try:
            results = movie_search_service.search(request.args.get("query", ""))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"results": results})

    @bp.route("/api/collections/<int:collection_id>")
    def get_collection(collection_id):
        refresh = request.args.get("refresh") == "1"
        collection, source = movie_search_service.get_collection(collection_id, force_refresh=refresh)
        return jsonify({"source": source, "collection": collection})

    @bp.route("/api/movies/request", methods=["POST"])
    def request_movie():
        tmdb_id = (request.get_json(force=True) or {}).get("tmdb_id")
        if not isinstance(tmdb_id, int):
            return jsonify({"error": "tmdb_id (integer) is required"}), 400
        try:
            return jsonify(movie_search_service.request_movie(tmdb_id))
        except MovieRequestError as e:
            return jsonify({"error": str(e)}), 502

    @bp.route("/api/collections/<int:collection_id>/request", methods=["POST"])
    def request_collection(collection_id):
        return jsonify(movie_search_service.request_collection(collection_id))

    return bp
