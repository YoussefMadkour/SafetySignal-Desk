# Example output

A real sample export from the demo case (**Cedar & Oat Cocoa Protein Bar, batch
CO-CPB-0426**), produced after the human recall manager approves a batch hold.
SafetySignal Desk writes these to `outputs/` at runtime (gitignored); the copies
here are committed as a reference.

| File | Description |
|---|---|
| `safety_decision_packet.md` | The Safety Decision Packet (Markdown). |
| `safety_decision_packet.pdf` | The same packet rendered as a PDF. |
| `audit_trail.json` | Every agent message and `@mention` handoff from the Band room, with structured findings, confidence, and timestamps. |

Numbers (risk score, counts, batch exposure, undeclared-allergen detection) are
deterministic; agent prose is LLM-generated and tagged `llm` vs `deterministic`
in the packet's *Reasoning Provenance* section.
