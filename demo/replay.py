#!/usr/bin/env python3
"""Offline, network-proof replay of the autonomous Band run — backup demo clip.

This reproduces the `python -m safety_signal.run_agents --auto-approve` terminal
experience with realistic pacing and color, WITHOUT touching Band or the network.
Use it to screen-record a backup clip, or as a live fallback if the venue blocks
WebSockets. It is purely cosmetic — the real system is in safety_signal/.

    python demo/replay.py            # play at demo speed
    python demo/replay.py --fast     # no delays (for quick capture)
"""
from __future__ import annotations

import sys
import time

FAST = "--fast" in sys.argv

# truecolor helpers
def c(rgb, s, bold=False):
    r, g, b = rgb
    b0 = "1;" if bold else ""
    return f"\x1b[{b0}38;2;{r};{g};{b}m{s}\x1b[0m"

DIM = lambda s: f"\x1b[2m{s}\x1b[0m"
INK = (230, 236, 245)
MUTED = (130, 145, 165)

AGENT = {
    "Complaint Intake Agent":               (37, 99, 235),
    "Pattern Detection Agent":              (124, 58, 237),
    "Label and Ingredient Agent":           (219, 39, 119),
    "Batch Trace Agent":                    (8, 145, 178),
    "Recall Precedent Agent":               (202, 138, 4),
    "Regulatory Risk Agent":                (220, 38, 38),
    "Customer and Retailer Response Agent": (13, 148, 136),
    "Human Recall Manager":                 (5, 150, 105),
}
TYPE_ICON = {"finding": "🔎", "handoff": "🤝", "veto": "⛔", "draft": "✉️",
             "human_action": "🧑‍⚖️"}


def pause(t):
    if not FAST:
        time.sleep(t)


def runtime(msg, t=0.5):
    print(DIM("[runtime] ") + c(MUTED, msg))
    pause(t)


def emit(agent, mtype, mentions, t=0.7):
    color = AGENT.get(agent, INK)
    icon = TYPE_ICON.get(mtype, "•")
    tag = c(color, f"[{mtype:>6}]", bold=True)
    name = c(color, agent, bold=True)
    arrow = ""
    if mentions:
        arrow = DIM("  →@ ") + DIM(", ".join(mentions))
    print(f"  {tag} {icon} {name}{arrow}")
    pause(t)


def banner():
    line = c((15, 118, 110), "━" * 66, bold=True)
    print(line)
    print(c(INK, "  🛡️  SafetySignal Desk", bold=True)
          + DIM("  · autonomous multi-agent run over Band"))
    print(DIM("  Cross-framework agents coordinating through real Band rooms"))
    print(line)
    pause(0.6)


def main():
    banner()
    print(c(INK, "Case: ") + c((202, 138, 4), "Cedar & Oat Cocoa Protein Bar / CO-CPB-0426")
          + DIM("  (openFDA live)"))
    print()
    pause(0.5)

    runtime("Band room: 55a9cb21-63c7-47b0-8a2d-3f07c5e41edd")
    for a in ["Pattern Detection Agent", "Label and Ingredient Agent", "Batch Trace Agent",
              "Recall Precedent Agent", "Regulatory Risk Agent",
              "Customer and Retailer Response Agent", "Human Recall Manager (human)"]:
        runtime(f"  + {a}", 0.18)
    runtime("Kickoff posted → @Complaint Intake Agent", 0.7)

    runtime("Complaint Intake Agent triggered (have: [])", 0.5)
    emit("Complaint Intake Agent", "finding",
         ["Pattern Detection Agent", "Label and Ingredient Agent"])

    runtime("Pattern Detection Agent triggered (have: ['complaint_intake'])", 0.3)
    runtime("Label and Ingredient Agent triggered (have: ['complaint_intake'])", 0.4)
    emit("Pattern Detection Agent", "handoff",
         ["Label and Ingredient Agent", "Batch Trace Agent", "Regulatory Risk Agent"])
    emit("Label and Ingredient Agent", "veto",
         ["Regulatory Risk Agent", "Recall Precedent Agent", "Batch Trace Agent"])

    runtime("Batch Trace Agent triggered (have: ['pattern_detection'])", 0.3)
    runtime("Recall Precedent Agent triggered (have: ['label_ingredient'])", 0.4)
    emit("Batch Trace Agent", "finding",
         ["Customer and Retailer Response Agent", "Regulatory Risk Agent"])
    emit("Recall Precedent Agent", "finding",
         ["Regulatory Risk Agent", "Customer and Retailer Response Agent"])

    runtime("Regulatory Risk Agent triggered "
            "(have: ['batch_trace', 'label_ingredient', 'pattern_detection', 'recall_precedent'])  "
            + c((220, 38, 38), "← converged", bold=True), 0.6)
    emit("Regulatory Risk Agent", "veto",
         ["Customer and Retailer Response Agent", "Human Recall Manager"])

    runtime("Customer and Retailer Response Agent triggered (have: ['regulatory_risk'])", 0.4)
    emit("Customer and Retailer Response Agent", "draft", ["Human Recall Manager"])

    runtime("Pipeline complete — drafts posted; awaiting human decision.", 0.7)
    runtime("Auto-approving as Recall Manager (demo mode).", 0.6)
    emit("Human Recall Manager", "human_action", ["Customer and Retailer Response Agent"])

    print()
    print(c(INK, "Room: ") + "55a9cb21-63c7-47b0-8a2d-3f07c5e41edd"
          + DIM("  |  messages emitted: 8"))
    risk = c((220, 38, 38), "CRITICAL (100/100)", bold=True)
    print(c(INK, "Risk: ") + risk + c(INK, " → HUMAN_REVIEW_REQUIRED"))
    print(DIM("Packet:  outputs/safety_decision_packet.md"))
    print(DIM("Audit:   outputs/audit_trail.json"))
    print()
    print(c((15, 118, 110), "View the live transcript in the Band web app (app.band.ai).", bold=True))


if __name__ == "__main__":
    main()
