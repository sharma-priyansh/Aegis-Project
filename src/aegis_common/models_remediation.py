"""ORM models for the agent workflow + remediation path (ADR-007/014/016).

Registered on the same Base.metadata as models.py, so `create_all` / Alembic pick them
up when this module is imported. Keep this import alongside models wherever the schema is
created (scripts/init_db.py and db/migrations/env.py do so).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class WorkflowSnapshotRow(Base):
    """Durable snapshot of IncidentState after the agent run (ADR-006)."""

    __tablename__ = "workflow_snapshots"

    incident_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlanRow(Base):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed", index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    autonomy_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanStepRow(Base):
    __tablename__ = "plan_steps"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("plans.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(128))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    risk_tier: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|applied|rolled_back|failed


class ApprovalRow(Base):
    """Immutable approval/rejection record; signed for the credential issuer (ADR-014)."""

    __tablename__ = "approvals"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    incident_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    decision: Mapped[str] = mapped_column(String(16))  # approved | rejected
    approver: Mapped[str] = mapped_column(String(128))
    fencing_token: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(String(128))  # HMAC over the approval record
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionLedgerRow(Base):
    """Append-only execution ledger — idempotency + fencing (ADR-005/009)."""

    __tablename__ = "actions_ledger"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), index=True)
    plan_step_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    fencing_token: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(128))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[str] = mapped_column(String(32))  # success | failed | rolled_back
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
