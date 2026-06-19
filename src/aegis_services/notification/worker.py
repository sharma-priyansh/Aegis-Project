"""Notification worker (FR-6.3).

Consumes `incidents.lifecycle` and fans out human-facing notifications. Sinks:
  * structured log (always) — the deterministic paging path that works without the AI
    tier (NFR-3 / ADR-019: human paging never depends on agents).
  * optional outbound webhook (AEGIS_NOTIFY_WEBHOOK) — chat/paging integration.

Only high-signal transitions (opened, escalated, resolved, awaiting approval) page by
default to avoid notification fatigue.
"""
from __future__ import annotations

import asyncio
import os
import signal as os_signal

import httpx

from aegis_common.config import get_settings
from aegis_common.events import IncidentEvent, IncidentEventType, Topic
from aegis_common.kafka import InboundMessage, KafkaBus
from aegis_common.logging import configure_logging, get_logger
from aegis_common.telemetry import setup_telemetry

log = get_logger(__name__)
settings = get_settings()
GROUP_ID = "notification"
WEBHOOK = os.getenv("AEGIS_NOTIFY_WEBHOOK", "")
CONSOLE_BASE = os.getenv("AEGIS_CONSOLE_URL", "http://localhost:8002")

PAGING_EVENTS = {
    IncidentEventType.OPENED,
    IncidentEventType.ESCALATED,
    IncidentEventType.RESOLVED,
    IncidentEventType.PLAN_PROPOSED,
}


async def handle(msg: InboundMessage, client: httpx.AsyncClient) -> None:
    event = IncidentEvent.model_validate(msg.value)
    should_page = event.event_type in PAGING_EVENTS
    link = f"{CONSOLE_BASE}/incidents/{event.incident_id}"
    log.info(
        "notification",
        extra={
            "incident_id": str(event.incident_id),
            "event": event.event_type.value,
            "paging": should_page,
            "link": link,
            "data": event.data,
        },
    )
    if should_page and WEBHOOK:
        text = (f":rotating_light: Incident {event.event_type.value} "
                f"[{event.data.get('severity', 'n/a')}] {event.data.get('title', '')} — {link}")
        try:
            await client.post(WEBHOOK, json={"text": text}, timeout=5.0)
        except httpx.HTTPError as exc:
            log.warning("webhook delivery failed", extra={"error": str(exc)})


async def run() -> None:
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    bus = KafkaBus(settings)
    await bus.start_producer()  # not used for produce, but keeps lifecycle uniform
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)

    async with httpx.AsyncClient() as client:
        async def handler(m: InboundMessage) -> None:
            await handle(m, client)

        log.info("notification worker starting")
        try:
            await bus.consume([Topic.INCIDENTS_LIFECYCLE], GROUP_ID, handler, stop_event=stop)
        finally:
            await bus.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
