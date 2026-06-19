"""Local live console for the autonomous (WebSocket) Band review.

Runs the REAL event-driven runtime — the 7 agents coordinate over Band's
WebSocket — and streams every agent message to the browser over Server-Sent
Events as Band delivers each @mention. No deployment: localhost only.

    python -m web.server          # then open http://localhost:8600

Requires Band configured + agents registered (agents.json), exactly like
`run_agents`. Falls back to an error banner in the page if Band isn't reachable.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from safety_signal import event_runtime
from safety_signal.case import load_case

HERE = Path(__file__).resolve().parent

# Each connected browser gets a queue; broadcasts fan out to all of them.
_subscribers: set[asyncio.Queue] = set()
_run = {"task": None}


def _broadcast(event: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except Exception:
            pass


async def _run_review() -> None:
    """Kick off the real autonomous review and stream its events out."""
    def log_cb(line: str) -> None:
        text = str(line)
        _broadcast({"type": "log", "text": text})
        if "Band room:" in text:
            _broadcast({"type": "room", "id": text.split("Band room:", 1)[1].strip()})

    def emit_cb(m) -> None:
        _broadcast({
            "type": "message",
            "agent": m.agent_name,
            "mtype": m.message_type,
            "summary": m.summary,
            "mentions": list(m.mentions or []),
            "structured": m.structured_data or {},
        })

    try:
        _broadcast({"type": "status", "text": "Opening Band room and recruiting agents…"})
        case = await asyncio.to_thread(load_case, None, True)
        _, chat_id, msgs = await event_runtime.run_event_driven(
            case, auto_approve=True, on_emit=emit_cb, log=log_cb, timeout=150.0,
        )
        _broadcast({"type": "done", "room": chat_id, "count": len(msgs)})
    except Exception as exc:  # surface to the page instead of dying silently
        _broadcast({"type": "error", "text": f"{type(exc).__name__}: {exc}"})


async def homepage(request: Request) -> FileResponse:
    return FileResponse(HERE / "index.html")


async def start(request: Request) -> JSONResponse:
    if _run["task"] and not _run["task"].done():
        return JSONResponse({"status": "already-running"})
    _run["task"] = asyncio.create_task(_run_review())
    return JSONResponse({"status": "started"})


async def events(request: Request) -> StreamingResponse:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)

    async def stream():
        try:
            yield "retry: 3000\n\n"
            yield f"data: {json.dumps({'type': 'hello'})}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # comment frame keeps the socket open
        finally:
            _subscribers.discard(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


app = Starlette(routes=[
    Route("/", homepage),
    Route("/start", start, methods=["POST"]),
    Route("/events", events),
])


if __name__ == "__main__":
    print("SafetySignal live console → http://localhost:8600")
    uvicorn.run(app, host="127.0.0.1", port=8600, log_level="warning")
