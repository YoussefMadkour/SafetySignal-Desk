"""Agent 7 — Customer & Retailer Response: draft safe comms. Cannot send."""
from __future__ import annotations

from .base import AgentOutput

_SYSTEM = (
    "You draft cautious product-safety communications for a recall review. "
    "Never confirm a product is safe. Never promise a recall. Mark everything as "
    "a DRAFT requiring human approval. Return strict JSON with keys: "
    "retailer_hold_notice, customer_support_reply, internal_qa_task, public_statement_draft."
)


def _deterministic(case) -> dict:
    b = case.batch_code
    return {
        "retailer_hold_notice": (
            f"DRAFT — Please place batch {b} of {case.product} on hold pending safety "
            f"review. Do not sell or dispose of affected units until further notice."),
        "customer_support_reply": (
            "DRAFT — Thank you for contacting us. Your report is being reviewed urgently "
            "by our quality team. If you are experiencing ongoing medical symptoms, please "
            "seek medical attention."),
        "internal_qa_task": (
            f"DRAFT — Investigate supplier ingredient change and label verification failure "
            f"for batch {b}."),
        "public_statement_draft": (
            "DRAFT — Requires QA, legal, regulatory, and human recall manager approval before use."),
    }


def run(case, state, llm=None) -> AgentOutput:
    drafts = _deterministic(case)

    # Optional LLM polish (kept within strict safe-language constraints).
    used_llm = False
    if llm is not None and getattr(llm, "enabled", False):
        prompt = (
            f"Product: {case.product}. Batch: {case.batch_code}. "
            f"Suspected undeclared allergen: {(case.undeclared or ['none'])[0]}. "
            f"Affected inventory: {case.exposure.units_in_inventory} units across "
            f"{', '.join(case.exposure.retailers_affected)}. "
            "Draft the four communications as DRAFTs."
        )
        out = llm.complete_json(_SYSTEM, prompt)
        if isinstance(out, dict):
            for k in drafts:
                v = out.get(k)
                if isinstance(v, str) and v.strip():
                    drafts[k] = v if v.strip().upper().startswith("DRAFT") else f"DRAFT — {v.strip()}"
                    used_llm = True

    structured = {
        "agent": "customer_response",
        "requires_human_approval": True,
        "reasoning_mode": "llm" if used_llm else "deterministic",
        **drafts,
    }
    summary = ("Drafted retailer hold notice, customer support reply, internal QA task, and "
               "public statement — all marked DRAFT, not approved for sending. "
               "Awaiting human recall manager decision.")
    return AgentOutput(
        structured=structured,
        summary=summary,
        ui_type="draft",
        next_keys=[],
        include_human=True,
        handoff_text=("Draft communications are ready for review. They will NOT be sent without "
                      "your approval. Please choose a decision."),
    )
