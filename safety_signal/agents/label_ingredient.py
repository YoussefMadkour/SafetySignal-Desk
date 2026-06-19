"""Agent 3 — Label & Ingredient: consumer label vs supplier ingredient sheet.

The undeclared-allergen detection is a deterministic set-diff (supplier allergens
not declared on the consumer label) and stays authoritative. The LLM, when
configured, reads the actual label and supplier text to produce grounded
evidence quotes and a short consumer-risk analysis.
"""
from __future__ import annotations

from .base import SAFETY_PREAMBLE, AgentOutput, apply_narrative

_SYSTEM = (
    SAFETY_PREAMBLE + " You are a labeling-compliance analyst comparing a "
    "consumer label against a supplier ingredient sheet. Cite specific wording "
    "from the documents as evidence. Do not change which allergen was detected."
)


def _llm_enrich(case, primary, llm) -> dict | None:
    user = (
        f"Deterministic analysis already detected an undeclared allergen: "
        f"{primary}.\n\n"
        f"CONSUMER LABEL:\n{case.label_text}\n\n"
        f"SUPPLIER INGREDIENT SHEET:\n{case.supplier_text}\n\n"
        "Return JSON with keys: "
        '"evidence" (list of short quotes/lines from the documents that support '
        f'the undeclared-{primary} finding), '
        '"analysis" (2-3 sentences on the consumer risk this mismatch creates).'
    )
    return llm.complete_json(_SYSTEM, user)


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

    used_llm = False
    if detected and llm is not None and getattr(llm, "enabled", False):
        used_llm = apply_narrative(
            structured, _llm_enrich(case, primary, llm),
            text_fields=("analysis",),
            list_fields=("evidence",),
        )
    structured["reasoning_mode"] = "llm" if used_llm else "deterministic"
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
