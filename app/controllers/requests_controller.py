"""HTTP layer for /api/requests. Parses the request, calls the service,
serializes the response — no business logic, no direct repo/DB access."""
from flask import Blueprint, jsonify, request


def create_requests_blueprint(requests_service):
    bp = Blueprint("requests", __name__)

    @bp.route("/api/requests")
    def list_requests():
        filter_key = request.args.get("filter", "all")
        force_refresh = request.args.get("refresh") == "1"
        rows, source = requests_service.get_requests(filter_key, force_refresh=force_refresh)
        return jsonify({"source": source, "results": rows})

    return bp
