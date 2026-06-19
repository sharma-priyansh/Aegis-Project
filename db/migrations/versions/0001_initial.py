"""initial schema + fencing-token sequence

Creates all Aegis tables from the ORM metadata and the linearizable fencing-token
sequence used for incident ownership on the action path (ADR-009).

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-19
"""
from alembic import op

from aegis_common.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Create all tables defined on the ORM metadata (single source of truth).
    Base.metadata.create_all(bind=bind)
    # Linearizable, monotonic fencing-token source (ADR-009). Not expressible via ORM.
    op.execute("CREATE SEQUENCE IF NOT EXISTS aegis_fencing_token_seq START 1 INCREMENT 1")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP SEQUENCE IF EXISTS aegis_fencing_token_seq")
    Base.metadata.drop_all(bind=bind)
