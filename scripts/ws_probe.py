"""Diagnostic: print every raw Band WebSocket frame an agent receives.

Connects as the Complaint Intake (coordinator) agent, opens a fresh room, has a
second agent post a message that @mentions the listener, and dumps every raw
frame for ~18s. Use this to see whether phx_join is accepted and what event
name/topic Band actually delivers messages under.

Run:  python -m scripts.ws_probe
"""
from __future__ import annotations

import asyncio
import json
import ssl

import certifi
import websockets

from safety_signal import config
from safety_signal.band_client import BandAgentClient, build_mentions


async def main() -> None:
    reg = config.load_agent_registry()
    if not reg:
        print("No agent registry (agents.json). Run scripts.register_agents first.")
        return

    listener = reg["complaint_intake"]
    poster_key = "regulatory_risk" if "regulatory_risk" in reg else \
        next(k for k in reg if k != "complaint_intake")
    poster = reg[poster_key]

    coord = BandAgentClient(listener["api_key"], listener["agent_id"])
    chat = coord.create_chat("WS PROBE")
    chat_id = chat.get("id") or (chat.get("chat") or {}).get("id")
    print(f"room: {chat_id}")
    coord.add_participant(chat_id, poster["agent_id"])
    print(f"added poster: {poster['name']}")

    url = (f"{config.BAND_WS_URL}?api_key={listener['api_key']}"
           f"&agent_id={listener['agent_id']}&vsn=2.0.0")
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    ref = {"n": 1}

    def nref() -> str:
        ref["n"] += 1
        return str(ref["n"])

    async with websockets.connect(url, ssl=ssl_ctx, max_size=None) as ws:
        await ws.send(json.dumps(["1", nref(), f"agent_rooms:{listener['agent_id']}",
                                  "phx_join", {}]))
        await ws.send(json.dumps(["1", nref(), f"chat_room:{chat_id}", "phx_join", {}]))
        print("sent phx_join for agent_rooms + chat_room")

        async def post_later():
            await asyncio.sleep(4)
            pc = BandAgentClient(poster["api_key"], poster["agent_id"])
            prefix, mentions = build_mentions(["complaint_intake"], reg)
            pc.post_message(chat_id, f"{prefix} PROBE PING — do you receive this?", mentions)
            print(">>> poster posted an @mention message")

        asyncio.create_task(post_later())

        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=18)
                print("FRAME:", raw[:600])
        except asyncio.TimeoutError:
            print("\n(no more frames — 18s elapsed)")


if __name__ == "__main__":
    asyncio.run(main())
