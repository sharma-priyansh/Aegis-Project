"""IncidentState — the typed, checkpointed blackboard for the agent graph (ADR-003/006).

Agents coordinate by reading/writing this shared state, not by free-form chat. It is a
TypedDict so LangGraph can checkpoint it after every node, making workflows durable and
resumable (ADR-006). All fields are JSON-serialisable for checkpoint persistence.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class ProposedAction(TypedDict):
    action: str
    params: dict[str, Any]


class IncidentState(TypedDict, total=False):
    # --- identity / inputs ---
    incident_id: str
    fencing_token: Optional[int]
    title: str
    services: list[str]
    severity: str
    signals: list[dict[str, Any]]

    # --- triage outputs ---
    triage_summary: str
    urgent: bool

    # --- retrieval / investigation ---
    query: str
    citations: list[str]
    has_precedent: bool
    best_precedent_score: float
    root_cause: str
    confidence: float
    evidence_refs: list[str]

    # --- recommendation ---
    plan: list[ProposedAction]
    rationale: str

    # --- control / safety (ADR-016/017) ---
    autonomy_allowed: bool        # precedent-gated
    requires_approval: bool
    escalated: bool
    escalation_reason: str
    iterations: int
    tokens_used: int
    decision: str                 # one of: plan_ready | escalate | resolved
    notes: list[str]
