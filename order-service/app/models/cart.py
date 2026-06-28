import uuid6
import enum
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class CartStatus(str, enum.Enum):
    active = "active"
    checked_out = "checked_out"


class Cart(Base):
    __tablename__ = "carts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(Enum(CartStatus), nullable=False, default=CartStatus.active)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
    cart_id = Column(UUID(as_uuid=True), ForeignKey("carts.id"), nullable=False, index=True)

    # Cross-service references — no FK constraints since product_service_db
    # is a separate database entirely.
    product_id = Column(UUID(as_uuid=True), nullable=False)
    variant_id = Column(UUID(as_uuid=True), nullable=False)

    # Price/name snapshots at add time — re-verified at checkout
    product_name = Column(String(150), nullable=False)
    size = Column(String(20), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)

    quantity = Column(Integer, nullable=False, default=1)
    added_at = Column(DateTime, default=func.now())

    cart = relationship("Cart", back_populates="items")
