"""Agent 1 — Complaint Intake: extract structured safety facts from complaints."""
from __future__ import annotations

from .base import AgentOutput


def run(case, state, llm=None) -> AgentOutput:
    f = case.facts
    structured = {
        "agent": "complaint_intake",
        "product": case.product,
        "complaint_count": f.complaint_count,
        "batch_codes_detected": f.batch_codes_detected,
        "symptoms": f.symptoms,
        "allergen_mentions": f.allergen_mentions,
        "medical_escalations": f.medical_escalations,
        "high_risk_complaints": f.high_risk_complaints,
        "missing_fields": ["purchase receipt", "product photo", "medical documentation"],
        "confidence": 0.92,
    }
    summary = (
        f"Extracted {f.complaint_count} complaints for {case.product}. "
        f"{f.allergic_reaction_mentions} describe allergic reactions, "
        f"{f.peanut_allergy_mentions} mention peanut allergy, "
        f"{f.medical_escalations} mention urgent care or a doctor. "
        f"Batch {case.batch_code} appears in {f.target_batch_count} complaints."
    )

    # Allergens were mentioned -> also pull in the Label & Ingredient agent early.
    next_keys = ["pattern_detection"]
    if f.allergen_mentions:
        next_keys.append("label_ingredient")

    return AgentOutput(
        structured=structured,
        summary=summary,
        ui_type="finding",
        next_keys=next_keys,
        handoff_text=("Posting extracted complaint facts. Please assess clustering "
                      "and label/ingredient consistency."),
    )
