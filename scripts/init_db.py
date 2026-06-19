"""Local DB bootstrap: create schema, fencing sequence, and seed catalog + policy.

For local development this is a faster alternative to running Alembic. In CI/prod use
`alembic upgrade head` (same metadata). Idempotent: safe to re-run.

    python scripts/init_db.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select, text

from aegis_common.config import get_settings
from aegis_common.db import init_engine, session_scope
from aegis_common.models import ActionCatalogRow, Base, PolicyRow
# Importing this module registers the remediation/workflow tables on Base.metadata.
import aegis_common.models_remediation  # noqa: F401

SEED_ACTIONS = [
    dict(name="restart_deployment", description="Roll-restart a Kubernetes deployment",
         params_schema={"type": "object", "required": ["namespace", "deployment"]},
         risk_tier="low", requires_approval=False, rollback_action=None),
    dict(name="scale_replicas", description="Scale a deployment's replica count",
         params_schema={"type": "object", "required": ["namespace", "deployment", "replicas"]},
         risk_tier="medium", requires_approval=True, rollback_action="scale_replicas"),
    dict(name="rollback_revision", description="Roll back a deployment to its previous revision",
         params_schema={"type": "object", "required": ["namespace", "deployment"]},
         risk_tier="high", requires_approval=True, rollback_action=None),
    dict(name="clear_cache", description="Flush an application cache namespace",
         params_schema={"type": "object", "required": ["namespace", "cache"]},
         risk_tier="low", requires_approval=False, rollback_action=None),
]


async def main() -> None:
    settings = get_settings()
    engine = init_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE SEQUENCE IF NOT EXISTS aegis_fencing_token_seq START 1"))

    async with session_scope() as session:
        for spec in SEED_ACTIONS:
            exists = await session.get(ActionCatalogRow, spec["name"])
            if not exists:
                session.add(ActionCatalogRow(**spec))
        has_policy = (await session.execute(select(PolicyRow).limit(1))).scalar_one_or_none()
        if not has_policy:
            session.add(PolicyRow(environment="local", service_pattern="*",
                                  max_severity="sev3", mode="suggest"))
    print("DB initialised: schema + fencing sequence + seed catalog/policy")


if __name__ == "__main__":
    asyncio.run(main())
