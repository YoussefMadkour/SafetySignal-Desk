"""Agent 6 — Regulatory Risk: classify operational risk, require human review.

Does NOT provide legal/medical/regulatory advice. Computes the deterministic
risk score, checks company policy escalation triggers, and blocks unsafe
automatic messaging.
"""
from __future__ import annotations

import json

from .. import scoring
from .base import SAFETY_PREAMBLE, AgentOutput, apply_narrative

_SYSTEM = (
    SAFETY_PREAMBLE + " You are a regulatory-risk analyst. The risk score, "
    "level, and decision are already computed deterministically and are FIXED — "
    "do not restate or change any number. Write only a concise rationale "
    "grounded in the provided breakdown and policy triggers. This is an "
    "operational escalation, not legal, medical, or regulatory advice."
)


def _llm_rationale(case, risk, triggers, llm) -> dict | None:
    user = (
        f"Product: {case.product} (batch {case.batch_code}).\n"
        f"Computed risk: {risk.level} (score {risk.score}/100), "
        f"decision {risk.decision}.\n"
        f"Score breakdown: {json.dumps(risk.breakdown, indent=2)}\n"
        f"Company-policy triggers that fired: {json.dumps(triggers)}\n\n"
        "Return JSON with key \"reason\": a 2-4 sentence professional rationale "
        "explaining why this case warrants the stated risk level and human "
        "review, citing the breakdown categories and triggers above."
    )
    return llm.complete_json(_SYSTEM, user)

RECOMMENDED_ACTIONS = [
    "Place affected batch on internal hold",
    "Notify affected retailers to pause sale pending review",
    "Prepare recall decision packet for QA, legal, and regulatory review",
    "Collect missing customer evidence",
    "Prepare regulatory escalation assessment for human review",
]
BLOCKED_ACTIONS = [
    "Do not send public recall notice without human approval",
    "Do not tell customers the product is confirmed safe",
    "Do not dismiss complaints as isolated",
]


def evaluate_policy(case) -> list[str]:
    """Return the company-policy escalation triggers that fired."""
    f, e = case.facts, case.exposure
    fired = []
    if f.target_batch_count > 5 and (f.span_days or 7) <= 7:
        fired.append(f"{f.target_batch_count} complaints on one batch within {f.span_days} days (>5/7d)")
    if f.medical_escalations >= 1:
        fired.append("complaints mention urgent care / doctor / swelling")
    if case.undeclared:
        fired.append(f"suspected undeclared major allergen ({case.undeclared[0]})")
    # retailer label-inconsistency report present in complaints
    if any("label" in c.text and ("peanut" in c.text or "almond" in c.text) for c in case.complaints):
        fired.append("retailer/customer reports label inconsistency")
    if e.units_in_inventory > 1000:
        fired.append(f"{e.units_in_inventory:,} units remain in market/inventory (>1,000)")
    return fired


def run(case, state, llm=None) -> AgentOutput:
    risk = scoring.compute_risk(
        case.facts, case.exposure,
        undeclared_allergen=bool(case.undeclared),
        unclear_mismatch=False,
        precedent_strong=(case.precedents.get("results") and len(case.precedents["results"]) >= 2),
    )
    triggers = evaluate_policy(case)

    structured = {
        "agent": "regulatory_risk",
        "risk_level": risk.level,
        "risk_score": risk.score,
        "score_breakdown": risk.breakdown,
        "decision": risk.decision,
        "policy_triggers": triggers,
        "recommended_actions": RECOMMENDED_ACTIONS,
        "blocked_actions": BLOCKED_ACTIONS,
        "reason": ("Same-batch complaint clustering, suspected undeclared peanut allergen, "
                   "medical escalation mentions, and remaining inventory exposure"),
        "disclaimer": ("Operational escalation only. Not legal, medical, or regulatory advice."),
        "confidence": 0.9,
    }

    used_llm = False
    if llm is not None and getattr(llm, "enabled", False):
        # The LLM may rephrase only the rationale; score/level/decision are fixed.
        used_llm = apply_narrative(
            structured, _llm_rationale(case, risk, triggers, llm),
            text_fields=("reason",),
        )
    structured["reasoning_mode"] = "llm" if used_llm else "deterministic"
    summary = (
        f"Risk {risk.level} (score {risk.score}/100) — {risk.decision}. "
        f"{len(triggers)} company-policy escalation triggers fired. "
        f"Blocking unsafe automatic messaging; routing to the human recall manager."
    )
    return AgentOutput(
        structured=structured,
        summary=summary,
        ui_type="veto",
        next_keys=["customer_response"],
        include_human=True,
        handoff_text=("CRITICAL risk. Draft retailer/customer communications as DRAFTS only. "
                      "Human recall manager approval is required before any external action."),
        confidence=0.9,
    )
