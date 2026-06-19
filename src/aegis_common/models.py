"""SQLAlchemy ORM models — the storage representation (ADR-012, ADR-014).

Design choices:
  * incidents.version  -> optimistic concurrency (ADR-009 final-arbiter on writes).
  * audit_log is append-only and HASH-CHAINED (prev_hash -> hash) for tamper-evidence
    (ADR-014); the application never updates or deletes audit rows.
  * fencing tokens come from a dedicated Postgres SEQUENCE (created in migrations),
    giving a linearizable monotonic source (ADR-009), not Redis.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list: JSONB}


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(Text)
    services: Mapped[list] = mapped_column(JSONB, default=list)
    fencing_token: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    signals: Mapped[list["SignalRow"]] = relationship(back_populates="incident")


class SignalRow(Base):
    __tablename__ = "signals"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(128))
    service: Mapped[str] = mapped_column(String(256), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16))
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    incident: Mapped[Optional[IncidentRow]] = relationship(back_populates="signals")


class AuditRow(Base):
    """Append-only, hash-chained audit log (ADR-014). Never UPDATE/DELETE.

    `seq` is a contiguous per-chain counter; `hash` = H(seq || prev_hash || canonical(payload)).
    A break anywhere in the chain is detectable by recomputation.
    """

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(128))  # service or human principal
    action: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    trace_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionCatalogRow(Base):
    """Governed action catalog (ADR-007). The only actions agents may request."""

    __tablename__ = "action_catalog"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    params_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # JSON Schema
    risk_tier: Mapped[str] = mapped_column(String(16))  # low | medium | high
    requires_approval: Mapped[bool] = mapped_column(default=True)
    rollback_action: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True)


class PolicyRow(Base):
    """Autonomy policy per environment/service/severity (FR-7.1)."""

    __tablename__ = "policies"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    environment: Mapped[str] = mapped_column(String(32), index=True)
    service_pattern: Mapped[str] = mapped_column(String(256), default="*")
    max_severity: Mapped[str] = mapped_column(String(16), default="sev3")
    mode: Mapped[str] = mapped_column(String(16), default="suggest")  # observe|suggest|auto_low
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
