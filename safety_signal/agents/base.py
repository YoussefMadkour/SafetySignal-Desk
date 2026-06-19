"""Shared agent contract + Band publishing.

Each specialist agent module exposes ``run(case, state, llm) -> AgentOutput``.
Logic is pure (no Band calls) so it is unit-testable; the orchestrator handles
publishing every output to the real Band room with that agent's own key:

* a structured **event** (the JSON finding) — the audit-grade record, and
* a **handoff message** that @mentions the next agent(s) — the coordination.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .. import config
from ..band_client import BandAgentClient, build_mentions
from ..schemas import AgentMessage

_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

# Shared system preamble for every LLM-backed agent. Keeps the model strictly
# grounded in the deterministic facts it is handed — no invented numbers, firms,
# recall ids, or dates — and inside the case's safety guardrails.
SAFETY_PREAMBLE = (
    "You assist a product-safety recall review in a regulated context. "
    "Use ONLY the facts provided in the user message. Never invent or alter "
    "numbers, company names, recall identifiers, dates, or quantities. Never "
    "state that a product is safe, and never confirm, order, or rule out a "
    "recall. If a fact is not provided, omit it rather than guessing. "
    "Return STRICT JSON only, containing exactly the requested keys."
)


def apply_narrative(
    structured: dict,
    llm_out: dict | None,
    *,
    text_fields: tuple[str, ...] = (),
    list_fields: tuple[str, ...] = (),
) -> bool:
    """Overlay only whitelisted *language* fields from an LLM response.

    Numeric / decision fields are never touched — the LLM can phrase findings
    but cannot change the deterministic ground truth. ``text_fields`` are
    replaced outright; ``list_fields`` are unioned with any existing
    deterministic entries (order-preserving). Returns True if the LLM
    contributed at least one field, so callers can tag ``reasoning_mode``.
    """
    if not isinstance(llm_out, dict):
        return False
    applied = False
    for k in text_fields:
        v = llm_out.get(k)
        if isinstance(v, str) and v.strip():
            structured[k] = v.strip()
            applied = True
    for k in list_fields:
        v = llm_out.get(k)
        if isinstance(v, list):
            cleaned = [str(x).strip() for x in v if str(x).strip()]
            if cleaned:
                existing = structured.get(k) if isinstance(structured.get(k), list) else []
                structured[k] = list(dict.fromkeys([*existing, *cleaned]))
                applied = True
    return applied


def embed_json(text: str, data: dict) -> str:
    """Append a fenced JSON block so the mentioned agent can read the sender's
    structured finding straight out of the Band message (context-through-Band)."""
    return f"{text}\n\n```json\n{json.dumps(data)}\n```"


def extract_jsons(content: str) -> list[dict]:
    """Pull any fenced JSON findings out of an inbound Band message's content."""
    out = []
    for m in _JSON_FENCE.findall(content or ""):
        try:
            out.append(json.loads(m))
        except json.JSONDecodeError:
            continue
    return out

# Map our UI message types -> Band event message_type.
_EVENT_TYPE = {
    "finding": "tool_result",
    "handoff": "thought",
    "draft": "tool_result",
    "veto": "error",
    "final_packet": "tool_result",
}


@dataclass
class AgentOutput:
    structured: dict
    summary: str
    ui_type: str = "finding"
    next_keys: list[str] = field(default_factory=list)
    include_human: bool = False
    handoff_text: str | None = None
    confidence: float | None = None


def publish(
    client: BandAgentClient | None,
    registry: dict[str, dict],
    chat_id: str,
    spec: config.AgentSpec,
    output: AgentOutput,
    embed_context: bool = False,
) -> AgentMessage:
    """Post the finding (event) + handoff (message) to Band; return the
    AgentMessage we rendered locally so the UI can show it immediately.

    If ``client`` is None (offline/dev mode), posting is skipped but the same
    AgentMessage is still returned so the pipeline can be exercised without Band.
    """
    conf = output.confidence
    if conf is None:
        conf = output.structured.get("confidence")

    # Resolve the @mention targets (works offline too, for the rendered card).
    mentioned_names: list[str] = []
    prefix, mentions = "", []
    if output.next_keys or output.include_human:
        prefix, mentions = build_mentions(output.next_keys, registry, output.include_human)
        mentioned_names = [m["name"] for m in mentions]

    if client is not None:
        # 1) Structured finding as a Band event (no mention required).
        try:
            client.post_event(
                chat_id,
                content=output.summary,
                message_type=_EVENT_TYPE.get(output.ui_type, "tool_result"),
                metadata={"structured_data": output.structured, "ui_type": output.ui_type,
                          "agent_key": spec.key},
            )
        except Exception as exc:  # keep the demo moving; surface in console
            print(f"[band] event post failed for {spec.name}: {exc}")

        # 2) Handoff message with @mentions (Band requires >=1 mention).
        if mentions:
            text = f"{prefix} {output.handoff_text or output.summary}".strip()
            if embed_context:
                # Carry the structured finding through Band so the mentioned
                # agent can consume upstream context directly from the message.
                text = embed_json(text, output.structured)
            try:
                client.post_message(chat_id, text, mentions)
            except Exception as exc:
                print(f"[band] message post failed for {spec.name}: {exc}")
                mentioned_names = []

    return AgentMessage(
        room_id=chat_id or "offline",
        agent_name=spec.name,
        message_type=output.ui_type,
        summary=output.summary,
        structured_data=output.structured,
        mentions=mentioned_names,
        confidence=conf,
    )
