"""HTTP layer for /api/settings. Parses the request, calls the service,
serializes the response — no business logic of its own."""
from flask import Blueprint, jsonify, request


def create_settings_blueprint(settings_service):
    bp = Blueprint("settings", __name__)

    @bp.route("/api/settings")
    def list_settings():
        return jsonify({"switches": settings_service.list_switches()})

    @bp.route("/api/settings", methods=["POST"])
    def set_setting():
        body = request.get_json(force=True)
        try:
            switches = settings_service.set_switch(
                body["key"], bool(body.get("enabled")), body.get("seconds")
            )
        except KeyError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"switches": switches})

    return bp
