"""Persistence helpers for incidents and signals (keeps services thin).

Writes go through here so optimistic-concurrency (ADR-009) and audit appends are applied
consistently. Read helpers back the Console API (CQRS-lite read path).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import IncidentRow, SignalRow
from .schemas import Incident, IncidentStatus, Signal


class ConcurrencyError(RuntimeError):
    """Raised when an optimistic-concurrency version check fails."""


async def persist_signal(session: AsyncSession, signal: Signal, incident_id: Optional[UUID]) -> SignalRow:
    row = SignalRow(
        id=signal.signal_id,
        incident_id=incident_id,
        kind=signal.kind.value,
        source=signal.source,
        service=signal.service,
        title=signal.title,
        description=signal.description,
        severity=signal.severity.value,
        labels=signal.labels,
        value=signal.value,
        fingerprint=signal.fingerprint(),
        observed_at=signal.observed_at,
    )
    session.add(row)
    return row


async def create_incident(session: AsyncSession, incident: Incident) -> IncidentRow:
    row = IncidentRow(
        id=incident.incident_id,
        status=incident.status.value,
        severity=incident.severity.value,
        title=incident.title,
        services=incident.services,
        fencing_token=incident.fencing_token,
        version=0,
        extra=incident.extra,
    )
    session.add(row)
    return row


async def get_incident(session: AsyncSession, incident_id: UUID) -> Optional[IncidentRow]:
    return await session.get(IncidentRow, incident_id)


async def list_incidents(
    session: AsyncSession, *, status: Optional[str] = None, limit: int = 100
) -> Sequence[IncidentRow]:
    stmt = select(IncidentRow).order_by(IncidentRow.opened_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(IncidentRow.status == status)
    return (await session.execute(stmt)).scalars().all()


async def update_status(
    session: AsyncSession, incident_id: UUID, new_status: IncidentStatus, expected_version: int
) -> IncidentRow:
    """Advance incident status with an optimistic-concurrency check (ADR-009).

    Raises ConcurrencyError if another writer advanced the row first.
    """
    row = await session.get(IncidentRow, incident_id, with_for_update=True)
    if row is None:
        raise ValueError(f"incident {incident_id} not found")
    if row.version != expected_version:
        raise ConcurrencyError(
            f"version mismatch: expected {expected_version}, found {row.version}"
        )
    row.status = new_status.value
    row.version += 1
    if new_status == IncidentStatus.RESOLVED:
        row.resolved_at = datetime.now(timezone.utc)
    return row


async def find_open_incident_for_service(
    session: AsyncSession, service: str
) -> Optional[IncidentRow]:
    """Return an active incident already covering `service`, if any (for correlation)."""
    stmt = (
        select(IncidentRow)
        .where(IncidentRow.status.notin_([IncidentStatus.RESOLVED.value]))
        .order_by(IncidentRow.opened_at.desc())
    )
    for row in (await session.execute(stmt)).scalars().all():
        if service in (row.services or []):
            return row
    return None
