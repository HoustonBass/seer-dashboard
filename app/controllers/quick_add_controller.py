"""HTTP layer for /api/quick-add. Parses the request, calls the service,
serializes the response — no business logic, no direct repo/DB access."""
from flask import Blueprint, jsonify, request

from app.services.quick_add_service import QuickAddError


def create_quick_add_blueprint(quick_add_service):
    bp = Blueprint("quick_add", __name__)

    @bp.route("/api/quick-add/search")
    def search():
        query = request.args.get("query", "")
        try:
            results = quick_add_service.search_candidates(query)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"results": results})

    @bp.route("/api/quick-add", methods=["POST"])
    def add():
        try:
            result = quick_add_service.add_and_match(request.get_json(force=True))
        except QuickAddError as e:
            # 502: we're the one failing to reach Overseerr, not the caller's
            # fault — the attempt is saved (failed_id) for retry from the
            # failed-quick-adds popover instead of being lost.
            return jsonify({"error": str(e), "failed_id": e.failed_id}), 502
        return jsonify(result)

    @bp.route("/api/quick-add/failed")
    def list_failed():
        return jsonify({"failed": quick_add_service.list_failed()})

    @bp.route("/api/quick-add/failed/<int:failed_id>/retry", methods=["POST"])
    def retry_failed(failed_id):
        try:
            result = quick_add_service.retry_failed(failed_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except QuickAddError as e:
            return jsonify({"error": str(e), "failed_id": e.failed_id}), 502
        return jsonify(result)

    @bp.route("/api/quick-add/failed/<int:failed_id>", methods=["DELETE"])
    def dismiss_failed(failed_id):
        quick_add_service.dismiss_failed(failed_id)
        return jsonify({"ok": True})

    return bp
