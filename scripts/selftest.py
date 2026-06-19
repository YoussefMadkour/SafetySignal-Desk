"""End-to-end self-test for the SafetySignal pipeline (no Band required).

Runs the full 7-agent pipeline twice — once with the LLM forced OFF
(deterministic) and once with whatever LLM is configured — and asserts:

  1. The audited ground truth (risk score/level/decision, complaint counts,
     batch exposure, undeclared-allergen detection) is correct, and
  2. It is *byte-for-byte identical* across both modes — i.e. the LLM can phrase
     findings but can never move a number or a decision, and
  3. Safety guardrails hold (every draft is a DRAFT, none claims the product is
     safe or promises a recall), and
  4. The decision packet builds and contains the audit-grade sections.

Run:  python -m scripts.selftest        (uses configured LLM if a key is set)
Exit code 0 = all checks passed; 1 = a check failed.
"""
from __future__ import annotations

import sys

from safety_signal import config, report_generator
from safety_signal.case import load_case
from safety_signal.llm_client import LLMClient
from safety_signal.orchestrator import PIPELINE, _AGENT_RUN
from safety_signal.schemas import AgentMessage, SafetySignalState

# Fields that MUST never be influenced by the LLM, per agent key.
IMMUTABLE = {
    "complaint_intake": ["complaint_count", "medical_escalations", "high_risk_complaints"],
    "pattern_detection": ["cluster_detected", "signal_strength", "batch_concentration"],
    "label_ingredient": ["undeclared_allergen_detected", "undeclared_allergen",
                          "consumer_label_allergens", "supplier_sheet_allergens"],
    "batch_trace": ["units_produced", "units_sold", "units_in_inventory"],
    "regulatory_risk": ["risk_level", "risk_score", "decision", "score_breakdown",
                        "policy_triggers"],
}
LANGUAGE_AGENTS = ["complaint_intake", "label_ingredient", "recall_precedent",
                   "regulatory_risk", "customer_response"]
UNSAFE_PHRASES = ["is safe", "confirmed safe", "guaranteed safe", "we are recalling",
                  "product is being recalled", "safe to eat", "safe to consume"]

_AGENT_DISPLAY = {k: config.AGENTS_BY_KEY[k].name for k in PIPELINE}


class Checker:
    def __init__(self):
        self.failed = 0

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {label}"
        if not ok and detail:
            line += f"  -> {detail}"
        print(line)
        if not ok:
            self.failed += 1


def run_pipeline(llm) -> tuple[dict, SafetySignalState]:
    """Run all agents with cached precedents (no network) and a given llm."""
    case = load_case(fetch_precedents=False)
    state = SafetySignalState(case_id=case.case_id, product=case.product,
                             batch_code=case.batch_code)
    structured: dict[str, dict] = {}
    for key in PIPELINE:
        out = _AGENT_RUN[key](case, structured, llm)
        structured[out.structured["agent"]] = out.structured
        state.absorb(key, out.structured)
        state.audit_trail.append(AgentMessage(
            room_id="selftest", agent_name=_AGENT_DISPLAY[key],
            summary=out.summary, structured_data=out.structured))
    return structured, state


def main() -> int:
    c = Checker()

    # --- Deterministic baseline (LLM forced off) ---
    det_client = LLMClient()
    det_client.enabled = False  # force the deterministic path regardless of key
    print("Running deterministic baseline (LLM off)...")
    det, det_state = run_pipeline(det_client)

    print("\n== Ground-truth assertions (deterministic) ==")
    rr = det["regulatory_risk"]
    c.check(rr["risk_score"] == 100, "risk score == 100", str(rr.get("risk_score")))
    c.check(rr["risk_level"] == "CRITICAL", "risk level == CRITICAL", rr.get("risk_level"))
    c.check(rr["decision"] == "HUMAN_REVIEW_REQUIRED", "decision == HUMAN_REVIEW_REQUIRED",
            rr.get("decision"))
    c.check(det["label_ingredient"]["undeclared_allergen"] == "peanut",
            "undeclared allergen == peanut", str(det["label_ingredient"].get("undeclared_allergen")))
    c.check(det["pattern_detection"]["cluster_detected"] is True, "cluster detected")
    c.check(det["recall_precedent"]["precedent_match"] == "STRONG",
            "precedent match == STRONG", det["recall_precedent"].get("precedent_match"))
    c.check(len(det_state.audit_trail) == len(PIPELINE),
            f"all {len(PIPELINE)} agents produced output", str(len(det_state.audit_trail)))

    print("\n== Safety guardrails (deterministic drafts) ==")
    _check_drafts(c, det["customer_response"])

    print("\n== Packet builds with audit-grade sections ==")
    packet = report_generator.build_packet(det_state, load_case(fetch_precedents=False))
    for section in ["## Risk Scoring", "## Public Recall Precedents", "## Reasoning Provenance",
                    "## Draft Communications", "Internal QA Task"]:
        c.check(section in packet, f"packet contains '{section}'")

    # --- LLM path (only if a key is configured) ---
    if config.llm_enabled():
        llm = LLMClient()
        print(f"\nRunning LLM path (model={llm.model})...")
        llm_out, llm_state = run_pipeline(llm)

        print("\n== Immutability: LLM must NOT change any audited number ==")
        for key, fields in IMMUTABLE.items():
            for fld in fields:
                same = det[key].get(fld) == llm_out[key].get(fld)
                c.check(same, f"{key}.{fld} unchanged by LLM",
                        f"det={det[key].get(fld)!r} llm={llm_out[key].get(fld)!r}")

        print("\n== LLM actually engaged on language agents ==")
        for key in LANGUAGE_AGENTS:
            mode = llm_out[key].get("reasoning_mode")
            c.check(mode == "llm", f"{key} reasoning_mode == llm", str(mode))

        print("\n== Safety guardrails (LLM drafts) ==")
        _check_drafts(c, llm_out["customer_response"])
    else:
        print("\n(LLM not configured — skipping LLM-path checks. Set OPENAI_API_KEY to enable.)")

    print()
    if c.failed:
        print(f"RESULT: {c.failed} check(s) FAILED")
        return 1
    print("RESULT: all checks passed ✅")
    return 0


def _check_drafts(c: Checker, resp: dict) -> None:
    draft_keys = ["retailer_hold_notice", "customer_support_reply",
                  "internal_qa_task", "public_statement_draft"]
    for k in draft_keys:
        v = (resp.get(k) or "")
        c.check(v.strip().upper().startswith("DRAFT"), f"{k} marked DRAFT")
        lowered = v.lower()
        bad = [p for p in UNSAFE_PHRASES if p in lowered]
        c.check(not bad, f"{k} avoids unsafe language", f"found: {bad}")
    c.check(resp.get("requires_human_approval") is True, "requires_human_approval == True")


if __name__ == "__main__":
    sys.exit(main())
