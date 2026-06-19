"""Hash-chained audit log writer (ADR-014).

Each audit record commits the previous record's hash, forming a tamper-evident chain:
    hash_n = sha256(seq_n || prev_hash || canonical_json(payload))
Any retroactive edit breaks every subsequent hash, which `verify_chain` detects.

The writer serialises appends per chain via a transactional read of the latest row.
For Phase 1 there is a single global chain (incident_id is recorded but the chain is
global); per-incident chains are a straightforward extension.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional
from uuid import UUID

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditRow

GENESIS_HASH = "0" * 64


def _compute_hash(seq: int, prev_hash: str, payload: dict[str, Any]) -> str:
    canonical = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    raw = f"{seq}|{prev_hash}|".encode() + canonical
    return hashlib.sha256(raw).hexdigest()


async def append_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    payload: dict[str, Any],
    incident_id: Optional[UUID] = None,
    trace_id: Optional[str] = None,
) -> AuditRow:
    """Append one tamper-evident audit record. Caller controls the transaction."""
    last = (
        await session.execute(select(AuditRow).order_by(AuditRow.seq.desc()).limit(1))
    ).scalar_one_or_none()
    prev_hash = last.hash if last else GENESIS_HASH
    next_seq = (last.seq + 1) if last else 1
    row = AuditRow(
        seq=next_seq,
        incident_id=incident_id,
        actor=actor,
        action=action,
        payload=payload,
        trace_id=trace_id,
        prev_hash=prev_hash,
        hash=_compute_hash(next_seq, prev_hash, payload),
    )
    session.add(row)
    return row


async def verify_chain(session: AsyncSession) -> bool:
    """Recompute the chain and return True iff intact (used in tests/audits)."""
    rows = (await session.execute(select(AuditRow).order_by(AuditRow.seq.asc()))).scalars().all()
    prev_hash = GENESIS_HASH
    for row in rows:
        expected = _compute_hash(row.seq, prev_hash, row.payload)
        if expected != row.hash or row.prev_hash != prev_hash:
            return False
        prev_hash = row.hash
    return True
