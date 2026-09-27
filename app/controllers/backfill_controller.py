"""HTTP layer for /api/branches/backfill — lets the Settings popover trigger
the branch-availability backfill (see app/services/backfill_service.py)
instead of only a CLI/docker-exec run. Parses the request, calls the
service, serializes the response — no business logic of its own.
"""
from flask import Blueprint, jsonify, request


def create_backfill_blueprint(backfill_service):
    bp = Blueprint("backfill", __name__)

    @bp.route("/api/branches/backfill", methods=["POST"])
    def start_backfill():
        force = request.args.get("force") == "1"
        started = backfill_service.start_backfill(force=force)
        if not started:
            return jsonify({"started": False, "already_running": True}), 409
        return jsonify({"started": True})

    @bp.route("/api/branches/backfill")
    def backfill_status():
        return jsonify(backfill_service.status())

    return bp
