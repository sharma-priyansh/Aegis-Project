"""Policy & Approval service API — the PDP (ADR-007/014).

Endpoints:
  * GET  /v1/plans/pending          — plans awaiting human approval (Console reads this).
  * GET  /v1/plans/{plan_id}        — plan detail with per-step dispositions.
  * POST /v1/plans/{plan_id}/decision — human approves/rejects; writes a SIGNED, immutable
        approval record (ADR-014) and, on approval, emits actions.requested for the Executor.

This service decides and records; it never executes (PDP, not PEP). The Action Executor
independently verifies the signature before acting (ADR-014).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel
from sqlalchemy import select

from aegis_common.audit import append_audit
from aegis_common.config import get_settings
from aegis_common.db import init_engine, session_scope
from aegis_common.events import IncidentEvent, IncidentEventType, Topic
from aegis_common.kafka import KafkaBus
from aegis_common.logging import configure_logging, get_logger
from aegis_common.metrics import incr, setup_metrics
from aegis_common.models import IncidentRow, PolicyRow
from aegis_common.models_remediation import ApprovalRow, PlanRow, PlanStepRow
from aegis_common.security import sign_approval
from aegis_common.telemetry import setup_telemetry, tracer

from .policy import PolicyMode, StepContext, evaluate_step

log = get_logger(__name__)
settings = get_settings()
_bus: Optional[KafkaBus] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bus
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    setup_metrics(settings)
    init_engine(settings)
    _bus = KafkaBus(settings)
    await _bus.start_producer()
    log.info("policy/approval (PDP) ready")
    yield
    await _bus.stop()


app = FastAPI(title="Aegis Policy & Approval (PDP)", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


class StepOut(BaseModel):
    step_id: UUID
    ordinal: int
    action: str
    params: dict
    risk_tier: str
    disposition: str


class PlanOut(BaseModel):
    plan_id: UUID
    incident_id: UUID
    status: str
    rationale: str
    requires_approval: bool
    autonomy_allowed: bool
    steps: list[StepOut]


async def _policy_mode(session, environment: str) -> PolicyMode:
    row = (await session.execute(
        select(PolicyRow).where(PolicyRow.environment == environment).limit(1))).scalar_one_or_none()
    return PolicyMode(row.mode) if row else PolicyMode.SUGGEST


async def _plan_out(session, plan: PlanRow) -> PlanOut:
    steps = (await session.execute(
        select(PlanStepRow).where(PlanStepRow.plan_id == plan.id).order_by(PlanStepRow.ordinal)
    )).scalars().all()
    mode = await _policy_mode(session, settings.environment)
    out_steps = []
    for s in steps:
        disp = evaluate_step(mode, StepContext(
            risk_tier=s.risk_tier, catalog_requires_approval=plan.requires_approval,
            autonomy_allowed=plan.autonomy_allowed))
        out_steps.append(StepOut(step_id=s.id, ordinal=s.ordinal, action=s.action,
                                 params=s.params, risk_tier=s.risk_tier, disposition=disp.value))
    return PlanOut(plan_id=plan.id, incident_id=plan.incident_id, status=plan.status,
                   rationale=plan.rationale, requires_approval=plan.requires_approval,
                   autonomy_allowed=plan.autonomy_allowed, steps=out_steps)


@app.get("/v1/plans/pending", response_model=list[PlanOut])
async def pending_plans() -> list[PlanOut]:
    async with session_scope() as session:
        plans = (await session.execute(
            select(PlanRow).where(PlanRow.status == "proposed"))).scalars().all()
        return [await _plan_out(session, p) for p in plans]


@app.get("/v1/plans/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: UUID) -> PlanOut:
    async with session_scope() as session:
        plan = await session.get(PlanRow, plan_id)
        if plan is None:
            raise HTTPException(404, "plan not found")
        return await _plan_out(session, plan)


class Decision(BaseModel):
    decision: str  # approved | rejected
    approver: str


@app.post("/v1/plans/{plan_id}/decision")
async def decide(plan_id: UUID, body: Decision) -> dict:
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved|rejected")
    with tracer(__name__).start_as_current_span("pdp.decide") as span:
        async with session_scope() as session:
            plan = await session.get(PlanRow, plan_id)
            if plan is None:
                raise HTTPException(404, "plan not found")
            if plan.status != "proposed":
                raise HTTPException(409, f"plan already {plan.status}")
            inc = await session.get(IncidentRow, plan.incident_id)
            fencing = inc.fencing_token if inc else 0

            # Build and SIGN the immutable approval record (ADR-014).
            record = {"plan_id": str(plan_id), "incident_id": str(plan.incident_id),
                      "decision": body.decision, "approver": body.approver,
                      "fencing_token": fencing}
            signature = sign_approval(record)
            session.add(ApprovalRow(plan_id=plan_id, incident_id=plan.incident_id,
                                    decision=body.decision, approver=body.approver,
                                    fencing_token=fencing, signature=signature))
            plan.status = "approved" if body.decision == "approved" else "rejected"
            await append_audit(session, actor=f"human:{body.approver}",
                               action=f"plan.{body.decision}", incident_id=plan.incident_id,
                               payload={"plan_id": str(plan_id), "fencing_token": fencing})
            span.set_attribute("approval.decision", body.decision)

        # On approval, request execution (PEP acts next). On rejection, escalate back.
        assert _bus is not None
        if body.decision == "approved":
            event = IncidentEvent(incident_id=plan.incident_id,
                                  event_type=IncidentEventType.APPROVED, fencing_token=fencing,
                                  data={"plan_id": str(plan_id), "approver": body.approver,
                                        "signature": signature, "record": record})
            await _bus.publish(Topic.ACTIONS_REQUESTED, key=str(plan.incident_id),
                               value=event.model_dump(mode="json"))
            incr("actions_executed", 0)  # counted at execution; here we mark the request
        else:
            incr("actions_rejected", 1)
        return {"status": plan.status}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    uvicorn.run("aegis_services.policy_approval.app:app", host="0.0.0.0",
                port=int(os.getenv("PORT", "8005")), log_config=None)


if __name__ == "__main__":
    main()
