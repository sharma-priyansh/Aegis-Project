"""Canonical domain schemas (FR-1.2). One source of truth for every service.

These Pydantic models define the wire format on Kafka and the API contract. They are
deliberately decoupled from the SQLAlchemy ORM models (models.py): schemas are the
external contract, ORM rows are the storage representation.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Severity(str, Enum):
    SEV1 = "sev1"  # critical, customer-facing outage
    SEV2 = "sev2"  # major degradation
    SEV3 = "sev3"  # minor / single-service
    SEV4 = "sev4"  # informational
    UNKNOWN = "unknown"


class SignalKind(str, Enum):
    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"
    ALERT = "alert"
    DEPLOY = "deploy"
    CHANGE = "change"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    PLAN_PROPOSED = "plan_proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class Signal(BaseModel):
    """A single normalized observability signal (FR-1.2)."""

    signal_id: UUID = Field(default_factory=uuid4)
    kind: SignalKind
    source: str  # e.g. "alertmanager", "otel-collector"
    service: str  # affected service name (the correlation/partition key, ADR-018)
    title: str
    description: str = ""
    severity: Severity = Severity.UNKNOWN
    labels: dict[str, str] = Field(default_factory=dict)
    value: Optional[float] = None
    observed_at: datetime = Field(default_factory=utcnow)
    received_at: datetime = Field(default_factory=utcnow)

    def fingerprint(self) -> str:
        """Stable content hash for deduplication (FR-1.3).

        Two signals that describe the same condition (same service/kind/title and
        label set) collapse to the same fingerprint regardless of timestamp.
        """
        label_part = "&".join(f"{k}={v}" for k, v in sorted(self.labels.items()))
        raw = f"{self.kind.value}|{self.service}|{self.title}|{label_part}"
        return hashlib.sha256(raw.encode()).hexdigest()


class Hypothesis(BaseModel):
    """A ranked root-cause hypothesis with grounding (FR-3.3, ADR-016)."""

    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)  # citation handles
    live_evidence: list[str] = Field(default_factory=list)  # corroborating live signals


class Incident(BaseModel):
    """A correlated incident — the unit of work the platform reasons about."""

    incident_id: UUID = Field(default_factory=uuid4)
    status: IncidentStatus = IncidentStatus.OPEN
    severity: Severity = Severity.UNKNOWN
    title: str
    services: list[str] = Field(default_factory=list)
    signal_ids: list[UUID] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    fencing_token: Optional[int] = None  # monotonic, from Postgres sequence (ADR-009)
    version: int = 0  # optimistic-concurrency guard
    opened_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    resolved_at: Optional[datetime] = None
    extra: dict[str, Any] = Field(default_factory=dict)
