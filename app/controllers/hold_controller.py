"""HTTP layer for /api/holds. Parses the request, calls the service,
serializes the response — no business logic, no direct repo/DB access.

Places a REAL hold on the live library account — see scripts/discovery/hold.md.
"""
from flask import Blueprint, jsonify, request


def create_hold_blueprint(hold_service):
    bp = Blueprint("hold", __name__)

    @bp.route("/api/holds", methods=["POST"])
    def place_hold():
        result = hold_service.place_hold(request.get_json(force=True))
        return jsonify(result)

    return bp
