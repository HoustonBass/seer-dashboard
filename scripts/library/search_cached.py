#!/usr/bin/env python3
"""Cached wrapper around the library catalog search.

Usage:
  scripts/library/search_cached.py "<query>" [FORMAT] [--refresh] [--ttl SECONDS] [--json]

Same ranking as scripts/library/search.sh (matchScore: 2 = "title: subtitle"
exact normalized match, 1 = bare title exact match, 0 = other — see
scripts/discovery/search.md) but checks scripts/lib/cache.py (SQLite, at
data/cache.db) first. On a cache miss (or --refresh) it calls the same
gateway.bibliocommons.com search API, caches the results, then prints them.

Auth is NOT reimplemented here — this shells out to scripts/library/auth.sh
(the already-reverse-engineered BiblioCommons login flow, see
scripts/discovery/auth.md) and reads BC_ACCESS_TOKEN/BC_SESSION_ID from its
output, same as search.sh does via `eval`.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import cache  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
AUTH_SH = SCRIPT_DIR / "auth.sh"
GATEWAY_URL = os.environ.get("LIBRARY_GATEWAY_URL", "https://gateway.bibliocommons.com")
AGENCY = os.environ.get("LIBRARY_AGENCY", "fulcolibrary")

COLUMNS = [
    "match_score", "bib_id", "title", "subtitle", "format",
    "availability_status", "copies", "publication_date", "call_number", "authors",
]


def get_auth():
    result = subprocess.run(
        ["sh", str(AUTH_SH)], capture_output=True, text=True, check=True
    )
    values = dict(line.split("=", 1) for line in result.stdout.strip().splitlines() if "=" in line)
    return values["BC_ACCESS_TOKEN"], values["BC_SESSION_ID"]


def normalize(text):
    text = text.lower().strip()
    text = re.sub(r"^the ", "", text)
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r" +", " ", text).strip()
    return text


def score_match(title, subtitle, query_norm):
    full_title = f"{title}: {subtitle}" if subtitle else title
    if normalize(full_title) == query_norm:
        return 2
    if normalize(title) == query_norm:
        return 1
    return 0


def fetch_search(query, format_filter):
    access_token, session_id = get_auth()
    search_query = f"formatcode:({format_filter}) {query}" if format_filter else query

    response = requests.get(
        f"{GATEWAY_URL}/v2/libraries/{AGENCY}/bibs/search",
        headers={
            "Accept": "application/json",
            "X-Access-Token": access_token,
            "X-Session-Id": session_id,
        },
        params={"query": search_query, "searchType": "bl", "locale": "en-US"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    query_norm = normalize(query)
    records = []
    for result in data["catalogSearch"]["results"]:
        bib = data["entities"]["bibs"][result["representative"]]
        info = bib["briefInfo"]
        availability = bib.get("availability") or {}
        title = info.get("title", "")
        subtitle = info.get("subtitle") or ""
        records.append(
            {
                "bib_id": bib["id"],
                "title": title,
                "subtitle": subtitle,
                "format": info.get("format", ""),
                "availability_status": availability.get("status", ""),
                "available_copies": availability.get("availableCopies"),
                "total_copies": availability.get("totalCopies"),
                "publication_date": info.get("publicationDate"),
                "call_number": info.get("callNumber"),
                "authors": "; ".join(info.get("authors") or []),
                "match_score": score_match(title, subtitle, query_norm),
            }
        )

    records.sort(key=lambda r: (-r["match_score"], r["publication_date"] or ""))
    return records


def as_row(record):
    row = dict(record)
    row["copies"] = f"{row.pop('available_copies')}/{row.pop('total_copies')}"
    return row


def main():
    parser = argparse.ArgumentParser(description="Cached library catalog search")
    parser.add_argument("query")
    parser.add_argument("format_filter", nargs="?", default="")
    parser.add_argument("--refresh", action="store_true", help="bypass cache, re-fetch live")
    parser.add_argument("--ttl", type=int, default=cache.DEFAULT_TTL_SECONDS, help="cache freshness window, in seconds")
    parser.add_argument("--json", action="store_true", help="print JSON instead of TSV")
    args = parser.parse_args()

    conn = cache.get_connection()

    records = None if args.refresh else cache.get_cached_search(conn, args.query, args.format_filter, ttl=args.ttl)
    source = "cache"
    if records is None:
        records = fetch_search(args.query, args.format_filter)
        cache.cache_search(conn, args.query, args.format_filter, records)
        source = "live"

    rows = [as_row(r) for r in records]

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print("\t".join(str(row[col]) if row[col] is not None else "" for col in COLUMNS))

    print(f"# source={source} count={len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    main()
