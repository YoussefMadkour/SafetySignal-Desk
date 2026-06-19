"""Central configuration, environment loading, and the agent roster.

Everything reads from environment variables (see .env.example). The agent
roster is the single source of truth for the 7 specialist agents plus the
human recall manager: names, handles, and the demo-case file each agent reads.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEMO_CASE_DIR = DATA_DIR / "demo_case"
PUBLIC_RECALL_DIR = DATA_DIR / "public_recall_examples"
OUTPUTS_DIR = ROOT / "outputs"
OPENFDA_CACHE = PUBLIC_RECALL_DIR / "openfda_undeclared_peanut.json"

# ---- Demo case identity ----
CASE_ID = "SS-CO-0426"
PRODUCT = "Cedar & Oat Cocoa Protein Bar"
BATCH_CODE = "CO-CPB-0426"
SKU = "CO-COCOA-PRO-60G"
COMPANY = "Cedar & Oat Foods"

# ---- LLM provider (configurable: aiml | openai | gemini) ----
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "aiml").strip().lower()

# Per-provider presets: (base_url, default_model, key_env, model_env).
_LLM_PRESETS = {
    "aiml": ("https://api.aimlapi.com/v1", "gpt-4o-mini", "AIML_API_KEY", "AIML_MODEL"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY", "OPENAI_MODEL"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "gemini-2.0-flash", "GEMINI_API_KEY", "GEMINI_MODEL"),
}

# Allow the AI/ML base URL to be overridden (kept for backwards compatibility).
_AIML_BASE_OVERRIDE = os.getenv("AIML_API_BASE_URL", "").strip()


def resolve_llm() -> tuple[str, str, str, str]:
    """Return (provider, api_key, base_url, model) for the selected provider.

    LLM_API_KEY / LLM_BASE_URL / LLM_MODEL are hard overrides that win over the
    provider preset, so any OpenAI-compatible endpoint can be plugged in.
    """
    provider = LLM_PROVIDER if LLM_PROVIDER in _LLM_PRESETS else "openai"
    base, model, key_env, model_env = _LLM_PRESETS[provider]
    if provider == "aiml" and _AIML_BASE_OVERRIDE:
        base = _AIML_BASE_OVERRIDE

    api_key = (os.getenv("LLM_API_KEY", "").strip() or os.getenv(key_env, "").strip())
    base_url = (os.getenv("LLM_BASE_URL", "").strip() or base)
    model = (os.getenv("LLM_MODEL", "").strip() or os.getenv(model_env, "").strip() or model)
    return provider, api_key, base_url, model

# ---- Band ----
BAND_API_KEY = os.getenv("BAND_API_KEY", "").strip()
BAND_API_BASE_URL = os.getenv("BAND_API_BASE_URL", "https://app.band.ai/api/v1").strip()
BAND_WS_URL = os.getenv("BAND_WS_URL", "wss://app.band.ai/api/v1/socket/websocket").strip()
BAND_OWNER_USER_ID = os.getenv("BAND_OWNER_USER_ID", "").strip()
BAND_OWNER_NAME = os.getenv("BAND_OWNER_NAME", "Recall Manager").strip()
BAND_OWNER_HANDLE = os.getenv("BAND_OWNER_HANDLE", "recall_manager").strip()
BAND_AGENT_KEYS_FILE = ROOT / os.getenv("BAND_AGENT_KEYS_FILE", "agents.json")

# ---- openFDA ----
USE_CACHED_PUBLIC_DATA = os.getenv("USE_CACHED_PUBLIC_DATA", "true").lower() == "true"
OPENFDA_BASE_URL = os.getenv("OPENFDA_BASE_URL", "https://api.fda.gov/food/enforcement.json").strip()


@dataclass(frozen=True)
class AgentSpec:
    """Static definition of one specialist agent."""

    key: str            # internal id, e.g. "complaint_intake"
    name: str           # Band display name, e.g. "Complaint Intake Agent"
    handle: str         # Band handle, e.g. "complaint_intake_agent"
    role: str           # one-line role description
    inputs: list[str] = field(default_factory=list)


# The roster is ordered for readability; coordination order is driven by @mentions.
AGENTS: list[AgentSpec] = [
    AgentSpec(
        key="complaint_intake",
        name="Complaint Intake Agent",
        handle="complaint_intake_agent",
        role=("Reads raw consumer complaints and extracts structured safety facts — "
              "symptoms, allergen mentions, batch codes, and medical escalations. Opens "
              "every case and hands the facts to Pattern Detection and Label & Ingredient."),
        inputs=["complaints.csv"],
    ),
    AgentSpec(
        key="pattern_detection",
        name="Pattern Detection Agent",
        handle="pattern_detection_agent",
        role=("Determines whether complaints form a meaningful safety cluster, measuring "
              "same-batch concentration and signal strength over time. Confirms (or rejects) "
              "that there's a real event worth escalating."),
    ),
    AgentSpec(
        key="label_ingredient",
        name="Label and Ingredient Agent",
        handle="label_ingredient_agent",
        role=("Compares the consumer label against the supplier ingredient sheet to catch "
              "undeclared allergens. Flags mismatches such as undeclared peanut and escalates "
              "to Regulatory Risk, Recall Precedent, and Batch Trace."),
        inputs=["consumer_label.txt", "supplier_ingredient_sheet.txt"],
    ),
    AgentSpec(
        key="batch_trace",
        name="Batch Trace Agent",
        handle="batch_trace_agent",
        role=("Quantifies affected product exposure — units produced, sold, and still in "
              "market across retailers and locations. Deterministic only (no model "
              "inference), so the figures are audit-grade."),
        inputs=["batch_distribution.csv"],
    ),
    AgentSpec(
        key="recall_precedent",
        name="Recall Precedent Agent",
        handle="recall_precedent_agent",
        role=("Pulls real recall precedents from the openFDA Food Enforcement database for "
              "similar undeclared-allergen events, and summarizes how they inform the "
              "expected action."),
    ),
    AgentSpec(
        key="regulatory_risk",
        name="Regulatory Risk Agent",
        handle="regulatory_risk_agent",
        role=("Scores operational risk on a transparent 100-point rubric, checks "
              "company-policy escalation triggers, and blocks unsafe automatic action — "
              "routing the decision to the human recall manager. Operational escalation "
              "only; not legal, medical, or regulatory advice."),
        inputs=["company_policy.txt"],
    ),
    AgentSpec(
        key="customer_response",
        name="Customer and Retailer Response Agent",
        handle="customer_response_agent",
        role=("Drafts cautious retailer hold notices, customer replies, and internal QA "
              "tasks — always marked DRAFT and never sent. Requires human approval before "
              "any external communication."),
    ),
]

AGENTS_BY_KEY: dict[str, AgentSpec] = {a.key: a for a in AGENTS}
AGENTS_BY_NAME: dict[str, AgentSpec] = {a.name: a for a in AGENTS}

# The human recall manager — a Band user, not a registered agent.
HUMAN_MANAGER_NAME = "Human Recall Manager"
HUMAN_MANAGER_HANDLE = BAND_OWNER_HANDLE


def load_agent_registry() -> dict[str, dict]:
    """Return {agent_key: {"agent_id": ..., "api_key": ..., "name": ..., "handle": ...}}.

    Populated by scripts/register_agents.py. For hosted deploys (Streamlit Cloud)
    where agents.json is not committed, the same JSON can be supplied via the
    BAND_AGENTS_JSON env var / secret. Returns {} if neither is present.
    """
    inline = os.getenv("BAND_AGENTS_JSON", "").strip()
    if inline:
        try:
            return json.loads(inline)
        except json.JSONDecodeError:
            pass
    if BAND_AGENT_KEYS_FILE.exists():
        return json.loads(BAND_AGENT_KEYS_FILE.read_text())
    return {}


def save_agent_registry(registry: dict[str, dict]) -> None:
    BAND_AGENT_KEYS_FILE.write_text(json.dumps(registry, indent=2))


def llm_enabled() -> bool:
    _, api_key, _, _ = resolve_llm()
    return bool(api_key)
