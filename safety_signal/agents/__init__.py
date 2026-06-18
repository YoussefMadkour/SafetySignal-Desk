"""Specialist agents. Each module exposes run(case, state, llm) -> AgentOutput."""

from . import (
    batch_trace,
    complaint_intake,
    customer_response,
    label_ingredient,
    pattern_detection,
    recall_precedent,
    regulatory_risk,
)

# key -> module, in coordination order
REGISTRY = {
    "complaint_intake": complaint_intake,
    "pattern_detection": pattern_detection,
    "label_ingredient": label_ingredient,
    "batch_trace": batch_trace,
    "recall_precedent": recall_precedent,
    "regulatory_risk": regulatory_risk,
    "customer_response": customer_response,
}
