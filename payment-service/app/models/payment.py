import uuid6
import enum
from sqlalchemy import Column, String, Numeric, DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class PaymentStatus(str, enum.Enum):
    pending   = "pending"    # initialized, awaiting user payment on Paystack page
    succeeded = "succeeded"  # webhook confirmed charge.success
    failed    = "failed"     # webhook confirmed charge.failure or timeout


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())

    # Cross-service references — no FK constraints (separate DBs)
    order_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id  = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Amount in kobo (Paystack uses smallest currency unit)
    # e.g. NGN 100.00 = 10000 kobo
    amount   = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="NGN")

    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.pending)

    # Paystack-specific fields
    paystack_reference   = Column(String(100), nullable=True, unique=True)
    authorization_url    = Column(String(500), nullable=True)
    paystack_response    = Column(JSONB, nullable=True)  # full API response for audit

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
