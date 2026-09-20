"""HTTP layer for /api/requests. Parses the request, calls the service,
serializes the response — no business logic, no direct repo/DB access.

Streams newline-delimited JSON (one `{"row": ..., "source": ...}` object per
line) instead of one big JSON array, so the frontend can render each request
as its title/TMDB data resolves rather than waiting for the whole batch —
see RequestsService.stream_requests for why this is worth doing (a cold
cache used to mean waiting on all ~250 requests before anything appeared).
"""
import json

from flask import Blueprint, Response, request, stream_with_context


def create_requests_blueprint(requests_service):
    bp = Blueprint("requests", __name__)

    @bp.route("/api/requests")
    def list_requests():
        filter_key = request.args.get("filter", "all")
        force_refresh = request.args.get("refresh") == "1"

        def generate():
            for row, source in requests_service.stream_requests(filter_key, force_refresh=force_refresh):
                yield json.dumps({"row": row, "source": source}) + "\n"

        return Response(stream_with_context(generate()), mimetype="application/x-ndjson")

    return bp
