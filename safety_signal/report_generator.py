"""Generate the Safety Decision Packet (Markdown) and audit trail (JSON).

Both are built from the SafetySignalState accumulated during the review, which
in turn comes from what each agent posted into the Band room. The audit trail
is the serialized Band transcript.
"""
from __future__ import annotations

import json

from .case import CaseData
from .schemas import AgentMessage, SafetySignalState

_DISCLAIMER = (
    "SafetySignal Desk is a decision-support prototype. It does not provide legal, "
    "medical, or regulatory advice and does not automatically issue recalls, public "
    "notices, or regulatory filings. All high-stakes actions require human approval."
)

_REVIEW_STATUS = {
    "HUMAN_REVIEW_REQUIRED": "Human Review Required",
    "MONITOR": "Monitor Only",
}

_DECISION_LABELS = {
    "APPROVE_BATCH_HOLD": "Approved Batch Hold",
    "REQUEST_MORE_EVIDENCE": "Requested More Evidence",
    "PREPARE_RECALL_PACKET": "Prepare Recall Packet",
    "MONITOR_ONLY": "Monitor Only",
    "REJECT_RECOMMENDATION": "Rejected Recommendation",
}


def build_packet(state: SafetySignalState, case: CaseData) -> str:
    f = case.facts
    e = case.exposure
    rr = state.regulatory_risk_summary or {}
    drafts = state.response_drafts or {}
    decision = state.human_decision or {}

    # Map agent summaries from the audit trail by agent name.
    by_name = {m.agent_name: m.summary for m in state.audit_trail}

    risk_level = rr.get("risk_level", "CRITICAL")
    review_status = _REVIEW_STATUS.get(rr.get("decision", "HUMAN_REVIEW_REQUIRED"),
                                       "Human Review Required")
    signal = (state.pattern_summary or {}).get("signal_strength", "HIGH").title()

    findings = [
        f"{f.complaint_count} complaints received in {f.span_days} days.",
        f"{f.target_batch_count} complaints linked to batch {case.batch_code}.",
        f"{f.allergic_reaction_mentions} complaints describe allergic reaction symptoms.",
        f"{f.peanut_allergy_mentions} complaints mention peanut allergy.",
        f"{f.medical_escalations} complaints mention urgent care or doctor visit.",
        f"Consumer label declares only: {', '.join(case.label_allergens) or 'n/a'} (no peanut).",
        "Supplier ingredient sheet lists peanut flour or peanut cross-contact.",
        f"{e.units_in_inventory:,} units remain in inventory or retailer channels.",
    ]

    recommended = rr.get("recommended_actions", [])
    blocked = rr.get("blocked_actions", [])

    def _sec(name):
        return by_name.get(name, "—")

    lines = [
        "# Safety Decision Packet",
        "",
        "## Case Summary",
        f"- Product: {case.product}",
        f"- Batch: {case.batch_code}",
        f"- Case ID: {case.case_id}",
        f"- Review Status: {review_status}",
        f"- Signal Strength: {signal}",
        f"- Risk Level: {risk_level.title()}"
        + (f" (score {rr.get('risk_score')}/100)" if rr.get("risk_score") is not None else ""),
        "",
        "## Key Findings",
    ]
    lines += [f"{i}. {x}" for i, x in enumerate(findings, 1)]

    lines += [
        "",
        "## Agent Findings",
        "",
        "### Complaint Intake Agent",
        _sec("Complaint Intake Agent"),
        "",
        "### Pattern Detection Agent",
        _sec("Pattern Detection Agent"),
        "",
        "### Label & Ingredient Agent",
        _sec("Label and Ingredient Agent"),
        "",
        "### Batch Trace Agent",
        _sec("Batch Trace Agent"),
        "",
        "### Recall Precedent Agent",
        _sec("Recall Precedent Agent"),
        "",
        "### Regulatory Risk Agent",
        _sec("Regulatory Risk Agent"),
        "",
        "### Customer & Retailer Response Agent",
        _sec("Customer and Retailer Response Agent"),
        "",
        "## Recommended Actions",
    ]
    lines += [f"- {a}" for a in recommended]
    lines += ["", "## Blocked Actions"]
    lines += [f"- {a}" for a in blocked]

    lines += [
        "",
        "## Draft Retailer Hold Notice",
        drafts.get("retailer_hold_notice", "—"),
        "",
        "## Draft Customer Support Response",
        drafts.get("customer_support_reply", "—"),
        "",
        "## Human Decision",
    ]
    if decision:
        lines += [
            f"- Decision: {_DECISION_LABELS.get(decision.get('decision',''), decision.get('decision','—'))}",
            f"- Notes: {decision.get('notes','—')}",
            f"- Timestamp: {decision.get('timestamp','—')}",
        ]
    else:
        lines.append("- Pending human recall manager decision.")

    lines += [
        "",
        "## Audit Trail",
        "Every agent message and handoff is recorded in the Band room. "
        f"This packet reflects {len(state.audit_trail)} recorded entries.",
        "",
        "---",
        f"_{_DISCLAIMER}_",
        "",
    ]
    return "\n".join(lines)


def build_audit_trail(messages: list[AgentMessage], chat_id: str | None = None) -> dict:
    return {
        "case": "SafetySignal Desk",
        "band_room_id": chat_id,
        "entry_count": len(messages),
        "entries": [m.model_dump() for m in messages],
    }


def write_outputs(state: SafetySignalState, case: CaseData,
                  messages: list[AgentMessage], outputs_dir, chat_id=None) -> tuple:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    packet_md = build_packet(state, case)
    audit = build_audit_trail(messages, chat_id)
    packet_path = outputs_dir / "safety_decision_packet.md"
    audit_path = outputs_dir / "audit_trail.json"
    packet_path.write_text(packet_md)
    audit_path.write_text(json.dumps(audit, indent=2))
    return packet_path, audit_path, packet_md, audit
