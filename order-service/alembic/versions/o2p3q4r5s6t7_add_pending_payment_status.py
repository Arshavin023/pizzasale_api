"""add pending_payment to orderstatus enum

Revision ID: o2p3q4r5s6t7
Revises: o1p2q3r4s5t6
Create Date: 2026-06-29 20:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'o2p3q4r5s6t7'
down_revision: Union[str, None] = 'o1p2q3r4s5t6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL requires this specific approach to add a value to an existing enum
    op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'pending_payment' BEFORE 'confirmed'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — downgrade is a no-op
    pass
