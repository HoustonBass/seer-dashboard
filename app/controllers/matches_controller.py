"""HTTP layer for /api/matches. Parses the request, calls the service,
serializes the response — no business logic, no direct repo/DB access."""
from flask import Blueprint, jsonify, request


def create_matches_blueprint(match_service):
    bp = Blueprint("matches", __name__)

    @bp.route("/api/matches", methods=["POST"])
    def save_match():
        match_service.save_match(request.get_json(force=True))
        return jsonify({"ok": True})

    @bp.route("/api/matches/unavailable", methods=["POST"])
    def mark_unavailable():
        match_service.mark_unavailable(request.get_json(force=True))
        return jsonify({"ok": True})

    @bp.route("/api/matches/<int:request_id>", methods=["DELETE"])
    def delete_match(request_id):
        match_service.clear_match(request_id)
        return jsonify({"ok": True})

    return bp
