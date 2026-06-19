"""OpenTelemetry bootstrap. Aegis dogfoods OTel (Observability §14).

`setup_telemetry` wires a tracer provider with an OTLP exporter. Services call it once
at startup; `tracer` gives every module a named tracer for custom spans around agent
steps, tool calls, and Kafka handlers.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import Settings

_INITIALISED = False


def setup_telemetry(settings: Settings) -> None:
    """Initialise the global tracer provider exactly once per process."""
    global _INITIALISED
    if _INITIALISED or not settings.otel_enabled:
        return
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _INITIALISED = True


def tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
