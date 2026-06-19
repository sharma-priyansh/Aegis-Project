"""Incident Orchestrator worker (FR-3).

Consumes `incidents.lifecycle` OPENED events, runs the LangGraph agent workflow, persists
a durable WorkflowSnapshot + Plan (ADR-006), and emits PLAN_PROPOSED or ESCALATED. It is
the single driver per incident by virtue of Kafka partition ownership (ADR-009); the plan
it writes is what the Approval/Executor services (Phase 4) act on.

Grounding is fetched from the RAG service over HTTP (Agent-comms §10). The LLM and RAG
endpoints are guarded by circuit breakers; budget is per-incident (ADR-017).
"""
from __future__ import annotations

import asyncio
import os
import signal as os_signal
import time
from uuid import UUID

import httpx
from sqlalchemy import delete, select

from aegis_common.audit import append_audit
from aegis_common.config import get_settings
from aegis_common.db import init_engine, session_scope
from aegis_common.events import IncidentEvent, IncidentEventType, Topic
from aegis_common.kafka import InboundMessage, KafkaBus
from aegis_common.llm import get_llm
from aegis_common.logging import configure_logging, get_logger
from aegis_common.metrics import incr, observe, setup_metrics
from aegis_common.models import ActionCatalogRow, IncidentRow, SignalRow
from aegis_common.models_remediation import PlanRow, PlanStepRow, WorkflowSnapshotRow  # noqa: F401
from aegis_common.reliability import Budget, CircuitBreaker
from aegis_common.telemetry import setup_telemetry, tracer

from .agents import AgentDeps
from .graph import build_graph
from .state import IncidentState

log = get_logger(__name__)
settings = get_settings()
GROUP_ID = "orchestrator"
RAG_URL = os.getenv("AEGIS_RAG_URL", "http://localhost:8004")

_llm = None
_rag_breaker = CircuitBreaker("rag", failure_threshold=4, cooldown_seconds=20)
_llm_breaker = CircuitBreaker("llm", failure_threshold=4, cooldown_seconds=20)


def _make_retriever(client: httpx.Client):
    def retrieve(query: str, service: str | None) -> dict:
        _rag_breaker.guard()
        try:
            resp = client.post(f"{RAG_URL}/v1/retrieve",
                               json={"query": query, "service": service}, timeout=15.0)
            resp.raise_for_status()
        except Exception:
            _rag_breaker.record_failure()
            raise
        _rag_breaker.record_success()
        data = resp.json()
        evidence_text = "\n".join(
            f"{h['citation']} {h['text'][:280]}" for h in data.get("runbooks", []))
        return {"citations": data.get("citations", []),
                "has_precedent": data.get("has_precedent", False),
                "best_precedent_score": data.get("best_precedent_score", 0.0),
                "evidence_text": evidence_text}
    return retrieve


async def _load_incident(session, incident_id: UUID) -> tuple[IncidentRow, list[SignalRow]]:
    inc = await session.get(IncidentRow, incident_id)
    sigs = (await session.execute(
        select(SignalRow).where(SignalRow.incident_id == incident_id))).scalars().all()
    return inc, list(sigs)


async def _risk_tier_map(session) -> dict[str, str]:
    rows = (await session.execute(select(ActionCatalogRow))).scalars().all()
    return {r.name: r.risk_tier for r in rows}


async def handle_opened(msg: InboundMessage, bus: KafkaBus, client: httpx.Client) -> None:
    event = IncidentEvent.model_validate(msg.value)
    if event.event_type != IncidentEventType.OPENED:
        return  # orchestrator only drives newly-opened incidents
    incident_id = event.incident_id
    started = time.monotonic()

    async with session_scope() as session:
        inc, sigs = await _load_incident(session, incident_id)
        if inc is None:
            log.warning("incident vanished before orchestration", extra={"incident_id": str(incident_id)})
            return
        risk_tiers = await _risk_tier_map(session)

    # Build the initial state from durable data.
    state: IncidentState = {
        "incident_id": str(incident_id),
        "fencing_token": inc.fencing_token,
        "title": inc.title,
        "services": list(inc.services or []),
        "severity": inc.severity,
        "signals": [{"service": s.service, "title": s.title, "severity": s.severity} for s in sigs],
        "notes": [],
    }

    budget = Budget(max_iterations=settings.max_diagnose_iterations,
                    wallclock_seconds=settings.incident_wallclock_budget_seconds,
                    max_tokens=settings.incident_token_budget).start()
    deps = AgentDeps(llm=_llm, breaker=_llm_breaker, budget=budget,
                     retrieve=_make_retriever(client))

    graph = build_graph(deps)
    config = {"configurable": {"thread_id": str(incident_id)}}
    with tracer(__name__).start_as_current_span("orchestrator.run") as span:
        final: IncidentState = await asyncio.to_thread(graph.invoke, state, config)
        span.set_attribute("incident.decision", final.get("decision", "?"))
        span.set_attribute("incident.escalated", bool(final.get("escalated")))

    incr("agent_iterations", final.get("iterations", 0))
    incr("llm_tokens", final.get("tokens_used", 0))
    observe("time_to_first_hypothesis", time.monotonic() - started)

    await _persist_and_emit(bus, incident_id, event, final, risk_tiers)


async def _persist_and_emit(bus, incident_id, event, final: IncidentState, risk_tiers) -> None:
    async with session_scope() as session:
        # Upsert workflow snapshot (durable, ADR-006).
        snap = await session.get(WorkflowSnapshotRow, incident_id)
        if snap is None:
            snap = WorkflowSnapshotRow(incident_id=incident_id)
            session.add(snap)
        snap.state = dict(final)
        snap.decision = final.get("decision", "unknown")
        snap.iterations = final.get("iterations", 0)
        snap.tokens_used = final.get("tokens_used", 0)

        escalated = bool(final.get("escalated"))
        if escalated or not final.get("plan"):
            await append_audit(session, actor="orchestrator", action="incident.escalated",
                               incident_id=incident_id, trace_id=event.trace_id,
                               payload={"reason": final.get("escalation_reason", "no plan")})
            out = IncidentEvent(incident_id=incident_id, event_type=IncidentEventType.ESCALATED,
                                fencing_token=final.get("fencing_token"), trace_id=event.trace_id,
                                data={"reason": final.get("escalation_reason", "no plan"),
                                      "root_cause": final.get("root_cause", "")})
        else:
            # Replace any prior plan for idempotency (redelivery-safe, ADR-005).
            old = (await session.execute(
                select(PlanRow.id).where(PlanRow.incident_id == incident_id))).scalars().all()
            if old:
                await session.execute(delete(PlanStepRow).where(PlanStepRow.plan_id.in_(old)))
                await session.execute(delete(PlanRow).where(PlanRow.incident_id == incident_id))
            plan = PlanRow(incident_id=incident_id, status="proposed",
                           rationale=final.get("rationale", ""),
                           requires_approval=final.get("requires_approval", True),
                           autonomy_allowed=final.get("autonomy_allowed", False))
            session.add(plan)
            await session.flush()
            for i, step in enumerate(final.get("plan", [])):
                session.add(PlanStepRow(plan_id=plan.id, ordinal=i, action=step.get("action", ""),
                                        params=step.get("params", {}),
                                        risk_tier=risk_tiers.get(step.get("action", ""), "medium")))
            await append_audit(session, actor="orchestrator", action="incident.plan_proposed",
                               incident_id=incident_id, trace_id=event.trace_id,
                               payload={"plan_id": str(plan.id),
                                        "actions": [s.get("action") for s in final.get("plan", [])],
                                        "requires_approval": plan.requires_approval,
                                        "confidence": final.get("confidence")})
            out = IncidentEvent(incident_id=incident_id, event_type=IncidentEventType.PLAN_PROPOSED,
                                fencing_token=final.get("fencing_token"), trace_id=event.trace_id,
                                data={"plan_id": str(plan.id), "title": final.get("title"),
                                      "severity": final.get("severity"),
                                      "root_cause": final.get("root_cause"),
                                      "requires_approval": plan.requires_approval})
    await bus.publish(Topic.INCIDENTS_LIFECYCLE, key=str(incident_id), value=out.model_dump(mode="json"))
    log.info("orchestration complete",
             extra={"incident_id": str(incident_id), "decision": final.get("decision")})


async def run() -> None:
    global _llm
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    setup_metrics(settings)
    init_engine(settings)
    _llm = get_llm(settings)
    bus = KafkaBus(settings)
    await bus.start_producer()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)

    with httpx.Client() as client:
        async def handler(m: InboundMessage) -> None:
            await handle_opened(m, bus, client)

        log.info("orchestrator starting", extra={"llm": _llm.name})
        try:
            await bus.consume([Topic.INCIDENTS_LIFECYCLE], GROUP_ID, handler, stop_event=stop)
        finally:
            await bus.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
