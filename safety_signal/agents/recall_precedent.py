"""Agent 5 — Recall Precedent: real openFDA Food Enforcement precedents.

The precedent records (firms, recall numbers, classifications) come straight from
openFDA and are passed through verbatim — never invented or altered. The LLM,
when configured, only summarizes how those real records apply to this case and
suggests standard consumer-notice language.
"""
from __future__ import annotations

import json

from .base import SAFETY_PREAMBLE, AgentOutput, apply_narrative

_RECOMMENDED_LANGUAGE = (
    "People with peanut allergy may risk serious allergic reaction if they "
    "consume the affected product."
)

_SYSTEM = (
    SAFETY_PREAMBLE + " You are a recall-precedent analyst. Summarize how the "
    "provided real FDA recall records apply to a suspected undeclared-peanut "
    "case. Use only the firms and recall numbers given; do not invent records."
)


def _llm_enrich(case, patterns, llm) -> dict | None:
    user = (
        f"Product under review: {case.product} (batch {case.batch_code}), "
        "suspected undeclared peanut allergen.\n\n"
        "Real openFDA Food Enforcement records:\n"
        f"{json.dumps(patterns, indent=2)}\n\n"
        "Return JSON with keys: "
        '"precedent_analysis" (2-3 sentences on how these precedents inform the '
        'expected action for this case), '
        '"recommended_language" (one sentence of standard undeclared-allergen '
        "consumer-notice wording)."
    )
    return llm.complete_json(_SYSTEM, user)


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
        "recommended_language": _RECOMMENDED_LANGUAGE,
        "sources_used": [source_label],
        "data_is_live": live,
        "confidence": 0.86,
    }

    used_llm = False
    if patterns and llm is not None and getattr(llm, "enabled", False):
        used_llm = apply_narrative(
            structured, _llm_enrich(case, patterns, llm),
            text_fields=("precedent_analysis", "recommended_language"),
        )
    structured["reasoning_mode"] = "llm" if used_llm else "deterministic"
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
