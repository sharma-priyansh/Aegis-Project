"""Detection & Correlation worker (FR-2, ADR-018).

Consumes `signals.raw`, normalizes, persists the signal, runs deterministic correlation,
creates or extends an incident with optimistic concurrency + a fencing token (ADR-009),
writes a tamper-evident audit record (ADR-014), and emits an `incidents.lifecycle` event.

The handler is idempotent (ADR-005): the signal_id is the primary key, so a redelivered
signal is rejected on insert and the message is acked without creating a duplicate.
"""
from __future__ import annotations

import asyncio
import signal as os_signal
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis_common.audit import append_audit
from aegis_common.config import get_settings
from aegis_common.db import init_engine, session_scope
from aegis_common.events import IncidentEvent, IncidentEventType, SignalEvent, Topic
from aegis_common.kafka import InboundMessage, KafkaBus
from aegis_common.logging import configure_logging, get_logger
from aegis_common.models import IncidentRow
from aegis_common.ownership import next_fencing_token
from aegis_common.repository import create_incident, persist_signal
from aegis_common.schemas import Incident, IncidentStatus, Severity, Signal
from aegis_common.telemetry import setup_telemetry, tracer
from aegis_common.schemas import SignalKind  # noqa: F401  (kept for normalization clarity)

from .correlation import (
    CorrelationDecision,
    DecisionKind,
    OpenIncidentView,
    correlate,
    more_severe,
)
from .topology import Topology

log = get_logger(__name__)
settings = get_settings()
GROUP_ID = "detection-correlation"


def normalize(signal: Signal) -> Signal:
    """Apply canonical normalization (FR-1.2).

    Gateway already emits the canonical schema, so normalization here is light: stamp
    received_at and coerce an unknown severity to sev3 for alerts (a firing alert is at
    least minor by definition). Kept explicit so the rule is auditable.
    """
    signal.received_at = datetime.now(timezone.utc)
    if signal.severity == Severity.UNKNOWN and signal.kind.value == "alert":
        signal.severity = Severity.SEV3
    return signal


async def _load_open_incident_views(session) -> list[OpenIncidentView]:
    stmt = select(IncidentRow).where(
        IncidentRow.status != IncidentStatus.RESOLVED.value
    ).order_by(IncidentRow.updated_at.desc()).limit(200)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        OpenIncidentView(
            incident_id=r.id,
            services=frozenset(r.services or []),
            severity=Severity(r.severity),
            last_updated=r.updated_at or r.opened_at,
        )
        for r in rows
    ]


async def handle_signal(msg: InboundMessage, bus: KafkaBus) -> None:
    event = SignalEvent.model_validate(msg.value)
    sig = normalize(event.signal)
    now = datetime.now(timezone.utc)

    async with session_scope() as session:
        views = await _load_open_incident_views(session)
        topology = Topology.load()
        decision: CorrelationDecision = correlate(
            sig, views, topology, now, settings.correlation_window_seconds
        )

        if decision.kind == DecisionKind.ATTACH and decision.incident_id is not None:
            inc_row = await session.get(IncidentRow, decision.incident_id, with_for_update=True)
            if inc_row is None:  # raced with resolution; fall through to new incident
                decision = CorrelationDecision(kind=DecisionKind.OPEN_NEW, severity=sig.severity)
            else:
                if sig.service not in (inc_row.services or []):
                    inc_row.services = [*(inc_row.services or []), sig.service]
                inc_row.severity = more_severe(Severity(inc_row.severity), sig.severity).value
                inc_row.version += 1
                inc_row.status = IncidentStatus.INVESTIGATING.value
                try:
                    await persist_signal(session, sig, inc_row.id)
                except IntegrityError:
                    log.info("duplicate signal ignored", extra={"signal_id": str(sig.signal_id)})
                    return
                await append_audit(
                    session, actor="detection", action="incident.signal_attached",
                    incident_id=inc_row.id, trace_id=event.trace_id,
                    payload={"signal_id": str(sig.signal_id), "service": sig.service},
                )
                outgoing = IncidentEvent(
                    incident_id=inc_row.id, event_type=IncidentEventType.UPDATED,
                    fencing_token=inc_row.fencing_token, trace_id=event.trace_id,
                    data={"added_service": sig.service, "severity": inc_row.severity},
                )
                await _publish_incident(bus, outgoing)
                log.info("signal attached to incident",
                         extra={"incident_id": str(inc_row.id), "service": sig.service})
                return

        # OPEN_NEW
        token = await next_fencing_token(session)
        incident = Incident(
            status=IncidentStatus.OPEN,
            severity=decision.severity,
            title=f"{sig.severity.value.upper()}: {sig.title} on {sig.service}",
            services=[sig.service],
            fencing_token=token,
        )
        await create_incident(session, incident)
        try:
            await persist_signal(session, sig, incident.incident_id)
        except IntegrityError:
            log.info("duplicate signal ignored", extra={"signal_id": str(sig.signal_id)})
            return
        await append_audit(
            session, actor="detection", action="incident.opened",
            incident_id=incident.incident_id, trace_id=event.trace_id,
            payload={"service": sig.service, "severity": decision.severity.value,
                     "fencing_token": token},
        )
        outgoing = IncidentEvent(
            incident_id=incident.incident_id, event_type=IncidentEventType.OPENED,
            fencing_token=token, trace_id=event.trace_id,
            data={"title": incident.title, "severity": incident.severity.value,
                  "services": incident.services},
        )
        await _publish_incident(bus, outgoing)
        log.info("incident opened",
                 extra={"incident_id": str(incident.incident_id), "severity": decision.severity.value})


async def _publish_incident(bus: KafkaBus, event: IncidentEvent) -> None:
    await bus.publish(
        Topic.INCIDENTS_LIFECYCLE,
        key=str(event.incident_id),  # partition by incident_id (ADR-009)
        value=event.model_dump(mode="json"),
    )


async def run() -> None:
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    init_engine(settings)
    bus = KafkaBus(settings)
    await bus.start_producer()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)

    async def handler(msg: InboundMessage) -> None:
        with tracer(__name__).start_as_current_span("detection.handle_signal"):
            await handle_signal(msg, bus)

    log.info("detection worker starting")
    try:
        await bus.consume([Topic.SIGNALS_RAW], GROUP_ID, handler, stop_event=stop)
    finally:
        await bus.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
