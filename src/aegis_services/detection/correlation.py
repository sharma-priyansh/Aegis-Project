"""Deterministic correlation logic (ADR-018) — pure and unit-testable (no I/O).

Rule set (deterministic-first; ML deferred per ADR-018):
  A signal correlates into an existing open incident when ALL hold:
    1. the incident was last updated within the correlation window, AND
    2. the signal's service is topology-adjacent to a service already on the incident.
  Otherwise a new incident is opened.

Incident severity is the most severe signal seen (sev1 < ... < sev4 ordering inverted
so sev1 is "highest"). This keeps a deterministic, explainable baseline that the agent
tier later builds on, rather than hiding correlation behind an opaque model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import UUID

from aegis_common.schemas import Severity, Signal

from .topology import Topology

# Rank for "how severe"; lower number = more severe.
_SEV_RANK = {
    Severity.SEV1: 0,
    Severity.SEV2: 1,
    Severity.SEV3: 2,
    Severity.SEV4: 3,
    Severity.UNKNOWN: 4,
}


def more_severe(a: Severity, b: Severity) -> Severity:
    return a if _SEV_RANK[a] <= _SEV_RANK[b] else b


@dataclass(frozen=True)
class OpenIncidentView:
    """Minimal projection of an open incident needed to make a correlation decision."""

    incident_id: UUID
    services: frozenset[str]
    severity: Severity
    last_updated: datetime


class DecisionKind(str, Enum):
    ATTACH = "attach"
    OPEN_NEW = "open_new"


@dataclass(frozen=True)
class CorrelationDecision:
    kind: DecisionKind
    incident_id: Optional[UUID] = None
    severity: Severity = Severity.UNKNOWN  # resulting/derived severity


def correlate(
    signal: Signal,
    open_incidents: list[OpenIncidentView],
    topology: Topology,
    now: datetime,
    window_seconds: int,
) -> CorrelationDecision:
    """Decide whether `signal` joins an existing incident or opens a new one."""
    window = timedelta(seconds=window_seconds)
    # Prefer the most-recently-updated adjacent incident for stable, deterministic grouping.
    candidates = sorted(open_incidents, key=lambda i: i.last_updated, reverse=True)
    for inc in candidates:
        within_window = (now - inc.last_updated) <= window
        if within_window and topology.related(signal.service, set(inc.services)):
            return CorrelationDecision(
                kind=DecisionKind.ATTACH,
                incident_id=inc.incident_id,
                severity=more_severe(inc.severity, signal.severity),
            )
    return CorrelationDecision(kind=DecisionKind.OPEN_NEW, severity=signal.severity)
