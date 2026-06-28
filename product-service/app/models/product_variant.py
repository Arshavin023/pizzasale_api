import uuid6
import enum
from sqlalchemy import Column, Numeric, Boolean, DateTime, ForeignKey, Enum, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class SizeEnum(str, enum.Enum):
    small = "small"
    medium = "medium"
    large = "large"


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        # A product can't have two "large" variants — one price per
        # size, per product.
        UniqueConstraint("product_id", "size", name="uq_product_size"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)

    size = Column(Enum(SizeEnum), nullable=False)

    # Numeric, not Float — Float introduces real floating-point
    # rounding error for money (classic 0.1 + 0.2 != 0.3 problem).
    # Numeric(10, 2) is exact: up to 10 digits total, 2 after the
    # decimal point — correct for currency.
    price = Column(Numeric(10, 2), nullable=False)

    is_available = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="variants")