import uuid6
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False, index=True)

    name = Column(String(150), nullable=False)
    description = Column(String(500), nullable=True)

    # Product-level availability — e.g. taken off the menu entirely,
    # distinct from a single size being temporarily unavailable
    # (that's tracked per-variant, see ProductVariant.is_available).
    is_available = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    category = relationship("Category", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")