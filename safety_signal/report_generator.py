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


_AGENT_LABELS = [
    ("complaint_summary", "Complaint Intake Agent"),
    ("pattern_summary", "Pattern Detection Agent"),
    ("label_summary", "Label & Ingredient Agent"),
    ("batch_trace_summary", "Batch Trace Agent"),
    ("recall_precedent_summary", "Recall Precedent Agent"),
    ("regulatory_risk_summary", "Regulatory Risk Agent"),
    ("response_drafts", "Customer & Retailer Response Agent"),
]


def _md_escape(text: str) -> str:
    """Make free text safe to drop inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def build_packet(state: SafetySignalState, case: CaseData) -> str:
    f = case.facts
    e = case.exposure
    intake = state.complaint_summary or {}
    label = state.label_summary or {}
    precedent = state.recall_precedent_summary or {}
    rr = state.regulatory_risk_summary or {}
    drafts = state.response_drafts or {}
    decision = state.human_decision or {}

    # Agent summaries (one-liners) from the audit trail, keyed by Band name.
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

    # ---- AI reasoning (LLM-generated, grounded in deterministic facts) ----
    reasoning = [
        ("Complaint Intake", intake.get("intake_summary")),
        ("Label & Ingredient", label.get("analysis")),
        ("Recall Precedent", precedent.get("precedent_analysis")),
        ("Regulatory Risk", rr.get("reason")),
    ]
    reasoning = [(name, text) for name, text in reasoning if text]
    if reasoning:
        lines += ["", "## Agent Reasoning"]
        for name, text in reasoning:
            lines += [f"**{name}.** {text}", ""]
        lines = lines[:-1]  # drop trailing blank

    # ---- Risk scoring breakdown (deterministic 100-point rubric) ----
    breakdown = rr.get("score_breakdown") or {}
    if breakdown:
        lines += [
            "",
            f"## Risk Scoring ({rr.get('risk_score', '?')}/100 — {risk_level})",
            "",
            "| Category | Points | Max | Basis |",
            "| --- | ---: | ---: | --- |",
        ]
        for cat, d in breakdown.items():
            lines.append(
                f"| {_md_escape(cat)} | {d.get('points', 0)} | {d.get('max', 0)} "
                f"| {_md_escape(d.get('reason', ''))} |"
            )
        triggers = rr.get("policy_triggers") or []
        if triggers:
            lines += ["", "**Company-policy escalation triggers fired:**"]
            lines += [f"- {t}" for t in triggers]

    # ---- Public recall precedents (real openFDA records, verbatim) ----
    patterns = precedent.get("similar_recall_patterns") or []
    if patterns:
        src = ", ".join(precedent.get("sources_used") or []) or "openFDA Food Enforcement"
        lines += [
            "",
            f"## Public Recall Precedents ({precedent.get('precedent_match', 'NONE')} match)",
            f"_Source: {src}._",
            "",
            "| Recalling Firm | Recall # | Class | Reason |",
            "| --- | --- | --- | --- |",
        ]
        for p in patterns:
            lines.append(
                f"| {_md_escape(p.get('recalling_firm', '—'))} "
                f"| {_md_escape(p.get('recall_number', '—'))} "
                f"| {_md_escape(p.get('classification', '—'))} "
                f"| {_md_escape(p.get('reason', '—'))} |"
            )
        rec_lang = precedent.get("recommended_language")
        if rec_lang:
            lines += ["", f"**Recommended consumer-notice language:** {rec_lang}"]

    # ---- One-line agent findings (the Band handoff summaries) ----
    lines += ["", "## Agent Findings", ""]
    for _, label_name in _AGENT_LABELS:
        lines += [f"### {label_name}", by_name.get(label_name, "—"), ""]
    lines = lines[:-1]

    lines += ["", "## Recommended Actions"]
    lines += [f"- {a}" for a in rr.get("recommended_actions", [])]
    lines += ["", "## Blocked Actions"]
    lines += [f"- {a}" for a in rr.get("blocked_actions", [])]

    # ---- All four drafts (none sendable without human approval) ----
    lines += [
        "",
        "## Draft Communications (NOT sent — require human approval)",
        "",
        "### Retailer Hold Notice",
        drafts.get("retailer_hold_notice", "—"),
        "",
        "### Customer Support Reply",
        drafts.get("customer_support_reply", "—"),
        "",
        "### Internal QA Task",
        drafts.get("internal_qa_task", "—"),
        "",
        "### Public Statement Draft",
        drafts.get("public_statement_draft", "—"),
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

    # ---- Provenance: which findings are deterministic vs AI-generated ----
    modes = []
    for slot, label_name in _AGENT_LABELS:
        mode = (getattr(state, slot, {}) or {}).get("reasoning_mode")
        if mode:
            modes.append(f"- {label_name}: {mode}")
    lines += [
        "",
        "## Reasoning Provenance",
        "Scores, counts, batch exposure, and the undeclared-allergen detection are "
        "computed deterministically and are not model-generated. Where an agent's "
        "language is AI-generated it is marked `llm` below.",
    ]
    lines += modes or ["- (all deterministic — no LLM configured)"]

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
