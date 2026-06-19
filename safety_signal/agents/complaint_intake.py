"""Agent 1 — Complaint Intake: extract structured safety facts from complaints.

Counts (complaint volume, batch concentration, medical escalations) are computed
deterministically in ``data_loaders`` and feed scoring, so they stay the source
of truth. The LLM only enriches the *qualitative* picture — a plain-language
summary plus any symptom / allergen mentions it reads out of the raw text — and
falls back cleanly to the deterministic extraction when no model is configured.
"""
from __future__ import annotations

from .base import SAFETY_PREAMBLE, AgentOutput, apply_narrative

_SYSTEM = (
    SAFETY_PREAMBLE + " You are a complaint-intake analyst. Read the raw "
    "consumer complaints and extract qualitative observations only. Do NOT "
    "output counts or totals — those are computed separately."
)


def _llm_enrich(case, llm) -> dict | None:
    lines = [
        f"- [{c.complaint_id}] severity={c.severity or 'n/a'} batch={c.batch_code or 'n/a'}: "
        f"{c.customer_message}"
        for c in case.complaints
    ]
    user = (
        f"Product under review: {case.product} (batch {case.batch_code}).\n\n"
        "Raw consumer complaints:\n" + "\n".join(lines) + "\n\n"
        "Return JSON with keys: "
        '"intake_summary" (2-3 sentence plain-language overview of what '
        'consumers are reporting), '
        '"symptoms" (list of distinct symptoms actually mentioned), '
        '"allergen_mentions" (list of allergens actually mentioned), '
        '"severity_note" (one sentence on the most serious reports).'
    )
    return llm.complete_json(_SYSTEM, user)


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

    used_llm = False
    if llm is not None and getattr(llm, "enabled", False):
        used_llm = apply_narrative(
            structured, _llm_enrich(case, llm),
            text_fields=("intake_summary", "severity_note"),
            list_fields=("symptoms", "allergen_mentions"),
        )
    structured["reasoning_mode"] = "llm" if used_llm else "deterministic"
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
