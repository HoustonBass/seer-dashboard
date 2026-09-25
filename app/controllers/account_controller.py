"""HTTP layer for /api/account. Parses the request, calls the service,
serializes the response — no business logic, no direct repo/DB access."""
from flask import Blueprint, jsonify, request


def create_account_blueprint(account_service):
    bp = Blueprint("account", __name__)

    @bp.route("/api/account/dvd-count")
    def dvd_count():
        force_refresh = request.args.get("refresh") == "1"
        summary, source = account_service.get_dvd_activity_count(force_refresh=force_refresh)
        return jsonify({"source": source, **summary})

    return bp
