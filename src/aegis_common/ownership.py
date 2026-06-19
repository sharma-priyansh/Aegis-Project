"""Incident-ownership primitives (ADR-009).

Single-driver semantics come from Kafka's single-consumer-per-partition guarantee on
`incidents.lifecycle` (keyed by incident_id). The *action path* is additionally guarded
by a monotonic fencing token drawn from a linearizable Postgres sequence here — so a
stale owner whose work was superseded cannot execute, because its token is no longer the
highest issued for that incident.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def next_fencing_token(session: AsyncSession) -> int:
    """Return the next monotonic fencing token from the Postgres sequence."""
    result = await session.execute(text("SELECT nextval('aegis_fencing_token_seq')"))
    return int(result.scalar_one())
