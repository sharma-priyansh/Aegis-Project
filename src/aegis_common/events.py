"""Kafka topic registry and event envelopes (ADR-002).

Topic names and their partition keys are defined here once. The partition key choice
is a correctness concern, not a perf detail:
  - signals.raw / signals.normalized  -> key = service   (locality for correlation)
  - incidents.lifecycle               -> key = incident_id (single-driver, ADR-009)
  - actions.*                         -> key = incident_id
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .schemas import Signal, utcnow


class Topic(str, Enum):
    SIGNALS_RAW = "signals.raw"
    SIGNALS_NORMALIZED = "signals.normalized"
    INCIDENTS_LIFECYCLE = "incidents.lifecycle"
    ACTIONS_REQUESTED = "actions.requested"
    ACTIONS_RESULT = "actions.result"
    KNOWLEDGE_INGEST = "knowledge.ingest"
    NOTIFICATIONS_OUTBOUND = "notifications.outbound"


class IncidentEventType(str, Enum):
    OPENED = "opened"
    UPDATED = "updated"
    INVESTIGATING = "investigating"
    PLAN_PROPOSED = "plan_proposed"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class EventEnvelope(BaseModel):
    """Common envelope wrapping every domain event on Kafka.

    `idempotency_key` lets every consumer be idempotent (ADR-005); `trace_id` carries
    distributed-tracing context across the async boundary (Observability §14).
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    occurred_at: str = Field(default_factory=lambda: utcnow().isoformat())
    idempotency_key: str
    trace_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalEvent(BaseModel):
    """Envelope for a raw/normalized signal."""

    signal: Signal
    idempotency_key: str
    trace_id: Optional[str] = None

    @classmethod
    def of(cls, signal: Signal, trace_id: Optional[str] = None) -> "SignalEvent":
        return cls(signal=signal, idempotency_key=signal.fingerprint(), trace_id=trace_id)


class IncidentEvent(BaseModel):
    """Lifecycle event for an incident (partitioned by incident_id)."""

    incident_id: UUID
    event_type: IncidentEventType
    occurred_at: str = Field(default_factory=lambda: utcnow().isoformat())
    fencing_token: Optional[int] = None
    trace_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
