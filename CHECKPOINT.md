# SafetySignal Desk — Checkpoint (resume here)

_Last updated: 2026-06-19. This is a continuity doc so a new chat can pick up without re-deriving context._

## What this project is
Band-powered product-safety **recall review room**. 7 specialist agents + a human
recall manager collaborate **through real Band** on a fictional **Cedar & Oat Foods**
undeclared-peanut case (batch **CO-CPB-0426**). Output: an audit-ready Safety Decision
Packet + Band-transcript audit trail. Hackathon: "Band of Agents" — Track 3 (Regulated),
secondary Track 1. Min req (≥3 agents collaborating through Band) is exceeded.

Location: `~/Documents/KourysApps/SafetySignal`  ·  venv: `.venv`  ·  Python 3.12.

## Status: WORKING end-to-end (real Band)
- ✅ 7 agents registered on Band (`agents.json`, gitignored). Owner UUID `64798b17-…`.
- ✅ **Event-driven mode** (`python -m safety_signal.run_agents --auto-approve`): agents are
  WebSocket listeners; Band delivers @mentions; agents read upstream findings from the
  Band message (JSON embedded in handoffs); Regulatory Risk converges on {label,batch,recall}.
  Verified live multiple times. Risk = CRITICAL 100/100.
- ✅ **Sequenced mode** (Streamlit `app.py`): reliable human console + fallback (REST only, no WS).
- ✅ openFDA precedents are REAL (live fetch + cache fallback; cache has real FDA records).
- ✅ Streamlit visuals upgraded (Bricolage Grotesque + IBM Plex Sans/Mono, gradient bg, entrance anim).
- ✅ Backup clip: `demo/replay.py` (offline, network-proof) + `demo/autonomous_run.log`.
- ✅ Public repo: **github.com/YoussefMadkour/SafetySignal-Desk** (SSH, personal acct; NO secrets committed).

## Run it
```bash
source .venv/bin/activate
python -m safety_signal.run_agents --auto-approve   # autonomous Band demo (watch app.band.ai)
streamlit run app.py                                # human console  (currently running on :8501)
python demo/replay.py                               # offline backup clip
```

## ✅ LLM / "AI" is NOW ACTIVE (done 2026-06-19)
- `LLM_PROVIDER=openai`, `OPENAI_API_KEY` set in `.env` (gpt-4o-mini). `llm_enabled()=True`.
- LLM wired into the **5 language agents** with deterministic fallback, all verified live:
  Complaint Intake (`intake_summary`+symptom/allergen extraction), Label & Ingredient
  (`analysis`+evidence grounded in real label/supplier text), Recall Precedent
  (`precedent_analysis`+`recommended_language`), Regulatory Risk (`reason` rationale only),
  Customer Response (4 drafts). Batch Trace + Pattern Detection stay fully deterministic.
- **Design = deterministic computes truth, LLM only produces language.** Numbers/decisions
  (score, level, decision, counts, exposure, undeclared-allergen set-diff) are NEVER model-set.
  Shared guardrail: `base.SAFETY_PREAMBLE` + `base.apply_narrative()` (overlays only whitelisted
  language fields; unions list fields). Each finding tagged `reasoning_mode: llm|deterministic`.
- Verified: LLM path keeps risk pinned at **CRITICAL 100/100**, narratives grounded (no
  hallucinated numbers/firms). Deterministic fallback (blank key) also still 100/100.
- Band is unaffected: Band does NOT proxy LLMs ("bring your own provider") — our agents call
  OpenAI directly. The OpenAI provider added in Band's UI powers Band-native features only.
- **Output packet upgraded to audit-grade** (`report_generator.build_packet`): now surfaces the
  AI reasoning, the 100-pt score breakdown table, real openFDA precedent records, policy
  triggers, all 4 drafts, and a Reasoning Provenance (AI-vs-deterministic) section.

## ⚠️ OPEN ITEM — autonomous WebSocket run is currently BROKEN (found 2026-06-19)
- `run_agents --auto-approve` creates the room + recruits all 7 + human + posts kickoff
  (REST all fine, room visible in app.band.ai) but **WS listeners never pick up the kickoff**
  → "agents reached: []", times out after 150s. Agents never execute.
- NOT caused by the LLM work (agents never ran). REST auth is fine. Suspect: Band key rotation
  (checkpoint flagged it) OR Band-side change to how events vs messages push over the socket
  (kickoff is posted via `post_event`/events endpoint, not a message with mentions — check
  whether WS delivers events to agents). Needs debugging in `event_runtime.py` / `band_client` WS.
- **Demo does NOT depend on this.** Streamlit sequenced mode posts the same real messages to
  the same real Band room via REST (reliable). Offline backup: `demo/replay.py`.

## Model + testing (2026-06-19)
- Using **`gpt-5.4-mini`** (`OPENAI_MODEL` in `.env`). Probed all candidates: 4o-mini, 5.4-mini,
  5.4-nano all work with our client (temperature + JSON mode OK, ~1.3s). Picked 5.4-mini for
  best grounded-rationale quality + 2025 knowledge cutoff; cost negligible at demo token volume.
- **`python -m scripts.selftest`** — dependency-free integration test, 49 checks PASS. Proves:
  ground truth correct, **LLM changes zero audited numbers** (18 immutability checks), language
  agents engage (`reasoning_mode==llm`), drafts safe, packet builds with audit sections.
- Demo script: **`demo/DEMO_SCRIPT.md`** (3-min, Streamlit cockpit + Band web-app proof cut).

## Key platform facts (don't re-discover)
- Band **Human API (`/me/...`) is Enterprise-gated**; user is on **Pro** → only `/me/profile` + `/me/agents` work.
  Runtime uses **Agent API** (`/agent/...`) entirely. Human approval is **relayed via an agent gateway**
  (a `human_action` event attributed to the recall manager) — documented honestly in README.
- Band quirks: responses wrapped in `{"data":...}`; register key at `data.credentials.api_key`;
  create chat `{"chat":{}}`; add participant `{"participant":{"participant_id":ID}}`; messages need
  @mentions of existing participants; register rejects a `handle` field.
- WebSocket needs certifi SSL ctx on macOS (`ssl.create_default_context(cafile=certifi.where())`).
- Band key (`band_u_…`) is in `.env`; user said they'd rotate it — if broken, that's why.

## Deploy (Streamlit Community Cloud) — prepared, not yet clicked
- One-click: https://share.streamlit.io/deploy?repository=YoussefMadkour/SafetySignal-Desk&branch=main&mainModule=app.py
- Paste the contents of local `.streamlit/secrets.toml` (gitignored; has real Band key + owner +
  `BAND_AGENTS_JSON` registry) into the app's Secrets box. `config.load_agent_registry()` reads
  `BAND_AGENTS_JSON`; `app.py` bridges `st.secrets`→`os.environ`.

## File map
- `safety_signal/`: `config.py`, `band_client.py` (REST+WS), `event_runtime.py` (WS coordination),
  `orchestrator.py` (sequenced), `agents/*` (7 + base), `scoring.py`, `case.py`, `data_loaders.py`,
  `openfda.py`, `llm_client.py`, `report_generator.py`, `run_agents.py`.
- `scripts/register_agents.py`, `scripts/fetch_openfda.py`.
- `data/demo_case/*` (synthetic), `data/public_recall_examples/*` (real openFDA cache).
- `app.py` (Streamlit), `demo/` (backup clip), `outputs/` (generated packet + audit).

## Suggested next steps (in order)
1. ✅ DONE — LLM wired into the 5 language agents + audit-grade packet (2026-06-19).
2. Run the full autonomous Band demo with LLM active (`run_agents --auto-approve`) and confirm
   the live Band-room handoffs still converge (was verified pre-LLM; re-verify with LLM on).
3. Click-deploy to Streamlit Cloud; paste secrets (incl. `OPENAI_API_KEY`); confirm public URL.
4. Record the backup clip from `demo/replay.py`; write the 3-min submission script.
5. (Optional) `--transport poll` WS-free fallback for `run_agents`.
