"""SafetySignal Desk — Streamlit recall-manager console.

Single-page app: load the Cedar & Oat Foods demo case, start a Band-coordinated safety
review, watch the 7 agents post into the investigation room, review the evidence
board, approve/reject as the human recall manager, then export the Safety
Decision Packet and the Band audit trail.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

# On Streamlit Community Cloud, secrets are provided via st.secrets. Bridge them
# into the environment BEFORE importing safety_signal (config reads os.environ).
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float, bool)):
            os.environ.setdefault(_k, str(_v))
except Exception:
    pass  # no secrets.toml locally — .env / process env are used instead

from safety_signal import config
from safety_signal.case import load_case
from safety_signal.orchestrator import ReviewSession
from safety_signal import report_generator as rg

st.set_page_config(page_title="SafetySignal Desk", page_icon="🛡️", layout="wide")

DISCLAIMER = (
    "SafetySignal Desk is a decision-support prototype. It does not provide legal, "
    "medical, or regulatory advice and does not automatically issue recalls, public "
    "notices, or regulatory filings. All high-stakes actions require human approval."
)

# message type -> (emoji, label background, label text color) — warm console palette
TYPE_STYLE = {
    "finding":      ("🔎", "rgba(47,83,83,0.10)",   "#2F5353"),
    "handoff":      ("🤝", "rgba(104,144,143,0.16)", "#3c605f"),
    "challenge":    ("⚠️", "rgba(205,157,92,0.16)",  "#a9772f"),
    "veto":         ("⛔", "rgba(156,66,33,0.14)",   "#9c4221"),
    "draft":        ("✉️", "rgba(47,83,83,0.08)",    "#213C43"),
    "human_action": ("🧑‍⚖️", "rgba(43,73,52,0.12)",  "#2B4934"),
    "final_packet": ("📦", "rgba(216,201,177,0.35)", "#5B6763"),
}

# per-agent avatar initials + accent color — tones drawn from the console palette
AGENT_META = {
    "Complaint Intake Agent":                ("CI", "#2F5353"),
    "Pattern Detection Agent":               ("PD", "#68908F"),
    "Label and Ingredient Agent":            ("LI", "#a9772f"),
    "Batch Trace Agent":                     ("BT", "#213C43"),
    "Recall Precedent Agent":                ("RP", "#8a6a3a"),
    "Regulatory Risk Agent":                 ("RR", "#9c4221"),
    "Customer and Retailer Response Agent":  ("CR", "#2B4934"),
    "Human Recall Manager":                  ("RM", "#3d6b4a"),
}

RISK_COLOR = {"LOW": "#2B4934", "MEDIUM": "#CD9D5C", "HIGH": "#a9772f", "CRITICAL": "#9c4221"}

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');
      :root{ --page:#FAF4E8; --card:#FEFBF5; --ink:#162526; --muted:#5B6763;
        --teal:#2F5353; --teal-deep:#213C43; --green:#2B4934;
        --amber:#CD9D5C; --amber-deep:#a9772f;
        --amber-dim:rgba(205,157,92,0.14); --teal-dim:rgba(47,83,83,0.07); --green-dim:rgba(43,73,52,0.10);
        --line:rgba(165,167,160,0.45); --line-strong:rgba(91,103,99,0.32); --accent:#2F5353;
        --font:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
        --display:'Archivo Black','Arial Black',system-ui,sans-serif;
        --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,monospace; }
      .stApp{ background:var(--page); }
      .stApp, .stApp p, .stApp li, .stApp label, .stApp .stMarkdown,
      .stApp .stButton button, .stApp textarea, .stApp input{ font-family:var(--font); }
      .block-container{ padding-top:1.4rem; max-width:1180px; }
      h1,h2,h3,h4{ color:var(--ink); font-family:var(--display); text-transform:uppercase;
        letter-spacing:0; }
      @keyframes ssRise{ from{opacity:0; transform:translateY(10px)} to{opacity:1; transform:none} }

      /* ---- header banner ---- */
      .ss-header{ background:var(--card); border:1px solid var(--line);
        border-radius:16px; padding:20px 26px; color:var(--ink); display:flex;
        align-items:center; justify-content:space-between; flex-wrap:wrap; gap:14px;
        box-shadow:0 6px 16px rgba(22,37,38,0.04); margin-bottom:6px;
        animation:ssRise .6s ease both; }
      .ss-header-main{ display:flex; align-items:center; gap:16px; }
      .ss-logo{ font-size:2.0rem; line-height:1; }
      .ss-title{ font-family:var(--display); text-transform:uppercase; font-size:1.55rem;
        line-height:1; color:var(--ink); }
      .ss-sub{ color:var(--muted); font-size:11px; font-weight:600; letter-spacing:0.16em;
        text-transform:uppercase; margin-top:6px; }
      .ss-header-side{ display:flex; flex-direction:column; gap:8px; align-items:flex-end; }
      .ss-chip{ display:inline-flex; align-items:center; gap:8px; padding:6px 14px; border-radius:999px;
        font-size:11px; font-weight:600; letter-spacing:0.12em; text-transform:uppercase; white-space:nowrap;
        border:1px solid var(--line-strong); }
      .ss-chip-case{ background:var(--card); color:var(--muted); font-family:var(--mono);
        letter-spacing:0.04em; text-transform:none; }
      .ss-chip-on{ background:var(--green-dim); color:var(--green); border-color:var(--green); }
      .ss-chip-off{ background:var(--amber-dim); color:var(--amber-deep); border-color:var(--amber); }

      /* ---- section labels ---- */
      .ss-sec{ display:flex; align-items:center; gap:12px; margin:28px 0 14px; }
      .ss-sec h3{ margin:0; font-size:1.0rem; color:var(--teal); }
      .ss-sec .ss-rule{ flex:1; height:1px; background:var(--line); }

      /* ---- timeline cards ---- */
      .ss-row{ display:flex; gap:12px; align-items:flex-start; margin-bottom:10px;
        animation:ssRise .45s cubic-bezier(.21,.6,.35,1) both; }
      .ss-avatar{ flex:none; width:38px; height:38px; border-radius:50%; color:#fff;
        font-weight:700; font-size:0.82rem; display:flex; align-items:center;
        justify-content:center; box-shadow:0 2px 6px rgba(22,37,38,.12); margin-top:2px; }
      .ss-card{ flex:1; border:1px solid var(--line); border-left:3px solid var(--c,var(--teal));
        border-radius:12px; padding:12px 16px; background:var(--card);
        box-shadow:0 6px 16px rgba(22,37,38,0.03); }
      .ss-card-top{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
      .ss-agent{ font-weight:700; font-size:0.95rem; color:var(--ink); }
      .ss-pill{ padding:2px 9px; border-radius:5px; font-size:0.66rem; font-weight:700;
        text-transform:uppercase; letter-spacing:.08em; }
      .ss-conf{ margin-left:auto; color:var(--muted); font-size:0.74rem; font-family:var(--mono); }
      .ss-summary{ margin-top:6px; font-size:0.9rem; line-height:1.5; color:var(--ink); }
      .ss-ments{ margin-top:8px; display:flex; gap:6px; flex-wrap:wrap; }
      .ss-ment{ background:var(--teal-dim); color:var(--teal); border:1px solid var(--line); border-radius:6px;
        padding:1px 7px; font-size:0.72rem; font-weight:600; }

      /* ---- risk banner + gauge ---- */
      .ss-risk{ display:flex; gap:22px; align-items:center; background:var(--card); border:1px solid var(--line);
        border-radius:16px; padding:18px 22px; box-shadow:0 6px 16px rgba(22,37,38,0.03);
        animation:ssRise .5s ease both; }
      .ss-gauge{ width:118px; height:118px; border-radius:50%; display:flex; align-items:center;
        justify-content:center; flex:none; }
      .ss-gauge-hole{ width:88px; height:88px; border-radius:50%; background:var(--card); display:flex;
        flex-direction:column; align-items:center; justify-content:center; }
      .ss-gauge-score{ font-family:var(--display); font-size:1.9rem; line-height:1; color:var(--ink); }
      .ss-gauge-of{ font-family:var(--mono); font-size:0.72rem; color:var(--muted); margin-top:2px; }
      .ss-risk-info{ flex:1; }
      .ss-risk-level{ display:inline-block; padding:3px 12px; border-radius:999px; color:#fff;
        font-weight:700; font-size:0.78rem; letter-spacing:.06em; text-transform:uppercase; }
      .ss-risk-decision{ font-size:1.15rem; font-weight:700; color:var(--ink); margin-top:8px; }
      .ss-risk-meta{ color:var(--muted); font-size:0.85rem; margin-top:3px; }

      /* ---- evidence grid ---- */
      .ss-grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:12px; }
      .ss-tile{ border:1px solid var(--line); border-top:3px solid var(--a,var(--teal)); border-radius:12px;
        padding:14px 16px; background:var(--card); box-shadow:0 6px 16px rgba(22,37,38,0.03);
        animation:ssRise .5s ease both; }
      .ss-tile-ic{ font-size:1.1rem; }
      .ss-tile-label{ text-transform:uppercase; letter-spacing:.05em; font-size:0.7rem;
        color:var(--muted); font-weight:700; margin-top:4px; }
      .ss-tile-val{ font-family:var(--display); font-size:1.4rem; color:var(--ink); margin-top:4px; line-height:1.1; }
      .ss-tile-sub{ font-size:0.8rem; color:var(--muted); margin-top:4px; line-height:1.4; }
      @media (max-width:820px){ .ss-grid{ grid-template-columns:1fr; } }

      /* ---- buttons ---- */
      .stButton>button{ border-radius:8px; font-weight:700; border:1px solid var(--line-strong);
        background:var(--card); color:var(--ink); }
      .stButton>button:hover{ background:#fff; border-color:var(--teal); }
      .stButton>button[kind="primary"]{ background:var(--teal); color:#fff; border-color:var(--teal); }
      .stButton>button[kind="primary"]:hover{ background:var(--teal-deep); border-color:var(--teal-deep); }
      div[data-testid="stSidebar"] .stButton>button{ border:1px solid var(--line-strong); }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("phase", "idle")        # idle -> loaded -> reviewed -> decided
ss.setdefault("case", None)
ss.setdefault("session", None)
ss.setdefault("messages", [])
ss.setdefault("packet_md", None)
ss.setdefault("audit", None)


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------
def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _avatar(name: str):
    if name in AGENT_META:
        return AGENT_META[name]
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    return initials, "#475569"


def render_card(msg):
    icon, pill_bg, pill_fg = TYPE_STYLE.get(msg.message_type, ("•", "#e2e8f0", "#334155"))
    initials, color = _avatar(msg.agent_name)
    conf = f"confidence {msg.confidence:.2f}" if msg.confidence is not None else ""
    ments = ""
    if msg.mentions:
        ments = "<div class='ss-ments'>" + "".join(
            f"<span class='ss-ment'>→ @{_esc(m)}</span>" for m in msg.mentions) + "</div>"
    st.markdown(
        f"<div class='ss-row'>"
        f"<div class='ss-avatar' style='background:{color}'>{initials}</div>"
        f"<div class='ss-card' style='--c:{color}'>"
        f"<div class='ss-card-top'>"
        f"<span class='ss-agent'>{_esc(msg.agent_name)}</span>"
        f"<span class='ss-pill' style='background:{pill_bg};color:{pill_fg}'>{icon} {msg.message_type}</span>"
        f"<span class='ss-conf'>{conf}</span></div>"
        f"<div class='ss-summary'>{_esc(msg.summary)}</div>{ments}"
        f"</div></div>",
        unsafe_allow_html=True,
    )
    if msg.structured_data:
        with st.expander("structured evidence (JSON)"):
            st.json(msg.structured_data)


def section(title: str):
    st.markdown(f"<div class='ss-sec'><h3>{title}</h3><div class='ss-rule'></div></div>",
                unsafe_allow_html=True)


def gauge_html(score, level, color) -> str:
    try:
        pct = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        pct = 0
    deg = pct * 3.6
    return (
        f"<div class='ss-gauge' style='background:conic-gradient({color} {deg}deg,#eef1f5 0)'>"
        f"<div class='ss-gauge-hole'>"
        f"<div class='ss-gauge-score' style='color:{color}'>{score}</div>"
        f"<div class='ss-gauge-of'>/ 100</div></div></div>"
    )


def tile(icon, label, value, sub, accent) -> str:
    return (f"<div class='ss-tile' style='--a:{accent}'>"
            f"<div class='ss-tile-ic'>{icon}</div>"
            f"<div class='ss-tile-label'>{_esc(label)}</div>"
            f"<div class='ss-tile-val'>{value}</div>"
            f"<div class='ss-tile-sub'>{sub}</div></div>")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
band_ready = bool(config.BAND_API_KEY and config.load_agent_registry())
band_chip = ("<span class='ss-chip ss-chip-on'>● Real Band connected</span>" if band_ready
             else "<span class='ss-chip ss-chip-off'>● Local preview mode</span>")
st.markdown(
    f"<div class='ss-header'>"
    f"<div class='ss-header-main'><div class='ss-logo'>🛡️</div>"
    f"<div><div class='ss-title'>SafetySignal Desk</div>"
    f"<div class='ss-sub'>From scattered complaints to recall-ready decisions</div></div></div>"
    f"<div class='ss-header-side'>"
    f"<span class='ss-chip ss-chip-case'>{_esc(config.PRODUCT)} · {config.BATCH_CODE}</span>"
    f"{band_chip}</div></div>",
    unsafe_allow_html=True,
)
if not band_ready:
    st.caption("Set `BAND_API_KEY` and run `python -m scripts.register_agents` to use the real Band room.")

# ---------------------------------------------------------------------------
# Input panel
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🗂️ Case Inputs")
    st.caption("Synthetic Cedar & Oat Foods case data. Recall precedents are pulled live from openFDA.")
    with st.expander("Optional: upload your own files"):
        up_complaints = st.file_uploader("Complaints CSV", type="csv")
        up_label = st.file_uploader("Consumer label", type="txt")
        up_supplier = st.file_uploader("Supplier ingredient sheet", type="txt")
        up_batch = st.file_uploader("Batch distribution CSV", type="csv")
        up_policy = st.file_uploader("Company policy", type="txt")
    st.divider()
    load_clicked = st.button("📂 Load Demo Case", use_container_width=True)
    start_clicked = st.button("▶️ Start Safety Review", type="primary",
                              use_container_width=True,
                              disabled=ss.phase == "idle")
    if st.button("🔄 Reset", use_container_width=True):
        for k in ("phase", "case", "session", "messages", "packet_md", "audit"):
            ss[k] = "idle" if k == "phase" else (None if k != "messages" else [])
        st.rerun()
    st.divider()
    st.caption("Tip: for the autonomous Band demo run "
               "`python -m safety_signal.run_agents --auto-approve` and watch app.band.ai.")


def _uploads():
    out = {}
    for key, f in (("complaints", up_complaints), ("label", up_label),
                   ("supplier", up_supplier), ("batch", up_batch), ("policy", up_policy)):
        if f is not None:
            out[key] = f.getvalue()
    return out


if load_clicked:
    with st.spinner("Loading case files and fetching real openFDA recall precedents…"):
        ss.case = load_case(uploads=_uploads(), fetch_precedents=True)
    ss.phase = "loaded"
    ss.messages = []
    ss.session = None
    ss.packet_md = None
    # Rerun so the "Start Safety Review" button (rendered above, before this block)
    # re-evaluates its disabled state now that the case is loaded.
    st.rerun()

# ---------------------------------------------------------------------------
# Loaded case overview
# ---------------------------------------------------------------------------
if ss.case is not None:
    case = ss.case
    with st.expander("📋 Loaded case data", expanded=(ss.phase == "loaded")):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Complaints", case.facts.complaint_count)
        m2.metric("On batch " + case.batch_code, case.facts.target_batch_count)
        m3.metric("Units still in market", f"{case.exposure.units_in_inventory:,}")
        live = case.precedents.get("_live")
        m4.metric("openFDA precedents",
                  f"{len(case.precedents.get('results', []))}", "live" if live else "cached")
        st.dataframe(pd.DataFrame([vars(c) for c in case.complaints]), use_container_width=True,
                     height=220)
        cc1, cc2 = st.columns(2)
        cc1.text_area("Consumer label", case.label_text, height=170)
        cc2.text_area("Supplier ingredient sheet", case.supplier_text, height=170)

# ---------------------------------------------------------------------------
# Run the review
# ---------------------------------------------------------------------------
if start_clicked and ss.case is not None:
    sess = ReviewSession(case=ss.case, online=True, step_delay=0.7)
    ss.session = sess
    section("🏛️ Band Investigation Room")
    if sess.online:
        with st.spinner("Opening Band room and recruiting agents…"):
            room = sess.setup_room()
        st.success(f"Real Band room opened: `{room}`")
        with st.expander("Band room setup log"):
            for line in sess.setup_log:
                st.write(line)
    else:
        st.warning("Local preview mode — agent coordination is shown but not posted to Band.")
    room_box = st.container()
    msgs = []
    with room_box:
        for msg in sess.run_pipeline():
            render_card(msg)
            msgs.append(msg)
    ss.messages = msgs
    ss.phase = "reviewed"

# Re-render the timeline after reruns (decision phase).
elif ss.phase in ("reviewed", "decided") and ss.messages:
    section("🏛️ Band Investigation Room")
    for msg in ss.messages:
        render_card(msg)

# ---------------------------------------------------------------------------
# Evidence board
# ---------------------------------------------------------------------------
if ss.phase in ("reviewed", "decided") and ss.session is not None:
    state = ss.session.state
    case = ss.case
    section("🧩 Evidence Board")

    rr = state.regulatory_risk_summary or {}
    level = rr.get("risk_level", "CRITICAL")
    score = rr.get("risk_score", "—")
    color = RISK_COLOR.get(level, "#dc2626")
    decision = rr.get("decision", "HUMAN_REVIEW_REQUIRED")
    triggers = rr.get("policy_triggers", [])
    ps = state.pattern_summary or {}
    signal = ps.get("signal_strength", "HIGH")

    st.markdown(
        f"<div class='ss-risk'>{gauge_html(score, level, color)}"
        f"<div class='ss-risk-info'>"
        f"<span class='ss-risk-level' style='background:{color}'>{level} RISK</span>"
        f"<div class='ss-risk-decision'>{_esc(decision.replace('_',' ').title())}</div>"
        f"<div class='ss-risk-meta'>{len(triggers)} company-policy escalation triggers fired"
        f" · cluster signal {_esc(signal)} · awaiting human recall manager</div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    ls = state.label_summary or {}
    bs = state.batch_trace_summary or {}
    rp = state.recall_precedent_summary or {}
    actions = rr.get("recommended_actions", [])
    tiles = [
        tile("🧪", "Complaint Cluster", f"Signal {signal}",
             _esc(ps.get("cluster_reason", "")), "#7c3aed"),
        tile("🏷️", "Label Mismatch", f"Undeclared: {_esc(ls.get('undeclared_allergen', '—'))}",
             f"Label: {_esc(', '.join(ls.get('consumer_label_allergens', [])))}<br>"
             f"Supplier: {_esc(', '.join(ls.get('supplier_sheet_allergens', [])))}", "#db2777"),
        tile("📦", "Batch Exposure", f"{bs.get('units_in_inventory', 0):,} units in market",
             f"{len(bs.get('retailers_affected', []))} retailers · "
             f"{_esc(', '.join(bs.get('locations_affected', [])))}", "#0891b2"),
        tile("📚", "Public Recall Precedent", f"Match: {_esc(rp.get('precedent_match', '—'))}",
             f"{len(rp.get('similar_recall_patterns', []))} real FDA records "
             f"({'live' if rp.get('data_is_live') else 'cached'})", "#ca8a04"),
        tile("⚖️", "Regulatory Risk", f"{level} · {score}/100",
             "".join(f"• {_esc(t)}<br>" for t in triggers[:3]), "#dc2626"),
        tile("✅", "Recommended Actions", f"{len(actions)} actions",
             "".join(f"• {_esc(a)}<br>" for a in actions[:4]), "#0d9488"),
    ]
    st.markdown(f"<div class='ss-grid'>{''.join(tiles)}</div>", unsafe_allow_html=True)

    blocked = rr.get("blocked_actions", [])
    if blocked:
        st.error("⛔ **Blocked by Regulatory Risk Agent — require human approval:**\n\n"
                 + "\n".join(f"- {b}" for b in blocked))

# ---------------------------------------------------------------------------
# Human decision panel
# ---------------------------------------------------------------------------
if ss.phase == "reviewed" and ss.session is not None:
    section("🧑‍⚖️ Human Recall Manager Decision")
    st.markdown("**The AI cannot act without you.** Review the evidence above, then choose how to proceed.")
    notes = st.text_area(
        "Decision notes (recorded in the Band audit trail)",
        "Approve immediate batch hold and retailer notification. "
        "Prepare recall packet for QA, legal, and regulatory review.",
        height=80,
    )
    cols = st.columns(5)
    buttons = [
        ("✅ Approve Batch Hold", "APPROVE_BATCH_HOLD", "primary"),
        ("📑 Request Evidence", "REQUEST_MORE_EVIDENCE", "secondary"),
        ("📦 Prepare Recall Packet", "PREPARE_RECALL_PACKET", "secondary"),
        ("👁️ Monitor Only", "MONITOR_ONLY", "secondary"),
        ("❌ Reject", "REJECT_RECOMMENDATION", "secondary"),
    ]
    for col, (label, code, kind) in zip(cols, buttons):
        if col.button(label, use_container_width=True, type=kind):
            sess = ss.session
            sess.submit_decision(code, notes)
            pp, ap, md, audit = rg.write_outputs(
                sess.state, ss.case, sess.messages, config.OUTPUTS_DIR, sess.chat_id)
            sess.post_final_packet(md)
            ss.messages = sess.messages
            ss.packet_md = md
            ss.audit = audit
            ss.phase = "decided"
            st.rerun()

# ---------------------------------------------------------------------------
# Final packet + exports
# ---------------------------------------------------------------------------
if ss.phase == "decided" and ss.packet_md:
    section("📦 Safety Decision Packet")
    d = (ss.session.state.human_decision or {})
    st.success(f"Decision recorded in Band: **{d.get('decision','—').replace('_',' ').title()}** "
               f"· {d.get('timestamp','')}")
    e1, e2 = st.columns(2)
    e1.download_button("⬇️ Export Decision Packet (.md)", ss.packet_md,
                       file_name="safety_decision_packet.md", mime="text/markdown",
                       use_container_width=True, type="primary")
    e2.download_button("⬇️ Export Audit Trail (.json)",
                       json.dumps(ss.audit, indent=2),
                       file_name="audit_trail.json", mime="application/json",
                       use_container_width=True)
    with st.container(border=True):
        st.markdown(ss.packet_md)

st.divider()
st.caption(DISCLAIMER)
