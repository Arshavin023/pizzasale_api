import uuid6
import enum
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class OrderStatus(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"   # order-service drives this (checkout)
    paid = "paid"             # payment-service will drive this later
    shipped = "shipped"       # shipping-service will drive this later
    delivered = "delivered"   # shipping-service will drive this later
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.draft)
    total_amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)

    product_id = Column(UUID(as_uuid=True), nullable=False)
    variant_id = Column(UUID(as_uuid=True), nullable=False)

    # Full price snapshot — immutable after order creation
    product_name = Column(String(150), nullable=False)
    size = Column(String(20), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
