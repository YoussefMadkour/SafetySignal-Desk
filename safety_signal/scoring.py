"""Deterministic risk scoring (no LLM).

Implements the 100-point rubric from the spec. Each category is tiered and
capped; the function returns a transparent breakdown so the UI and the decision
packet can show exactly how the score was reached.

Expected demo result: score 95, level CRITICAL, decision HUMAN_REVIEW_REQUIRED.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .data_loaders import BatchExposure, ComplaintFacts


@dataclass
class ScoreLine:
    category: str
    points: int
    max_points: int
    reason: str


@dataclass
class RiskResult:
    score: int
    level: str
    decision: str
    lines: list[ScoreLine] = field(default_factory=list)

    @property
    def breakdown(self) -> dict[str, dict]:
        return {
            l.category: {"points": l.points, "max": l.max_points, "reason": l.reason}
            for l in self.lines
        }


def _level(score: int) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


def compute_risk(
    facts: ComplaintFacts,
    exposure: BatchExposure,
    undeclared_allergen: bool,
    unclear_mismatch: bool,
    precedent_strong: bool,
) -> RiskResult:
    lines: list[ScoreLine] = []

    # 1) Complaint volume and timing — 20 pts
    pts, why = 0, []
    n = facts.complaint_count
    if n > 10:
        pts, msg = 15, f"{n} complaints"
    elif n > 5:
        pts, msg = 10, f"{n} complaints"
    else:
        msg = f"{n} complaints"
    if pts:
        why.append(f"{msg} within {facts.span_days or 7} days")
    if len(facts.channels) > 1:
        pts += 5
        why.append(f"across {len(facts.channels)} channels")
    pts = min(pts, 20)
    lines.append(ScoreLine("Complaint volume and timing", pts, 20,
                           "; ".join(why) or "low volume"))

    # 2) Batch concentration — 20 pts
    ratio = facts.target_batch_count / facts.complaint_count if facts.complaint_count else 0.0
    if ratio > 0.70:
        pts = 20
    elif ratio > 0.50:
        pts = 15
    elif ratio > 0.30:
        pts = 10
    else:
        pts = 0
    lines.append(ScoreLine("Batch concentration", pts, 20,
                           f"{facts.target_batch_count}/{facts.complaint_count} "
                           f"complaints on same batch ({ratio:.0%})"))

    # 3) Medical severity — 20 pts
    serious = facts.medical_escalations
    if serious >= 2:
        pts, why = 20, f"{serious} medical-escalation mentions"
    elif serious >= 1 or facts.high_risk_complaints:
        pts, why = 10, "serious symptom or medical escalation mentioned"
    else:
        pts, why = 0, "no serious medical mentions"
    lines.append(ScoreLine("Medical severity", pts, 20, why))

    # 4) Label or ingredient mismatch — 25 pts
    if undeclared_allergen:
        pts, why = 25, "potential undeclared allergen"
    elif unclear_mismatch:
        pts, why = 10, "unclear allergen mismatch"
    else:
        pts, why = 0, "no label mismatch"
    lines.append(ScoreLine("Label or ingredient mismatch", pts, 25, why))

    # 5) Market exposure — 10 pts
    avail = exposure.units_in_inventory
    if avail > 1000:
        pts, why = 10, f"{avail:,} units still available"
    elif avail > 500:
        pts, why = 5, f"{avail:,} units still available"
    else:
        pts, why = 0, f"{avail:,} units available"
    lines.append(ScoreLine("Market exposure", pts, 10, why))

    # 6) Public recall precedent — 5 pts
    pts = 5 if precedent_strong else 0
    lines.append(ScoreLine("Public recall precedent", pts, 5,
                           "strong public recall precedent match" if precedent_strong
                           else "no strong precedent"))

    total = sum(l.points for l in lines)
    level = _level(total)
    decision = "HUMAN_REVIEW_REQUIRED" if total >= 50 else "MONITOR"
    return RiskResult(score=total, level=level, decision=decision, lines=lines)
