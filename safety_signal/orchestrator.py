"""Drive a full safety review inside a real Band room (agent-driven).

On the current Band tier the Human API is Enterprise-gated, so all runtime
coordination uses the Agent API: a coordinator agent creates the room, recruits
the other agents and the human owner as participants, and every agent posts its
structured finding (event) and @mention handoff (message) with its own key. The
human recall manager's decision is made in the UI and relayed into the room via
the agent gateway so it is captured in the Band transcript (the audit trail).

Execution order is sequenced here for a reliable demo, while the handoff
@mentions reflect the collaboration graph (including the parallel Label + Batch
Trace branch fanned out from Pattern Detection).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from . import config
from .agents import base
from .agents import (
    batch_trace, complaint_intake, customer_response, label_ingredient,
    pattern_detection, recall_precedent, regulatory_risk,
)
from .band_client import BandAgentClient, build_mentions
from .case import CaseData
from .llm_client import LLMClient
from .schemas import AgentMessage, SafetySignalState

PIPELINE = [
    "complaint_intake",
    "pattern_detection",
    "label_ingredient",   # parallel branch start
    "batch_trace",        # parallel branch
    "recall_precedent",
    "regulatory_risk",
    "customer_response",
]
COORDINATOR = "complaint_intake"

_AGENT_RUN = {
    "complaint_intake": complaint_intake.run,
    "pattern_detection": pattern_detection.run,
    "label_ingredient": label_ingredient.run,
    "batch_trace": batch_trace.run,
    "recall_precedent": recall_precedent.run,
    "regulatory_risk": regulatory_risk.run,
    "customer_response": customer_response.run,
}


@dataclass
class ReviewSession:
    case: CaseData
    online: bool = True
    step_delay: float = 0.6
    registry: dict[str, dict] = field(default_factory=dict)
    chat_id: str | None = None
    _agent_clients: dict[str, BandAgentClient] = field(default_factory=dict)
    state: SafetySignalState | None = None
    llm: LLMClient | None = None
    messages: list[AgentMessage] = field(default_factory=list)
    setup_log: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.llm = LLMClient()
        self.state = SafetySignalState(
            case_id=self.case.case_id, product=self.case.product, batch_code=self.case.batch_code
        )
        if self.online:
            self.registry = config.load_agent_registry()
            if not self.registry:
                self.online = False  # no registered agents -> local preview
        if self.online:
            for key, info in self.registry.items():
                self._agent_clients[key] = BandAgentClient(info["api_key"], info["agent_id"])

    # ---- setup ----
    def _coordinator(self) -> BandAgentClient | None:
        return self._agent_clients.get(COORDINATOR) or next(iter(self._agent_clients.values()), None)

    def setup_room(self) -> str | None:
        """Coordinator agent creates the room and recruits all participants."""
        if not self.online:
            return None
        coord = self._coordinator()
        title = f"SafetySignal Desk — {self.case.product} ({self.case.batch_code})"
        chat = coord.create_chat(title)
        self.chat_id = chat.get("id") or (chat.get("chat") or {}).get("id")
        self.setup_log.append(f"Room created: {self.chat_id}")

        # Recruit the other agents (coordinator is already a participant as creator).
        for key, info in self.registry.items():
            if key == COORDINATOR:
                continue
            try:
                coord.add_participant(self.chat_id, info["agent_id"])
                self.setup_log.append(f"+ {info['name']}")
            except Exception as exc:
                self.setup_log.append(f"! add {info['name']} failed: {exc}")
        # Recruit the human recall manager (owner).
        if config.BAND_OWNER_USER_ID:
            try:
                coord.add_participant(self.chat_id, config.BAND_OWNER_USER_ID)
                self.setup_log.append(f"+ {config.HUMAN_MANAGER_NAME} (human)")
            except Exception as exc:
                self.setup_log.append(f"! add human failed: {exc}")

        # Kickoff note as a Band event from the coordinator.
        try:
            coord.post_event(
                self.chat_id,
                content=(f"Case {self.case.case_id} opened for {self.case.product}, "
                         f"batch {self.case.batch_code}. Starting multi-agent safety review."),
                message_type="task",
                metadata={"ui_type": "finding", "case_id": self.case.case_id},
            )
        except Exception as exc:
            self.setup_log.append(f"! kickoff event failed: {exc}")
        return self.chat_id

    def _client_for(self, key: str) -> BandAgentClient | None:
        return self._agent_clients.get(key) if self.online else None

    def _gateway(self) -> BandAgentClient | None:
        """An agent client used to relay human-originated content into Band."""
        return (self._agent_clients.get("regulatory_risk")
                or self._coordinator())

    # ---- run ----
    def run_pipeline(self) -> Iterator[AgentMessage]:
        state_dict: dict[str, dict] = {}
        for key in PIPELINE:
            spec = config.AGENTS_BY_KEY[key]
            output = _AGENT_RUN[key](self.case, state_dict, self.llm)
            state_dict[key] = output.structured
            self.state.absorb(key, output.structured)
            msg = base.publish(self._client_for(key), self.registry, self.chat_id, spec, output)
            self.messages.append(msg)
            self.state.audit_trail.append(msg)
            yield msg
            if self.step_delay:
                time.sleep(self.step_delay)

    # ---- human decision ----
    def submit_decision(self, decision: str, notes: str) -> AgentMessage:
        ts = datetime.now(timezone.utc).isoformat()
        payload = {"actor": "human_recall_manager", "decision": decision,
                   "notes": notes, "timestamp": ts}
        self.state.human_decision = payload

        if self.online and self.chat_id:
            gw = self._gateway()
            content = f"Human Recall Manager decision: {decision}. {notes}"
            try:
                # Record the decision as an event (audit-grade, no mention needed).
                gw.post_event(self.chat_id, content=content, message_type="task",
                              metadata={"structured_data": payload,
                                        "ui_type": "human_action", "actor": "human"})
                # Hand off to Customer Response to act on the approved/changed plan.
                prefix, mentions = build_mentions(["customer_response"], self.registry,
                                                  include_human=True)
                if mentions:
                    gw.post_message(self.chat_id, f"{prefix} {content}", mentions)
            except Exception as exc:
                print(f"[band] decision relay failed: {exc}")

        msg = AgentMessage(
            room_id=self.chat_id or "offline",
            agent_name=config.HUMAN_MANAGER_NAME,
            message_type="human_action",
            summary=f"Decision: {decision}. {notes}",
            structured_data=payload,
            mentions=[config.AGENTS_BY_KEY["customer_response"].name],
            timestamp=ts,
        )
        self.messages.append(msg)
        self.state.audit_trail.append(msg)
        return msg

    def post_final_packet(self, packet_md: str) -> None:
        if self.online and self.chat_id:
            gw = self._gateway()
            try:
                gw.post_event(
                    self.chat_id,
                    content="Safety Decision Packet generated and attached to the case record.",
                    message_type="task",
                    metadata={"ui_type": "final_packet", "length_chars": len(packet_md)},
                )
            except Exception as exc:
                print(f"[band] final packet post failed: {exc}")
        self.messages.append(AgentMessage(
            room_id=self.chat_id or "offline",
            agent_name=config.HUMAN_MANAGER_NAME,
            message_type="final_packet",
            summary="Safety Decision Packet generated.",
            structured_data={"length_chars": len(packet_md)},
        ))
