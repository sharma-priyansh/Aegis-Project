"""OpenTelemetry metrics facade (Observability §14).

Exposes the domain metrics named in the architecture: time-to-first-hypothesis,
auto-remediation success, false-action rate, tokens/$ per incident, retrieval relevance.
A no-op fallback is used when OTel is disabled so call sites never need guards.
"""
from __future__ import annotations

from typing import Optional

from opentelemetry import metrics

from .config import Settings

_meter: Optional[metrics.Meter] = None
_instruments: dict[str, object] = {}


def setup_metrics(settings: Settings) -> None:
    global _meter
    if not settings.otel_enabled:
        return
    # The MeterProvider is configured via the OTel SDK env/autoinstrumentation;
    # here we just acquire a named meter.
    _meter = metrics.get_meter("aegis")
    _instruments["signals_ingested"] = _meter.create_counter(
        "aegis.signals.ingested", description="signals accepted by the gateway")
    _instruments["signals_deduplicated"] = _meter.create_counter(
        "aegis.signals.deduplicated", description="signals dropped as duplicates")
    _instruments["incidents_opened"] = _meter.create_counter(
        "aegis.incidents.opened", description="incidents opened")
    _instruments["agent_iterations"] = _meter.create_counter(
        "aegis.agent.iterations", description="agent graph node executions")
    _instruments["llm_tokens"] = _meter.create_counter(
        "aegis.llm.tokens", description="LLM tokens consumed")
    _instruments["actions_executed"] = _meter.create_counter(
        "aegis.actions.executed", description="remediation actions executed")
    _instruments["actions_rejected"] = _meter.create_counter(
        "aegis.actions.rejected", description="actions rejected by policy/approval")
    _instruments["time_to_first_hypothesis"] = _meter.create_histogram(
        "aegis.incident.time_to_first_hypothesis", unit="s",
        description="seconds from incident open to first hypothesis")


def incr(name: str, value: int = 1, **attrs) -> None:
    inst = _instruments.get(name)
    if inst is not None:
        inst.add(value, attributes=attrs)  # type: ignore[attr-defined]


def observe(name: str, value: float, **attrs) -> None:
    inst = _instruments.get(name)
    if inst is not None:
        inst.record(value, attributes=attrs)  # type: ignore[attr-defined]
