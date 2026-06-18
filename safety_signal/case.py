"""Load the full demo case into one bundle shared by all agents.

The Band room is the coordination layer (who runs when, via @mentions); this
bundle is the case file every agent reads. Agents may also enrich from prior
findings in ``state``, but they can always recompute deterministically from
here, which keeps the demo stable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import config, data_loaders as dl, openfda
from .data_loaders import BatchExposure, ComplaintFacts


@dataclass
class CaseData:
    case_id: str
    product: str
    batch_code: str
    complaints: list = field(default_factory=list)
    label_text: str = ""
    supplier_text: str = ""
    policy_text: str = ""
    batch_rows: list = field(default_factory=list)
    facts: ComplaintFacts | None = None
    exposure: BatchExposure | None = None
    label_allergens: list[str] = field(default_factory=list)
    supplier_allergens: list[str] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)
    precedents: dict[str, Any] = field(default_factory=dict)


def load_case(uploads: dict | None = None, fetch_precedents: bool = True) -> CaseData:
    """Build the case bundle from the demo files (or Streamlit uploads).

    ``uploads`` maps keys (complaints/label/supplier/batch/policy) to raw bytes.
    """
    uploads = uploads or {}
    complaints = dl.load_complaints(uploads.get("complaints"))
    label_text = dl.load_label(uploads.get("label"))
    supplier_text = dl.load_supplier_sheet(uploads.get("supplier"))
    policy_text = dl.load_policy(uploads.get("policy"))
    batch_rows = dl.load_batch_distribution(uploads.get("batch"))

    facts = dl.extract_complaint_facts(complaints, config.BATCH_CODE)
    exposure = dl.compute_batch_exposure(batch_rows, config.BATCH_CODE)
    label_allergens = dl.parse_allergens(label_text)
    supplier_allergens = dl.parse_allergens(supplier_text)
    undeclared = [a for a in supplier_allergens if a not in label_allergens]

    precedents = openfda.get_precedents() if fetch_precedents else openfda.load_cache()

    return CaseData(
        case_id=config.CASE_ID,
        product=config.PRODUCT,
        batch_code=config.BATCH_CODE,
        complaints=complaints,
        label_text=label_text,
        supplier_text=supplier_text,
        policy_text=policy_text,
        batch_rows=batch_rows,
        facts=facts,
        exposure=exposure,
        label_allergens=label_allergens,
        supplier_allergens=supplier_allergens,
        undeclared=undeclared,
        precedents=precedents,
    )
