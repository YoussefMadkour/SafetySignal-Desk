"""Event-driven (WebSocket) coordination — Band IS the collaboration layer.

Unlike the sequenced orchestrator, here nothing in Python decides who runs next.
Each of the 7 agents runs as a live WebSocket listener; when Band delivers a
message that @mentions an agent, that agent wakes up, reads the upstream
findings carried in the message (context-through-Band), checks its
prerequisites, runs its logic, and posts its own finding + @mention handoff back
into the room. Remove Band and the workflow cannot proceed — coordination,
context, and convergence all flow through Band.

Convergence: the Regulatory Risk agent is @mentioned by several agents and only
runs once all of its prerequisites (label + batch + recall) have arrived in the
room. The Customer Response agent is terminal and signals completion.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from . import config
from .agents import base
from .agents import (
    batch_trace, complaint_intake, customer_response, label_ingredient,
    pattern_detection, recall_precedent, regulatory_risk,
)
from .band_client import build_mentions, listen_ws
from .case import CaseData
from .orchestrator import ReviewSession
from .schemas import AgentMessage

_AGENT_RUN = {
    "complaint_intake": complaint_intake.run,
    "pattern_detection": pattern_detection.run,
    "label_ingredient": label_ingredient.run,
    "batch_trace": batch_trace.run,
    "recall_precedent": recall_precedent.run,
    "regulatory_risk": regulatory_risk.run,
    "customer_response": customer_response.run,
}

PIPELINE = list(_AGENT_RUN.keys())

# An agent runs once these upstream findings have arrived in the room.
# Empty set => runs on its first trigger (the human kickoff for intake).
PREREQS: dict[str, set[str]] = {
    "complaint_intake": set(),
    "pattern_detection": {"complaint_intake"},
    "label_ingredient": {"complaint_intake"},
    "batch_trace": {"pattern_detection"},
    "recall_precedent": {"label_ingredient"},
    "regulatory_risk": {"label_ingredient", "batch_trace", "recall_precedent"},
    "customer_response": {"regulatory_risk"},
}
TERMINAL = "customer_response"


@dataclass
class AgentNode:
    key: str
    spec: config.AgentSpec
    client: object
    case: CaseData
    registry: dict
    llm: object
    chat_id: str
    prereqs: set
    emit: Callable[[AgentMessage], None]
    terminal_event: asyncio.Event
    log: Callable[[str], None]
    is_terminal: bool = False
    state: dict = field(default_factory=dict)
    done: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def handle(self, msg: dict) -> None:
        # 1) Absorb any upstream findings carried in the Band message.
        for data in base.extract_jsons(msg.get("content") or ""):
            ak = data.get("agent")
            if ak:
                self.state[ak] = data

        # 2) Decide whether this agent is now ready to act (once).
        async with self.lock:
            if self.done:
                return
            ready = (not self.prereqs) or self.prereqs.issubset(self.state.keys())
            if not ready:
                return
            self.done = True

        self.log(f"{self.spec.name} triggered (have: {sorted(self.state)})")
        out_msg = await asyncio.to_thread(self._run_and_publish)
        if out_msg is not None:
            self.emit(out_msg)
        if self.is_terminal:
            self.terminal_event.set()

    def _run_and_publish(self) -> AgentMessage | None:
        try:
            output = _AGENT_RUN[self.key](self.case, self.state, self.llm)
            return base.publish(self.client, self.registry, self.chat_id, self.spec,
                                output, embed_context=True)
        except Exception as exc:  # never let one agent kill the loop
            self.log(f"{self.spec.name} error: {exc}")
            return None


async def run_event_driven(
    case: CaseData,
    auto_approve: bool = False,
    on_emit: Callable[[AgentMessage], None] | None = None,
    log: Callable[[str], None] = print,
    timeout: float = 150.0,
) -> tuple[ReviewSession, str, list[AgentMessage]]:
    """Open a Band room and let the agents coordinate over WebSocket."""
    session = ReviewSession(case=case, online=True, step_delay=0)
    if not session.online:
        raise RuntimeError("Band not configured or no registered agents (run scripts.register_agents).")

    chat_id = session.setup_room()
    log(f"Band room: {chat_id}")
    for line in session.setup_log:
        log(f"  {line}")

    registry = session.registry
    clients = session._agent_clients
    collected: list[AgentMessage] = []
    terminal_event = asyncio.Event()

    def emit(m: AgentMessage) -> None:
        collected.append(m)
        spec = config.AGENTS_BY_NAME.get(m.agent_name)
        if spec:
            session.state.absorb(spec.key, m.structured_data)
        session.state.audit_trail.append(m)
        session.messages.append(m)
        if on_emit:
            on_emit(m)

    nodes = {
        key: AgentNode(
            key=key, spec=config.AGENTS_BY_KEY[key], client=clients[key], case=case,
            registry=registry, llm=session.llm, chat_id=chat_id, prereqs=PREREQS[key],
            emit=emit, terminal_event=terminal_event, log=log, is_terminal=(key == TERMINAL),
        )
        for key in PIPELINE
    }

    stop = asyncio.Event()
    tasks = []
    for key, node in nodes.items():
        info = registry[key]
        tasks.append(asyncio.create_task(
            _resilient_listen(info["agent_id"], info["api_key"], chat_id, node.handle, stop, log,
                              info["name"])
        ))

    await asyncio.sleep(5.0)  # let all sockets join their channels

    # Kickoff: relay the Recall Manager opening the case (Human API is gated).
    gw = clients.get("regulatory_risk") or next(iter(clients.values()))
    prefix, mentions = build_mentions(["complaint_intake"], registry)
    kickoff_text = (
        f"{prefix} Case {case.case_id} opened by the Recall Manager for {case.product}, "
        f"batch {case.batch_code}. Please extract complaint facts and begin the review."
    )
    gw.post_message(chat_id, kickoff_text, mentions)
    log("Kickoff posted → @Complaint Intake Agent")

    # Join-race guard: if a socket finished joining *after* the kickoff was sent,
    # the first agent never sees it (Band doesn't replay pre-join messages) and
    # the whole pipeline stalls. Re-post the kickoff until the first agent acts.
    # The per-agent run-once guard makes re-posting harmless.
    async def _kickoff_guard():
        for _ in range(3):
            await asyncio.sleep(7.0)
            if collected or terminal_event.is_set():
                return
            log("No activity yet — re-sending kickoff (join-race guard).")
            try:
                gw.post_message(chat_id, kickoff_text, mentions)
            except Exception as exc:
                log(f"[ws] kickoff re-post failed: {exc}")
    guard_task = asyncio.create_task(_kickoff_guard())

    try:
        await asyncio.wait_for(terminal_event.wait(), timeout=timeout)
        log("Pipeline complete — Customer Response posted drafts; awaiting human decision.")
    except asyncio.TimeoutError:
        log(f"Timed out after {timeout}s; agents reached: {[m.agent_name for m in collected]}")

    if auto_approve:
        await asyncio.sleep(1.0)
        log("Auto-approving as Recall Manager (demo mode).")
        dec = session.submit_decision(
            "APPROVE_BATCH_HOLD",
            "Approve immediate batch hold and retailer notification. "
            "Prepare recall packet for QA, legal, and regulatory review.",
        )
        collected.append(dec)
        if on_emit:
            on_emit(dec)

    stop.set()
    guard_task.cancel()
    for t in tasks:
        t.cancel()
    await asyncio.gather(guard_task, *tasks, return_exceptions=True)
    return session, chat_id, collected


async def _resilient_listen(agent_id, api_key, chat_id, on_message, stop, log, name):
    """Wrap listen_ws so a dropped socket reconnects instead of ending the agent."""
    while not stop.is_set():
        try:
            await listen_ws(agent_id, api_key, [chat_id], on_message, stop)
            return  # clean stop
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log(f"[ws] {name} reconnecting after: {exc}")
            await asyncio.sleep(2.0)
