"""Agent 4 — Batch Trace: quantify affected product exposure (deterministic only)."""
from __future__ import annotations

from .base import AgentOutput


def run(case, state, llm=None) -> AgentOutput:
    e = case.exposure
    structured = {
        "agent": "batch_trace",
        "batch_code": e.batch_code,
        "units_produced": e.units_produced,
        "units_sold": e.units_sold,
        "units_in_inventory": e.units_in_inventory,
        "retailers_affected": e.retailers_affected,
        "locations_affected": e.locations_affected,
        "recommended_action": "Immediate batch hold and retailer notification",
        "confidence": 1.0,
    }
    summary = (
        f"Batch {e.batch_code}: {e.units_produced:,} produced, {e.units_sold:,} sold, "
        f"{e.units_in_inventory:,} still in inventory/retail across "
        f"{len(e.retailers_affected)} retailers ({', '.join(e.locations_affected)})."
    )
    return AgentOutput(
        structured=structured,
        summary=summary,
        ui_type="finding",
        next_keys=["customer_response", "regulatory_risk"],
        handoff_text=("Affected inventory quantified. Customer/retailer messaging and "
                      "regulatory risk assessment should reference these figures."),
        confidence=1.0,
    )
