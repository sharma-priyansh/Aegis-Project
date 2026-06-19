"""Action Executor worker — the PEP (ADR-007/009/014, FR-5.4/5.5).

Consumes `actions.requested` (APPROVED). For each plan it:
  1. INDEPENDENTLY verifies the approval signature (does not trust the producer, ADR-014).
  2. Confirms the fencing token is still current for the incident (ADR-009) — a superseded
     owner cannot execute.
  3. Mints a scoped, short-lived capability per namespace (ADR-014).
  4. Validates each step's params against the catalog schema (ADR-015).
  5. Executes steps in order, idempotently (unique idempotency_key ledger, ADR-005).
  6. On any failure, runs SAGA ROLLBACK of applied reversible steps in reverse (FR-5.4).
  7. Verifies and emits EXECUTING -> RESOLVED (or ESCALATED on failure).
"""
from __future__ import annotations

import asyncio
import os
import signal as os_signal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis_common.audit import append_audit
from aegis_common.config import get_settings
from aegis_common.db import init_engine, session_scope
from aegis_common.events import IncidentEvent, IncidentEventType, Topic
from aegis_common.kafka import InboundMessage, KafkaBus
from aegis_common.logging import configure_logging, get_logger
from aegis_common.metrics import incr, setup_metrics
from aegis_common.models import ActionCatalogRow, IncidentRow
from aegis_common.models_remediation import ActionLedgerRow, PlanRow, PlanStepRow
from aegis_common.reliability import CircuitBreaker
from aegis_common.security import Capability, mint_credential, validate_action_params, verify_approval
from aegis_common.telemetry import setup_telemetry, tracer

from .runtime import ActionResult, get_runtime

log = get_logger(__name__)
settings = get_settings()
GROUP_ID = "action-executor"
_runtime = None
_infra_breaker = CircuitBreaker("infra", failure_threshold=3, cooldown_seconds=30)


async def handle_approved(msg: InboundMessage, bus: KafkaBus) -> None:
    event = IncidentEvent.model_validate(msg.value)
    if event.event_type != IncidentEventType.APPROVED:
        return
    incident_id = event.incident_id
    plan_id = UUID(event.data["plan_id"])
    signature = event.data.get("signature", "")
    record = event.data.get("record", {})

    # (1) Independent signature verification (ADR-014).
    if not verify_approval(record, signature):
        log.error("approval signature invalid; refusing to execute",
                  extra={"plan_id": str(plan_id)})
        await _escalate(bus, incident_id, event, "approval signature verification failed")
        return

    async with session_scope() as session:
        plan = await session.get(PlanRow, plan_id)
        inc = await session.get(IncidentRow, incident_id)
        if plan is None or inc is None:
            return
        # (2) Fencing-token currency check (ADR-009): the approval must match the incident's
        # current fencing token; a superseded owner is rejected.
        if int(record.get("fencing_token", -1)) != int(inc.fencing_token or -2):
            await _escalate(bus, incident_id, event, "stale fencing token; ownership superseded")
            return
        steps = (await session.execute(
            select(PlanStepRow).where(PlanStepRow.plan_id == plan_id).order_by(PlanStepRow.ordinal)
        )).scalars().all()
        catalog = {c.name: c for c in (await session.execute(select(ActionCatalogRow))).scalars().all()}
        plan.status = "executing"

    await bus.publish(Topic.INCIDENTS_LIFECYCLE, key=str(incident_id),
                      value=IncidentEvent(incident_id=incident_id,
                                          event_type=IncidentEventType.EXECUTING,
                                          fencing_token=inc.fencing_token,
                                          data={"plan_id": str(plan_id)}).model_dump(mode="json"))

    applied: list[tuple[PlanStepRow, ActionCatalogRow]] = []
    fencing = int(inc.fencing_token or 0)
    ok = True
    failure_detail = ""

    with tracer(__name__).start_as_current_span("executor.run") as span:
        for step in steps:
            cat = catalog.get(step.action)
            if cat is None or not cat.enabled:
                ok, failure_detail = False, f"action {step.action} not in catalog/enabled"
                break
            # (4) Validate params against the catalog schema (ADR-015).
            try:
                validate_action_params(step.action, step.params, cat.params_schema or {})
            except Exception as exc:  # noqa: BLE001
                ok, failure_detail = False, f"param validation failed: {exc}"
                break
            # (3) Mint a scoped capability per step namespace (ADR-014).
            ns = step.params.get("namespace", "default")
            cap = mint_credential(incident_id=str(incident_id), plan_id=str(plan_id),
                                  fencing_token=fencing, namespace=ns)
            result = await _execute_step(incident_id, step, cap)
            if result.ok:
                applied.append((step, cat))
            else:
                ok, failure_detail = False, result.detail
                break
        span.set_attribute("executor.ok", ok)
        span.set_attribute("executor.steps_applied", len(applied))

    if ok:
        await _resolve(bus, incident_id, plan_id, event)
    else:
        await _rollback(incident_id, plan_id, applied, fencing)
        await _escalate(bus, incident_id, event, f"execution failed: {failure_detail}")


async def _execute_step(incident_id: UUID, step: PlanStepRow, cap: Capability) -> ActionResult:
    """Execute one step idempotently with a ledger guard + circuit breaker (ADR-005/017)."""
    idem = f"{incident_id}:{step.id}:{cap.fencing_token}"
    # Idempotency: if this exact step+token already succeeded, skip re-execution.
    async with session_scope() as session:
        existing = (await session.execute(
            select(ActionLedgerRow).where(ActionLedgerRow.idempotency_key == idem)
        )).scalar_one_or_none()
        if existing and existing.result == "success":
            log.info("step already applied; idempotent skip", extra={"key": idem})
            return ActionResult(True, "idempotent-skip")

    try:
        _infra_breaker.guard()
    except Exception as exc:  # noqa: BLE001
        return ActionResult(False, f"infra circuit open: {exc}")

    result = await _runtime.apply(step.action, step.params, cap)
    if result.ok:
        _infra_breaker.record_success()
        incr("actions_executed", 1, action=step.action)
    else:
        _infra_breaker.record_failure()

    async with session_scope() as session:
        try:
            session.add(ActionLedgerRow(
                incident_id=incident_id, plan_step_id=step.id, idempotency_key=idem,
                fencing_token=cap.fencing_token, action=step.action, params=step.params,
                result="success" if result.ok else "failed", detail=result.detail))
            await append_audit(session, actor="action-executor",
                               action=f"action.{'applied' if result.ok else 'failed'}",
                               incident_id=incident_id,
                               payload={"action": step.action, "detail": result.detail})
        except IntegrityError:
            pass  # concurrent duplicate; ledger unique constraint protects us
    return result


async def _rollback(incident_id: UUID, plan_id: UUID, applied: list, fencing: int) -> None:
    """Saga compensation: undo applied reversible steps in reverse order (FR-5.4)."""
    for step, cat in reversed(applied):
        rb = cat.rollback_action
        if not rb:
            log.warning("no rollback for action; leaving applied",
                        extra={"action": step.action})
            continue
        ns = step.params.get("namespace", "default")
        cap = mint_credential(incident_id=str(incident_id), plan_id=str(plan_id),
                              fencing_token=fencing, namespace=ns)
        result = await _runtime.apply(rb, step.params, cap)
        async with session_scope() as session:
            db_step = await session.get(PlanStepRow, step.id)
            if db_step:
                db_step.status = "rolled_back"
            await append_audit(session, actor="action-executor", action="action.rolled_back",
                               incident_id=incident_id,
                               payload={"action": step.action, "rollback": rb,
                                        "ok": result.ok, "detail": result.detail})
        log.info("rolled back step", extra={"action": step.action, "ok": result.ok})


async def _resolve(bus: KafkaBus, incident_id: UUID, plan_id: UUID, event: IncidentEvent) -> None:
    async with session_scope() as session:
        plan = await session.get(PlanRow, plan_id)
        inc = await session.get(IncidentRow, incident_id)
        if plan:
            plan.status = "executed"
        if inc:
            inc.status = "resolved"
            inc.version += 1
        await append_audit(session, actor="action-executor", action="incident.resolved",
                           incident_id=incident_id, payload={"plan_id": str(plan_id)})
    # RESOLVED feeds episodic memory via the Knowledge Ingestor (closed loop, FR-4.3).
    await bus.publish(Topic.INCIDENTS_LIFECYCLE, key=str(incident_id),
                      value=IncidentEvent(incident_id=incident_id,
                                          event_type=IncidentEventType.RESOLVED,
                                          data={"plan_id": str(plan_id),
                                                "resolution": "auto-remediated",
                                                "root_cause": event.data.get("root_cause", "")}
                                          ).model_dump(mode="json"))
    log.info("incident auto-resolved", extra={"incident_id": str(incident_id)})


async def _escalate(bus: KafkaBus, incident_id: UUID, event: IncidentEvent, reason: str) -> None:
    incr("actions_rejected", 1)
    await bus.publish(Topic.INCIDENTS_LIFECYCLE, key=str(incident_id),
                      value=IncidentEvent(incident_id=incident_id,
                                          event_type=IncidentEventType.ESCALATED,
                                          data={"reason": reason}).model_dump(mode="json"))
    log.warning("execution escalated to human", extra={"incident_id": str(incident_id), "reason": reason})


async def run() -> None:
    global _runtime
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    setup_metrics(settings)
    init_engine(settings)
    _runtime = get_runtime()
    bus = KafkaBus(settings)
    await bus.start_producer()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)

    async def handler(m: InboundMessage) -> None:
        await handle_approved(m, bus)

    log.info("action executor (PEP) starting", extra={"runtime": _runtime.name})
    try:
        await bus.consume([Topic.ACTIONS_REQUESTED], GROUP_ID, handler, stop_event=stop)
    finally:
        await bus.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
