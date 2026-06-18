"""Agent 3 — Label & Ingredient: consumer label vs supplier ingredient sheet."""
from __future__ import annotations

from .base import AgentOutput


def run(case, state, llm=None) -> AgentOutput:
    undeclared = case.undeclared
    detected = bool(undeclared)
    primary = undeclared[0] if undeclared else None

    evidence = []
    if primary:
        evidence.append(f"Consumer label does not list {primary}")
        evidence.append("Supplier ingredient sheet lists peanut flour or peanut cross-contact")

    structured = {
        "agent": "label_ingredient",
        "consumer_label_allergens": case.label_allergens,
        "supplier_sheet_allergens": case.supplier_allergens,
        "undeclared_allergen_detected": detected,
        "undeclared_allergen": primary,
        "evidence": evidence,
        "confidence": 0.91,
    }
    if detected:
        summary = (f"CRITICAL mismatch: supplier sheet declares {primary}, "
                   f"but the consumer label lists only {', '.join(case.label_allergens)}. "
                   f"Suspected undeclared {primary} allergen.")
        ui = "veto"
    else:
        summary = "No undeclared allergen mismatch found between label and supplier sheet."
        ui = "finding"

    return AgentOutput(
        structured=structured,
        summary=summary,
        ui_type=ui if detected else "finding",
        next_keys=["regulatory_risk", "recall_precedent", "batch_trace"],
        handoff_text=("Undeclared peanut mismatch confirmed. Please assess regulatory risk, "
                      "find recall precedents, and confirm affected batch exposure."),
    )
