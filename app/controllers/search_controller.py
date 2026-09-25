"""HTTP layer for /api/search. Parses the request, calls the service,
serializes the response — no business logic, no direct repo/DB access."""
from flask import Blueprint, jsonify, request


def create_search_blueprint(search_service):
    bp = Blueprint("search", __name__)

    @bp.route("/api/search")
    def search():
        query = request.args.get("query", "")
        format_filter = request.args.get("format", "")
        force_refresh = request.args.get("refresh") == "1"
        try:
            results, source = search_service.search(query, format_filter, force_refresh=force_refresh)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"source": source, "results": results})

    @bp.route("/api/search/<bib_id>/edition")
    def edition(bib_id):
        force_refresh = request.args.get("refresh") == "1"
        edition, source = search_service.get_bib_edition(bib_id, force_refresh=force_refresh)
        return jsonify({"source": source, "edition": edition})

    return bp
