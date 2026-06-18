"""Agent 2 — Pattern Detection: is this a meaningful safety cluster?"""
from __future__ import annotations

from .base import AgentOutput


def run(case, state, llm=None) -> AgentOutput:
    f = case.facts
    concentration = round(f.target_batch_count / f.complaint_count, 2) if f.complaint_count else 0.0
    signal = "HIGH" if concentration >= 0.5 and f.complaint_count >= 5 else \
        ("MEDIUM" if concentration >= 0.3 else "LOW")
    cluster = signal in ("HIGH", "MEDIUM")

    structured = {
        "agent": "pattern_detection",
        "cluster_detected": cluster,
        "signal_strength": signal,
        "cluster_reason": (f"{f.target_batch_count} of {f.complaint_count} complaints "
                           f"reference batch {case.batch_code} within {f.span_days} days"),
        "batch_concentration": concentration,
        "symptom_repetition": {
            "allergic_reaction": f.allergic_reaction_mentions,
            "peanut_allergy": f.peanut_allergy_mentions,
            "urgent_care_or_doctor": f.medical_escalations,
        },
        "recommended_next_agents": ["LabelIngredientAgent", "BatchTraceAgent", "RegulatoryRiskAgent"],
        "confidence": 0.9,
    }
    summary = (
        f"Cluster {'detected' if cluster else 'not detected'} — signal {signal}. "
        f"{f.target_batch_count}/{f.complaint_count} complaints "
        f"({concentration:.0%}) tie to batch {case.batch_code} over {f.span_days} days."
    )
    return AgentOutput(
        structured=structured,
        summary=summary,
        ui_type="handoff",
        next_keys=["label_ingredient", "batch_trace", "regulatory_risk"],
        handoff_text=("Same-batch cluster confirmed. Please verify the label vs supplier "
                      "sheet and quantify affected inventory in parallel."),
    )
