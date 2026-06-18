"""openFDA Food Enforcement precedent lookup.

Strategy (per the build constraint): try a real live fetch first; on success,
write the result to the local cache. If the live call fails (offline / rate
limit), fall back to the cached copy so the demo never hard-fails.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from . import config

DEFAULT_QUERY = 'reason_for_recall:"undeclared peanut"'


def fetch_live(query: str = DEFAULT_QUERY, limit: int = 5) -> dict:
    """Fetch precedent records live from openFDA. Raises on failure."""
    params = {"search": query, "limit": limit, "sort": "recall_initiation_date:desc"}
    with httpx.Client(timeout=15) as client:
        resp = client.get(config.OPENFDA_BASE_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    return {
        "_source": "openFDA Food Enforcement API",
        "_query": query,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_live": True,
        "results": payload.get("results", []),
    }


def load_cache() -> dict:
    if config.OPENFDA_CACHE.exists():
        return json.loads(config.OPENFDA_CACHE.read_text())
    return {"_live": False, "results": []}


def write_cache(data: dict) -> None:
    config.OPENFDA_CACHE.write_text(json.dumps(data, indent=2))


def get_precedents(query: str = DEFAULT_QUERY, limit: int = 5) -> dict:
    """Return precedent records, preferring a live fetch with cache fallback.

    The returned dict always has ``results`` and a ``_live`` flag the UI can
    surface ("live FDA data" vs "cached FDA data").
    """
    try:
        data = fetch_live(query, limit)
        if data["results"]:
            write_cache(data)
            return data
    except Exception as exc:  # network error, rate limit, bad response
        cached = load_cache()
        cached["_fetch_error"] = str(exc)
        return cached
    # Live succeeded but empty -> fall back to cache for a richer demo.
    return load_cache()


if __name__ == "__main__":
    out = get_precedents()
    print(f"live={out.get('_live')} results={len(out.get('results', []))} "
          f"fetched_at={out.get('_fetched_at')}")
    if out.get("_fetch_error"):
        print("fetch_error:", out["_fetch_error"])
    for r in out.get("results", [])[:5]:
        print(" -", r.get("recalling_firm"), "|", r.get("reason_for_recall", "")[:80])
