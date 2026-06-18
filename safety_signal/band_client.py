"""Real Band platform client.

Three pieces, all hitting the real platform at app.band.ai:

* ``BandHumanClient``  — Human API (/me): register agents, create rooms, add
  participants, post/list messages. Used by the recall-manager (the human).
* ``BandAgentClient``  — Agent API (/agent): post messages/events, read room
  context. Each specialist agent owns one, keyed by its own agent API key.
* ``listen_ws`` / ``poll_messages`` — receive inbound messages for an agent,
  either over the Phoenix-Channels WebSocket (primary) or by REST polling
  (fallback). Both feed the same agent run loop.

``normalize_message`` converts a raw Band transcript row into our AgentMessage
shape for the investigation-room UI and the audit trail.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

import httpx

from . import config
from .schemas import AgentMessage


# ---------------------------------------------------------------------------
# REST clients
# ---------------------------------------------------------------------------
class _BaseRest:
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = (base_url or config.BAND_API_BASE_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=30,
        )

    def _req(self, method: str, path: str, **kw) -> Any:
        resp = self._client.request(method, path, **kw)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        payload = resp.json()
        # Band wraps responses in a {"data": ...} envelope; unwrap it.
        if isinstance(payload, dict) and "data" in payload and len(payload) <= 2:
            return payload["data"]
        return payload

    def close(self):
        self._client.close()


class BandHumanClient(_BaseRest):
    """Human-centric API (base /me). Auth = owner/human key."""

    def __init__(self, api_key: str = None):
        super().__init__(api_key or config.BAND_API_KEY)

    def profile(self) -> dict:
        return self._req("GET", "/me/profile")

    def list_agents(self) -> list[dict]:
        return _items(self._req("GET", "/me/agents"))

    def register_agent(self, name: str, handle: str = None, description: str = "") -> dict:
        """Register a remote agent. Returns the created agent incl. its api_key (once).

        Note: the API derives the handle from the name; it does not accept a
        ``handle`` field on registration, so we don't send one.
        """
        body = {"agent": {"name": name, "description": description}}
        return self._req("POST", "/me/agents/register", json=body)

    def delete_agent(self, agent_id: str) -> None:
        self._req("DELETE", f"/me/agents/{agent_id}")

    def list_chats(self) -> list[dict]:
        return _items(self._req("GET", "/me/chats"))

    def create_chat(self, title: str = None) -> dict:
        body = {"chat": {"title": title}} if title else {}
        return self._req("POST", "/me/chats", json=body)

    def add_participant(self, chat_id: str, participant_id: str) -> dict:
        return self._req(
            "POST", f"/me/chats/{chat_id}/participants",
            json={"participant": {"id": participant_id}},
        )

    def list_participants(self, chat_id: str) -> list[dict]:
        return _items(self._req("GET", f"/me/chats/{chat_id}/participants"))

    def post_message(self, chat_id: str, content: str, mentions: list[dict]) -> dict:
        return self._req(
            "POST", f"/me/chats/{chat_id}/messages",
            json={"message": {"content": content, "mentions": mentions}},
        )

    def list_messages(self, chat_id: str, status: str = "all") -> list[dict]:
        return _items(self._req("GET", f"/me/chats/{chat_id}/messages",
                                params={"status": status}))


class BandAgentClient(_BaseRest):
    """Agent-centric API (base /agent). Auth = that agent's key."""

    def __init__(self, api_key: str, agent_id: str = None):
        super().__init__(api_key)
        self.agent_id = agent_id

    def me(self) -> dict:
        return self._req("GET", "/agent/me")

    def list_chats(self) -> list[dict]:
        return _items(self._req("GET", "/agent/chats"))

    def create_chat(self, title: str = None, task_id: str = None) -> dict:
        chat = {}
        if title:
            chat["title"] = title
        if task_id:
            chat["task_id"] = task_id
        return self._req("POST", "/agent/chats", json={"chat": chat})

    def add_participant(self, chat_id: str, participant_id: str) -> dict:
        return self._req(
            "POST", f"/agent/chats/{chat_id}/participants",
            json={"participant": {"participant_id": participant_id}},
        )

    def list_participants(self, chat_id: str) -> list[dict]:
        return _items(self._req("GET", f"/agent/chats/{chat_id}/participants"))

    def get_context(self, chat_id: str) -> list[dict]:
        return _items(self._req("GET", f"/agent/chats/{chat_id}/context"))

    def list_messages(self, chat_id: str, status: str = "all") -> list[dict]:
        return _items(self._req("GET", f"/agent/chats/{chat_id}/messages",
                                params={"status": status}))

    def next_message(self, chat_id: str) -> dict | None:
        """Drain one backlog message (startup/recovery). None on 204."""
        return self._req("GET", f"/agent/chats/{chat_id}/messages/next")

    def post_message(self, chat_id: str, content: str, mentions: list[dict]) -> dict:
        return self._req(
            "POST", f"/agent/chats/{chat_id}/messages",
            json={"message": {"content": content, "mentions": mentions}},
        )

    def post_event(self, chat_id: str, content: str, message_type: str = "thought",
                   metadata: dict = None) -> dict:
        return self._req(
            "POST", f"/agent/chats/{chat_id}/events",
            json={"event": {"content": content, "message_type": message_type,
                            "metadata": metadata or {}}},
        )

    def mark_processing(self, chat_id: str, msg_id: str) -> None:
        self._req("POST", f"/agent/chats/{chat_id}/messages/{msg_id}/processing")

    def mark_processed(self, chat_id: str, msg_id: str) -> None:
        self._req("POST", f"/agent/chats/{chat_id}/messages/{msg_id}/processed")

    def mark_failed(self, chat_id: str, msg_id: str, error: str) -> None:
        self._req("POST", f"/agent/chats/{chat_id}/messages/{msg_id}/failed",
                  json={"error": error})


def _items(payload: Any) -> list[dict]:
    """Band list endpoints may wrap results; normalize to a plain list."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    for key in ("data", "results", "items", "messages", "participants", "agents", "chats"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return [payload]


# ---------------------------------------------------------------------------
# Mention helpers
# ---------------------------------------------------------------------------
def mention_for_agent(agent_key: str, registry: dict[str, dict]) -> dict | None:
    info = registry.get(agent_key)
    if not info:
        return None
    return {"id": info["agent_id"], "name": info["name"], "handle": info["handle"]}


def mention_for_human() -> dict | None:
    if not config.BAND_OWNER_USER_ID:
        return None
    return {
        "id": config.BAND_OWNER_USER_ID,
        "name": config.HUMAN_MANAGER_NAME,
        "handle": config.BAND_OWNER_HANDLE,
    }


def build_mentions(target_keys: list[str], registry: dict[str, dict],
                   include_human: bool = False) -> tuple[str, list[dict]]:
    """Return (mention_prefix_text, mentions_list) for a set of agent keys."""
    mentions: list[dict] = []
    for k in target_keys:
        m = mention_for_agent(k, registry)
        if m:
            mentions.append(m)
    if include_human:
        h = mention_for_human()
        if h:
            mentions.append(h)
    prefix = " ".join(f"@{m['name']}" for m in mentions)
    return prefix, mentions


# ---------------------------------------------------------------------------
# Transcript normalization (raw Band row -> AgentMessage)
# ---------------------------------------------------------------------------
def normalize_message(row: dict, room_id: str, registry: dict[str, dict]) -> AgentMessage:
    sender = row.get("sender") or row.get("author") or {}
    name = (sender.get("name") if isinstance(sender, dict) else None) \
        or row.get("sender_name") or row.get("agent_name") or "Unknown"

    structured = {}
    meta = row.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("structured_data"):
        structured = meta["structured_data"]
    elif isinstance(meta, dict) and meta:
        structured = meta

    mtype = _classify(row, structured)
    mentions = [m.get("name", "") for m in (row.get("mentions") or []) if isinstance(m, dict)]

    return AgentMessage(
        room_id=room_id,
        agent_name=name,
        message_type=mtype,
        summary=row.get("content", "") or "",
        structured_data=structured if isinstance(structured, dict) else {},
        mentions=mentions,
        confidence=(structured.get("confidence") if isinstance(structured, dict) else None),
        timestamp=row.get("inserted_at") or row.get("created_at") or row.get("timestamp") or "",
    )


def _classify(row: dict, structured: dict) -> str:
    """Map a Band row to one of our UI message types."""
    meta = row.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("ui_type"):
        return meta["ui_type"]
    mt = (row.get("message_type") or "").lower()
    if mt in ("tool_call", "tool_result", "thought") and structured:
        return "finding"
    if mt == "error":
        return "veto"
    return "finding"


# ---------------------------------------------------------------------------
# WebSocket listener (Phoenix Channels) — primary inbound path
# ---------------------------------------------------------------------------
async def listen_ws(
    agent_id: str,
    agent_key: str,
    room_ids: list[str],
    on_message: Callable[[dict], Awaitable[None]],
    stop: "asyncio.Event | None" = None,
) -> None:
    """Connect to Band over WebSocket and invoke ``on_message`` for each
    ``message_created`` event in the given rooms. Handles join + 30s heartbeat.
    """
    import ssl

    import certifi
    import websockets  # imported lazily so REST-only paths don't need it

    url = (f"{config.BAND_WS_URL}?api_key={agent_key}"
           f"&agent_id={agent_id}&vsn=2.0.0")
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    ref = {"n": 1}

    def nref() -> str:
        ref["n"] += 1
        return str(ref["n"])

    async with websockets.connect(url, ssl=ssl_ctx, max_size=None) as ws:
        # Join agent_rooms + each chat_room channel.
        await ws.send(json.dumps(["1", nref(), f"agent_rooms:{agent_id}", "phx_join", {}]))
        for rid in room_ids:
            await ws.send(json.dumps(["1", nref(), f"chat_room:{rid}", "phx_join", {}]))

        async def heartbeat():
            while not (stop and stop.is_set()):
                await asyncio.sleep(30)
                try:
                    await ws.send(json.dumps([None, nref(), "phoenix", "heartbeat", {}]))
                except Exception:
                    return

        hb = asyncio.create_task(heartbeat())
        try:
            while not (stop and stop.is_set()):
                raw = await ws.recv()
                try:
                    _join_ref, _ref, topic, event, payload = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if event == "message_created" and topic.startswith("chat_room:"):
                    rid = topic.split(":", 1)[1]
                    msg = payload.get("message", payload)
                    msg.setdefault("_room_id", rid)
                    await on_message(msg)
                elif event == "room_added" and topic.startswith("agent_rooms:"):
                    rid = (payload.get("room") or {}).get("id") or payload.get("room_id")
                    if rid:
                        await ws.send(json.dumps(["1", nref(), f"chat_room:{rid}",
                                                  "phx_join", {}]))
        finally:
            hb.cancel()


async def poll_messages(
    client: BandAgentClient,
    chat_id: str,
    on_message: Callable[[dict], Awaitable[None]],
    stop: "asyncio.Event | None" = None,
    interval: float = 1.5,
) -> None:
    """REST-polling fallback for inbound messages (drains /messages/next)."""
    while not (stop and stop.is_set()):
        try:
            msg = client.next_message(chat_id)
        except Exception:
            msg = None
        if msg:
            msg.setdefault("_room_id", chat_id)
            await on_message(msg)
        else:
            await asyncio.sleep(interval)
