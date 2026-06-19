"""KafkaBus — a thin async abstraction over aiokafka (ADR-002).

Keeping all Kafka access behind this class means the client is swappable (the ADR
notes confluent-kafka as an alternative) and that tracing/serialization are applied
uniformly. Consumers are at-least-once with manual commit *after* successful handling
(ADR-005) so a crash mid-handle redelivers rather than loses the message.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Awaitable, Callable, Optional

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from opentelemetry import propagate, trace

from .config import Settings
from .events import Topic
from .logging import get_logger

log = get_logger(__name__)

Handler = Callable[["InboundMessage"], Awaitable[None]]


class InboundMessage:
    """A decoded Kafka record plus the extracted trace context."""

    def __init__(self, topic: str, key: Optional[str], value: dict, headers: dict[str, str]):
        self.topic = topic
        self.key = key
        self.value = value
        self.headers = headers


class KafkaBus:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._producer: Optional[AIOKafkaProducer] = None

    async def start_producer(self) -> None:
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._settings.kafka_bootstrap,
                client_id=f"{self._settings.kafka_client_id}-producer",
                enable_idempotence=True,  # broker-side dedup of producer retries
                acks="all",
            )
            await self._producer.start()
            log.info("kafka producer started")

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: Topic, key: str, value: dict) -> None:
        """Publish a JSON value keyed for partitioning, injecting trace context."""
        assert self._producer is not None, "producer not started"
        headers: list[tuple[str, bytes]] = []
        carrier: dict[str, str] = {}
        propagate.inject(carrier)
        for hk, hv in carrier.items():
            headers.append((hk, hv.encode()))
        await self._producer.send_and_wait(
            topic.value,
            key=key.encode(),
            value=orjson.dumps(value),
            headers=headers,
        )

    async def consume(
        self,
        topics: list[Topic],
        group_id: str,
        handler: Handler,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Run an at-least-once consume loop until `stop_event` is set.

        The offset is committed only after `handler` returns successfully, so failures
        redeliver. Handlers must therefore be idempotent (ADR-005).
        """
        consumer = AIOKafkaConsumer(
            *[t.value for t in topics],
            bootstrap_servers=self._settings.kafka_bootstrap,
            group_id=group_id,
            client_id=f"{self._settings.kafka_client_id}-{group_id}",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await consumer.start()
        log.info("kafka consumer started", extra={"group_id": group_id})
        tracer = trace.get_tracer(__name__)
        try:
            async for record in consumer:
                headers = {k: v.decode() for k, v in (record.headers or [])}
                ctx = propagate.extract(headers)
                with tracer.start_as_current_span(f"consume {record.topic}", context=ctx):
                    try:
                        msg = InboundMessage(
                            topic=record.topic,
                            key=record.key.decode() if record.key else None,
                            value=orjson.loads(record.value),
                            headers=headers,
                        )
                        await handler(msg)
                        await consumer.commit()
                    except Exception:  # noqa: BLE001 - log and continue; offset uncommitted
                        log.exception("handler failed; message will be redelivered",
                                      extra={"topic": record.topic})
                if stop_event is not None and stop_event.is_set():
                    break
        finally:
            await consumer.stop()
            log.info("kafka consumer stopped", extra={"group_id": group_id})


async def message_stream(consumer: AIOKafkaConsumer) -> AsyncIterator[InboundMessage]:
    async for record in consumer:
        headers = {k: v.decode() for k, v in (record.headers or [])}
        yield InboundMessage(
            topic=record.topic,
            key=record.key.decode() if record.key else None,
            value=orjson.loads(record.value),
            headers=headers,
        )
