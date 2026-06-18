"""Refresh the openFDA precedent cache from the real API.

    python -m scripts.fetch_openfda
"""
from __future__ import annotations

from safety_signal import openfda


def main() -> int:
    data = openfda.get_precedents()
    live = data.get("_live")
    print(f"live={live} results={len(data.get('results', []))}")
    if data.get("_fetch_error"):
        print("fetch_error (used cache):", data["_fetch_error"])
    for r in data.get("results", [])[:5]:
        print(" -", r.get("recalling_firm"), "|", (r.get("reason_for_recall") or "")[:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
