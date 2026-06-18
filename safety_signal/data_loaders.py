"""Load and parse the synthetic Cedar & Oat Foods demo-case files.

All parsing is deterministic Python. These loaders accept either the on-disk
demo files (default) or raw text/bytes uploaded through the Streamlit UI, so the
same logic backs both paths.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Iterable

from . import config

# ---- Keyword lexicons for deterministic complaint analysis ----
SERIOUS_SYMPTOMS = [
    "shortness of breath",
    "difficulty breathing",
    "swelling",
    "anaphyla",
    "throat",
]
ALL_SYMPTOMS = [
    "rash", "hives", "swelling", "shortness of breath", "stomach pain",
    "nausea", "throat irritation", "itchy throat", "throat",
]
MEDICAL_ESCALATION = ["urgent care", "doctor", "hospital", "emergency room", "physician"]
PEANUT_TERMS = ["peanut"]
ALLERGEN_REACTION = ["allergic reaction", "allergy", "allergic"]


@dataclass
class Complaint:
    complaint_id: str
    date: str
    channel: str
    customer_message: str
    product: str
    batch_code: str
    severity: str
    location: str

    @property
    def text(self) -> str:
        return self.customer_message.lower()


# ---------------------------------------------------------------------------
# Raw file loading
# ---------------------------------------------------------------------------
def _read_text(path_or_text: str | bytes | None, default_path) -> str:
    if path_or_text is None:
        return default_path.read_text(encoding="utf-8")
    if isinstance(path_or_text, bytes):
        return path_or_text.decode("utf-8")
    return path_or_text


def load_complaints(raw: str | bytes | None = None) -> list[Complaint]:
    text = _read_text(raw, config.DEMO_CASE_DIR / "complaints.csv")
    reader = csv.DictReader(io.StringIO(text))
    out: list[Complaint] = []
    for row in reader:
        out.append(
            Complaint(
                complaint_id=row.get("complaint_id", "").strip(),
                date=row.get("date", "").strip(),
                channel=row.get("channel", "").strip(),
                customer_message=row.get("customer_message", "").strip(),
                product=row.get("product", "").strip(),
                batch_code=row.get("batch_code", "").strip(),
                severity=row.get("severity", "").strip().lower(),
                location=row.get("location", "").strip(),
            )
        )
    return out


def load_label(raw: str | bytes | None = None) -> str:
    return _read_text(raw, config.DEMO_CASE_DIR / "consumer_label.txt")


def load_supplier_sheet(raw: str | bytes | None = None) -> str:
    return _read_text(raw, config.DEMO_CASE_DIR / "supplier_ingredient_sheet.txt")


def load_policy(raw: str | bytes | None = None) -> str:
    return _read_text(raw, config.DEMO_CASE_DIR / "company_policy.txt")


@dataclass
class BatchRow:
    batch_code: str
    sku: str
    units_produced: int
    units_sold: int
    units_in_inventory: int
    retailer: str
    location: str
    warehouse_status: str


def load_batch_distribution(raw: str | bytes | None = None) -> list[BatchRow]:
    text = _read_text(raw, config.DEMO_CASE_DIR / "batch_distribution.csv")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[BatchRow] = []
    for r in reader:
        rows.append(
            BatchRow(
                batch_code=r["batch_code"].strip(),
                sku=r["sku"].strip(),
                units_produced=int(r["units_produced"]),
                units_sold=int(r["units_sold"]),
                units_in_inventory=int(r["units_in_inventory"]),
                retailer=r["retailer"].strip(),
                location=r["location"].strip(),
                warehouse_status=r["warehouse_status"].strip(),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Deterministic analysis helpers (shared by agents and scoring)
# ---------------------------------------------------------------------------
def _count_matches(complaints: Iterable[Complaint], terms: list[str]) -> int:
    return sum(1 for c in complaints if any(t in c.text for t in terms))


def _present(complaints: Iterable[Complaint], terms: list[str]) -> list[Complaint]:
    return [c for c in complaints if any(t in c.text for t in terms)]


@dataclass
class ComplaintFacts:
    complaint_count: int
    batch_codes_detected: list[str]
    target_batch_count: int
    symptoms: list[str]
    allergen_mentions: list[str]
    medical_escalations: int
    high_risk_complaints: int
    allergic_reaction_mentions: int
    peanut_allergy_mentions: int
    channels: set[str] = field(default_factory=set)
    span_days: int = 0


def extract_complaint_facts(
    complaints: list[Complaint], target_batch: str = config.BATCH_CODE
) -> ComplaintFacts:
    """Deterministic extraction used both by the Intake agent and risk scoring."""
    batch_codes = sorted(
        {c.batch_code for c in complaints if c.batch_code and c.batch_code.upper() not in ("", "UNKNOWN")}
    )
    target_count = sum(1 for c in complaints if c.batch_code == target_batch)

    symptoms_found = [s for s in ("rash", "hives", "swelling", "shortness of breath",
                                  "stomach pain", "nausea", "throat irritation")
                      if _count_matches(complaints, [s]) > 0]

    allergen_mentions = []
    if _count_matches(complaints, ["peanut allergy"]):
        allergen_mentions.append("peanut allergy")
    if _count_matches(complaints, PEANUT_TERMS):
        allergen_mentions.append("peanut")

    medical = _count_matches(complaints, MEDICAL_ESCALATION)
    # "high risk" = complaints logged at high or critical severity
    high_risk = len([c for c in complaints if c.severity in ("high", "critical")])

    dates = sorted({c.date for c in complaints if c.date})
    span = _date_span_days(dates)

    return ComplaintFacts(
        complaint_count=len(complaints),
        batch_codes_detected=batch_codes,
        target_batch_count=target_count,
        symptoms=symptoms_found,
        allergen_mentions=allergen_mentions,
        medical_escalations=medical,
        high_risk_complaints=high_risk,
        allergic_reaction_mentions=_count_matches(complaints, ALLERGEN_REACTION),
        peanut_allergy_mentions=_count_matches(complaints, ["peanut allergy", "allergic to peanut"]),
        channels={c.channel for c in complaints if c.channel},
        span_days=span,
    )


def _date_span_days(dates: list[str]) -> int:
    from datetime import date

    parsed = []
    for d in dates:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
        if m:
            parsed.append(date(int(m[1]), int(m[2]), int(m[3])))
    if len(parsed) < 2:
        return 0
    return (max(parsed) - min(parsed)).days + 1


# ---- Allergen parsing for label vs supplier comparison ----
_KNOWN_ALLERGENS = [
    "milk", "egg", "fish", "shellfish", "tree nut", "almond", "almonds",
    "peanut", "peanuts", "wheat", "soy", "sesame",
]


def parse_allergens(block: str) -> list[str]:
    """Extract declared allergens from a label or supplier sheet.

    Prefers an explicit 'Contains:' / 'Allergen Declaration:' section; otherwise
    scans the whole text. Normalizes plurals (almonds -> almond).
    """
    lowered = block.lower()
    section = lowered
    for marker in ("contains:", "allergen declaration:"):
        if marker in lowered:
            after = lowered.split(marker, 1)[1]
            # stop at the next blank line / section header
            section = re.split(r"\n\s*\n", after, 1)[0]
            break

    found = []
    for a in _KNOWN_ALLERGENS:
        if re.search(rf"\b{re.escape(a)}\b", section):
            found.append(a)
    # normalize
    norm = []
    for a in found:
        a = {"almonds": "almond", "peanuts": "peanut"}.get(a, a)
        if a not in norm:
            norm.append(a)
    return norm


@dataclass
class BatchExposure:
    batch_code: str
    units_produced: int
    units_sold: int
    units_in_inventory: int
    retailers_affected: list[str]
    locations_affected: list[str]


def compute_batch_exposure(
    rows: list[BatchRow], batch_code: str = config.BATCH_CODE
) -> BatchExposure:
    """Deterministic inventory exposure for the affected batch.

    units_produced is taken as the per-batch production figure (constant across
    the batch's rows in the demo data); sold/inventory are summed across rows.
    """
    affected = [r for r in rows if r.batch_code == batch_code]
    produced = max((r.units_produced for r in affected), default=0)
    sold = sum(r.units_sold for r in affected)
    inventory = sum(r.units_in_inventory for r in affected)
    retailers = sorted({r.retailer for r in affected})
    locations = sorted({r.location for r in affected})
    return BatchExposure(
        batch_code=batch_code,
        units_produced=produced,
        units_sold=sold,
        units_in_inventory=inventory,
        retailers_affected=retailers,
        locations_affected=locations,
    )
