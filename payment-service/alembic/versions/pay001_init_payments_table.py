"""init payments table

Revision ID: pay001
Revises:
Create Date: 2026-06-29 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'pay001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    payment_status = postgresql.ENUM(
        'pending', 'succeeded', 'failed',
        name='paymentstatus'
    )
    payment_status.create(op.get_bind())

    op.create_table(
        'payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'succeeded', 'failed',
                  name='paymentstatus', create_type=False), nullable=False),
        sa.Column('paystack_reference', sa.String(length=100), nullable=True),
        sa.Column('authorization_url', sa.String(length=500), nullable=True),
        sa.Column('paystack_response', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paystack_reference'),
    )
    op.create_index('ix_payments_order_id', 'payments', ['order_id'])
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_payments_user_id', 'payments')
    op.drop_index('ix_payments_order_id', 'payments')
    op.drop_table('payments')
    op.execute('DROP TYPE paymentstatus')
