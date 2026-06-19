"""Unit tests for deterministic correlation (ADR-018). Pure logic, no infrastructure."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from aegis_common.schemas import Severity, Signal, SignalKind
from aegis_services.detection.correlation import (
    DecisionKind,
    OpenIncidentView,
    correlate,
    more_severe,
)
from aegis_services.detection.topology import Topology

NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
WINDOW = 120


def _sig(service: str, sev: Severity = Severity.SEV3) -> Signal:
    return Signal(kind=SignalKind.ALERT, source="test", service=service,
                  title="HighLatency", severity=sev)


def test_opens_new_incident_when_none_exist():
    decision = correlate(_sig("api"), [], Topology({}), NOW, WINDOW)
    assert decision.kind == DecisionKind.OPEN_NEW
    assert decision.severity == Severity.SEV3


def test_attaches_to_adjacent_incident_within_window():
    topo = Topology({"api": ["db"]})  # api <-> db
    inc = OpenIncidentView(uuid4(), frozenset({"db"}), Severity.SEV2,
                           NOW - timedelta(seconds=30))
    decision = correlate(_sig("api", Severity.SEV1), [inc], topo, NOW, WINDOW)
    assert decision.kind == DecisionKind.ATTACH
    assert decision.incident_id == inc.incident_id
    # severity escalates to the most severe of the two (sev1 < sev2 in rank)
    assert decision.severity == Severity.SEV1


def test_does_not_attach_outside_window():
    topo = Topology({"api": ["db"]})
    inc = OpenIncidentView(uuid4(), frozenset({"db"}), Severity.SEV2,
                           NOW - timedelta(seconds=600))
    decision = correlate(_sig("api"), [inc], topo, NOW, WINDOW)
    assert decision.kind == DecisionKind.OPEN_NEW


def test_does_not_attach_unrelated_service():
    topo = Topology({"api": ["db"]})  # 'cache' is unrelated
    inc = OpenIncidentView(uuid4(), frozenset({"cache"}), Severity.SEV2,
                           NOW - timedelta(seconds=10))
    decision = correlate(_sig("api"), [inc], topo, NOW, WINDOW)
    assert decision.kind == DecisionKind.OPEN_NEW


def test_same_service_always_adjacent():
    inc = OpenIncidentView(uuid4(), frozenset({"api"}), Severity.SEV3,
                           NOW - timedelta(seconds=10))
    decision = correlate(_sig("api"), [inc], Topology({}), NOW, WINDOW)
    assert decision.kind == DecisionKind.ATTACH


def test_picks_most_recent_adjacent_incident():
    topo = Topology({"api": ["db"]})
    older = OpenIncidentView(uuid4(), frozenset({"db"}), Severity.SEV3,
                             NOW - timedelta(seconds=90))
    newer = OpenIncidentView(uuid4(), frozenset({"api"}), Severity.SEV3,
                             NOW - timedelta(seconds=5))
    decision = correlate(_sig("api"), [older, newer], topo, NOW, WINDOW)
    assert decision.incident_id == newer.incident_id


def test_more_severe_ordering():
    assert more_severe(Severity.SEV1, Severity.SEV3) == Severity.SEV1
    assert more_severe(Severity.SEV4, Severity.SEV2) == Severity.SEV2
    assert more_severe(Severity.UNKNOWN, Severity.SEV4) == Severity.SEV4
