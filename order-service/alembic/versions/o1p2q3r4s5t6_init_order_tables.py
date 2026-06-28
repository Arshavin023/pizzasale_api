"""init order tables

Revision ID: o1p2q3r4s5t6
Revises:
Create Date: 2026-06-21 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'o1p2q3r4s5t6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cart_status = postgresql.ENUM('active', 'checked_out', name='cartstatus')
    cart_status.create(op.get_bind())

    order_status = postgresql.ENUM(
        'draft', 'confirmed', 'paid', 'shipped', 'delivered', 'cancelled',
        name='orderstatus'
    )
    order_status.create(op.get_bind())

    op.create_table('carts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'checked_out', name='cartstatus', create_type=False), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_carts_user_id', 'carts', ['user_id'])

    op.create_table('cart_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cart_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('variant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_name', sa.String(length=150), nullable=False),
        sa.Column('size', sa.String(length=20), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['cart_id'], ['carts.id']),
    )
    op.create_index('ix_cart_items_cart_id', 'cart_items', ['cart_id'])

    op.create_table('orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', postgresql.ENUM('draft', 'confirmed', 'paid', 'shipped', 'delivered', 'cancelled', name='orderstatus', create_type=False), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_orders_user_id', 'orders', ['user_id'])

    op.create_table('order_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('variant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_name', sa.String(length=150), nullable=False),
        sa.Column('size', sa.String(length=20), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
    )
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'])


def downgrade() -> None:
    op.drop_index('ix_order_items_order_id', 'order_items')
    op.drop_table('order_items')
    op.drop_index('ix_orders_user_id', 'orders')
    op.drop_table('orders')
    op.drop_index('ix_cart_items_cart_id', 'cart_items')
    op.drop_table('cart_items')
    op.drop_index('ix_carts_user_id', 'carts')
    op.drop_table('carts')
    op.execute('DROP TYPE orderstatus')
    op.execute('DROP TYPE cartstatus')
