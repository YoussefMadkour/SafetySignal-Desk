"""Agent 5 — Recall Precedent: real openFDA Food Enforcement precedents."""
from __future__ import annotations

from .base import AgentOutput

_RECOMMENDED_LANGUAGE = (
    "People with peanut allergy may risk serious allergic reaction if they "
    "consume the affected product."
)


def run(case, state, llm=None) -> AgentOutput:
    data = case.precedents or {}
    results = data.get("results", [])
    live = data.get("_live", False)

    patterns = []
    for r in results[:3]:
        patterns.append({
            "source": "openFDA Food Enforcement",
            "recalling_firm": r.get("recalling_firm"),
            "recall_number": r.get("recall_number"),
            "reason": r.get("reason_for_recall"),
            "classification": r.get("classification"),
            "typical_action": "Firm-initiated recall or public safety notice",
            "recommended_language": _RECOMMENDED_LANGUAGE,
        })

    match = "STRONG" if len(results) >= 2 else ("MODERATE" if results else "NONE")
    source_label = ("openFDA Food Enforcement (live)" if live
                    else "openFDA Food Enforcement (cached)")

    structured = {
        "agent": "recall_precedent",
        "precedent_match": match,
        "similar_recall_patterns": patterns,
        "sources_used": [source_label],
        "data_is_live": live,
        "confidence": 0.86,
    }
    firms = ", ".join(p["recalling_firm"] for p in patterns if p.get("recalling_firm")) or "n/a"
    summary = (
        f"{match} precedent match. {len(results)} real FDA undeclared-peanut "
        f"enforcement records found ({'live' if live else 'cached'}). "
        f"Examples: {firms}."
    )
    return AgentOutput(
        structured=structured,
        summary=summary,
        ui_type="finding",
        next_keys=["regulatory_risk", "customer_response"],
        handoff_text=("Precedent language available from real FDA recall records. "
                      "Recommend mirroring standard undeclared-allergen wording."),
    )
