"""Unit tests for signal fingerprinting / dedup semantics (FR-1.3)."""
from __future__ import annotations

from aegis_common.schemas import Severity, Signal, SignalKind


def _sig(**kw) -> Signal:
    base = dict(kind=SignalKind.ALERT, source="am", service="api", title="HighLatency",
                severity=Severity.SEV2, labels={"region": "us", "pod": "api-1"})
    base.update(kw)
    return Signal(**base)


def test_fingerprint_is_timestamp_independent():
    a = _sig()
    b = _sig()  # different signal_id and timestamps, same content
    assert a.signal_id != b.signal_id
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_changes_with_service():
    assert _sig(service="api").fingerprint() != _sig(service="db").fingerprint()


def test_fingerprint_changes_with_labels():
    assert _sig(labels={"pod": "a"}).fingerprint() != _sig(labels={"pod": "b"}).fingerprint()


def test_fingerprint_label_order_independent():
    a = _sig(labels={"a": "1", "b": "2"})
    b = _sig(labels={"b": "2", "a": "1"})
    assert a.fingerprint() == b.fingerprint()
