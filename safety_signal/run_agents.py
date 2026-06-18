"""Event-driven entrypoint: 7 agents collaborate autonomously over Band.

    python -m safety_signal.run_agents                # run, stop at human gate
    python -m safety_signal.run_agents --auto-approve  # full autonomous loop + packet
    python -m safety_signal.run_agents --no-precedent-fetch  # use cached openFDA

Watch the room live in the Band web app (app.band.ai) while this runs — every
handoff, finding, and the human decision appear there in real time.
"""
from __future__ import annotations

import argparse
import asyncio

from . import config, event_runtime, report_generator
from .case import load_case
from .schemas import AgentMessage


def main() -> int:
    ap = argparse.ArgumentParser(description="Band event-driven multi-agent safety review.")
    ap.add_argument("--auto-approve", action="store_true",
                    help="Relay a Recall Manager approval and generate the packet.")
    ap.add_argument("--no-precedent-fetch", action="store_true",
                    help="Use cached openFDA precedents instead of a live fetch.")
    ap.add_argument("--timeout", type=float, default=150.0,
                    help="Seconds to wait for the agent pipeline to converge.")
    args = ap.parse_args()

    if not config.load_agent_registry():
        print("No registered agents. Run: python -m scripts.register_agents")
        return 1

    case = load_case(fetch_precedents=not args.no_precedent_fetch)
    print(f"Case: {case.product} / {case.batch_code} "
          f"(openFDA {'live' if case.precedents.get('_live') else 'cached'})\n")

    def on_emit(m: AgentMessage) -> None:
        arrow = f"  →@ {', '.join(m.mentions)}" if m.mentions else ""
        print(f"  [{m.message_type:6}] {m.agent_name}{arrow}")

    session, chat_id, msgs = asyncio.run(event_runtime.run_event_driven(
        case, auto_approve=args.auto_approve, on_emit=on_emit,
        log=lambda s: print(f"[runtime] {s}"), timeout=args.timeout,
    ))

    print(f"\nRoom: {chat_id}  |  messages emitted: {len(msgs)}")
    rr = session.state.regulatory_risk_summary or {}
    if rr:
        print(f"Risk: {rr.get('risk_level')} ({rr.get('risk_score')}/100) → {rr.get('decision')}")

    if args.auto_approve:
        pp, ap_path, md, _ = report_generator.write_outputs(
            session.state, case, session.messages, config.OUTPUTS_DIR, chat_id)
        session.post_final_packet(md)
        print(f"Packet:  {pp}\nAudit:   {ap_path}")

    print("\nView the live transcript in the Band web app (app.band.ai).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
