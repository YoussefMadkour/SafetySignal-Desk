# SafetySignal Desk — 3-Minute Demo Script

_Band of Agents Hackathon · Track 3 (Regulated & High-Stakes) · secondary Track 1._

## The one-sentence pitch
> "SafetySignal Desk is a recall review room where **seven AI agents collaborate
> through Band** to investigate a product-safety complaint — and **a human makes
> the final call**, because in a regulated workflow no agent should be able to
> issue a recall on its own."

---

## What to demo (and on which screen)

**Demo BOTH — Streamlit is the cockpit, the Band web app is the proof.**

| Screen | Role in the demo |
|---|---|
| **Streamlit app** (`app.py`) | Primary narrative driver. Drives the review, shows agent findings as cards, the risk score, the **blocking** moment, the human decision, and the final packet. |
| **Band web app** (app.band.ai) | "This is real." A second tab/window showing the **same live room** fill up with each agent's events + @mention handoffs. Cut to it at the key moment. |

Lead with Streamlit. Cut to Band once, at the "agents are talking to each other"
beat, then come back to Streamlit for the human decision + packet.

> Why not the autonomous WS run (`run_agents --auto-approve`)? It's the most
> fragile path (live WebSocket timing) and currently flaky. The Streamlit
> sequenced run posts the **same real messages to the same real Band room** over
> REST — reliable, and you control the pacing. Keep `demo/replay.py` as an
> offline backup if the network dies.

---

## Pre-flight checklist (do this BEFORE you record / present)
1. `source .venv/bin/activate`
2. Confirm `.env` has `OPENAI_API_KEY` set and `LLM_PROVIDER=openai`, `OPENAI_MODEL=gpt-5.4-mini`.
3. `python -m scripts.selftest` → expect **"all checks passed ✅"** (proves LLM + guardrails).
4. `streamlit run app.py` → app on http://localhost:8501.
5. Log in to **app.band.ai** in a second browser tab; keep the rooms list visible.
6. In Streamlit sidebar, click **📂 Load Demo Case** so the case is pre-loaded (saves dead air).
7. Zoom browser to ~125% so cards/score are legible on video.

---

## The script (target 3:00)

### [0:00–0:25] Hook + stakes
- **[SAY]** "A protein bar batch is generating complaints. Some customers with
  peanut allergies are reporting reactions — but the label doesn't list peanuts.
  This is exactly the kind of high-stakes call where you want AI to investigate
  fast, but you cannot let it act alone."
- **[DO]** Streamlit showing the loaded case: complaint count, batch, the four
  input files. Point at "Recall precedents pulled **live from openFDA**."

### [0:25–1:15] The agents collaborate — through Band
- **[DO]** Click **▶️ Start Safety Review**. Point at the green
  **"Real Band room opened: `<id>`"** banner.
- **[SAY]** "Seven specialist agents now go to work, and they coordinate
  **through Band** — each is a real Band participant with its own identity. They
  hand off by @mentioning each other, and they pass structured findings as Band
  events."
- **[DO]** As cards appear, narrate the handoff chain:
  - *Complaint Intake* → extracts the facts (and an LLM reads the raw complaints).
  - *Pattern Detection* → "86% of complaints tie to one batch — that's a cluster."
  - *Label & Ingredient* → "The supplier sheet lists peanut flour; the label
    doesn't. **Undeclared allergen.**"
  - *Batch Trace* → "3,800 units still in market."
  - *Recall Precedent* → "Three **real** FDA Class I peanut recalls — same pattern."
- **[DO — THE BAND CUT]** Switch to the **Band web app**, open the room, scroll
  the agent messages + @mentions. **[SAY]** "This is the actual Band room — the
  agents are really talking to each other here, not in a log file."

### [1:15–2:00] The risk call + the block (Track-3 money shot)
- **[DO]** Back to Streamlit. Point at **Regulatory Risk: CRITICAL 100/100**.
- **[SAY]** "Here's the important design choice: the **score is computed
  deterministically** — a transparent 100-point rubric — so it's auditable and
  can't be hallucinated. The AI writes the *rationale*; it never writes the
  *number*."
- **[DO]** Point at the **⛔ Blocked by Regulatory Risk Agent — require human
  approval** banner and **"The AI cannot act without you."**
- **[SAY]** "The agents drafted the retailer hold notice and customer replies —
  but every one is marked **DRAFT**. Nothing gets sent. The system **blocks** and
  routes to me, the human recall manager."

### [2:00–2:40] Human decision + audit-grade output
- **[DO]** Click **Approve Batch Hold** (or your chosen decision).
- **[SAY]** "My decision is recorded back into Band, and the system generates an
  **audit-ready Safety Decision Packet**."
- **[DO]** Scroll the packet: the **score breakdown table**, the **real openFDA
  precedents**, the **AI reasoning**, and the **Reasoning Provenance** section.
- **[SAY]** "Every finding is labeled — deterministic vs AI-generated — and the
  whole conversation is preserved as the Band audit trail. That's what a
  regulated workflow needs: traceability, not a black box."

### [2:40–3:00] Close
- **[SAY]** "SafetySignal Desk: seven agents collaborating through Band, real
  public data, deterministic where it must be auditable, AI where judgment helps
  — and a human in control of the recall decision. Thank you."

---

## Wow moments (lean into these)
1. **The Band cut** — seeing the real room prove agent-to-agent collaboration.
2. **CRITICAL 100/100 + the block** — the system refuses to act; demands a human.
3. **Real openFDA precedents** — actual FDA recall numbers, not invented.
4. **The provenance line / selftest** — "we can *prove* the AI never moves a
   safety number." If you have 20 spare seconds, show
   `python -m scripts.selftest` output: 18 immutability checks all PASS.

## Likely judge questions — crisp answers
- **"Is Band just a notifier?"** → No. The @mention handoffs *are* the control
  flow; agents read each other's structured findings out of Band messages.
  Remove Band and the agents can't coordinate.
- **"Is the AI real or scripted?"** → Real: `gpt-5.4-mini` drives intake
  extraction, label reasoning, precedent summarization, the risk rationale, and
  the drafts — each with a deterministic fallback. The selftest proves it runs.
- **"What stops a hallucinated recall?"** → Numbers/decisions are deterministic
  Python; the LLM can only phrase. Drafts are DRAFT-only; the human approves.
- **"Why is the human relayed via an agent?"** → Band's Human API is
  Enterprise-gated (we're on Pro), so approval is relayed via an agent gateway —
  documented honestly in the README.

## If something breaks
- Streamlit/Band hiccup → run `python demo/replay.py` (offline, network-proof).
- LLM/network down → the agents fall back to deterministic output; the demo still
  runs and still scores CRITICAL 100/100 (just less rich language).
