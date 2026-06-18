"""Pydantic schemas for Band messages and the case state.

These mirror the spec. ``AgentMessage`` is the normalized shape we render in the
investigation room and export in the audit trail; it is built from real Band
transcript rows (see band_client.normalize_message).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Message/event types surfaced in the investigation room UI.
MESSAGE_TYPES = (
    "finding",
    "handoff",
    "challenge",
    "veto",
    "draft",
    "human_action",
    "final_packet",
)


class AgentMessage(BaseModel):
    room_id: str
    agent_name: str
    message_type: str = "finding"
    summary: str = ""
    structured_data: dict[str, Any] = Field(default_factory=dict)
    mentions: list[str] = Field(default_factory=list)
    confidence: float | None = None
    timestamp: str = ""


class SafetySignalState(BaseModel):
    case_id: str
    product: str
    batch_code: str
    complaint_summary: dict[str, Any] = Field(default_factory=dict)
    pattern_summary: dict[str, Any] = Field(default_factory=dict)
    label_summary: dict[str, Any] = Field(default_factory=dict)
    batch_trace_summary: dict[str, Any] = Field(default_factory=dict)
    recall_precedent_summary: dict[str, Any] = Field(default_factory=dict)
    regulatory_risk_summary: dict[str, Any] = Field(default_factory=dict)
    response_drafts: dict[str, Any] = Field(default_factory=dict)
    human_decision: dict[str, Any] | None = None
    audit_trail: list[AgentMessage] = Field(default_factory=list)

    def absorb(self, agent_key: str, data: dict[str, Any]) -> None:
        """Store an agent's structured output into the matching summary slot."""
        slot = {
            "complaint_intake": "complaint_summary",
            "pattern_detection": "pattern_summary",
            "label_ingredient": "label_summary",
            "batch_trace": "batch_trace_summary",
            "recall_precedent": "recall_precedent_summary",
            "regulatory_risk": "regulatory_risk_summary",
            "customer_response": "response_drafts",
        }.get(agent_key)
        if slot:
            setattr(self, slot, data)
