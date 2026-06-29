from pydantic import BaseModel
from typing import Optional, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum


class PaymentStatusEnum(str, Enum):
    pending   = "pending"
    succeeded = "succeeded"
    failed    = "failed"


class InitializePaymentRequest(BaseModel):
    order_id: UUID
    user_id:  UUID
    email:    str
    amount:   Decimal  # in NGN


class InitializePaymentResponse(BaseModel):
    payment_id:        UUID
    order_id:          UUID
    authorization_url: str
    reference:         str
    amount:            Decimal
    currency:          str
    status:            PaymentStatusEnum

    class Config:
        from_attributes = True


class PaymentResponse(BaseModel):
    id:                  UUID
    order_id:            UUID
    user_id:             UUID
    amount:              Decimal
    currency:            str
    status:              PaymentStatusEnum
    paystack_reference:  Optional[str] = None
    authorization_url:   Optional[str] = None
    created_at:          Optional[datetime] = None
    updated_at:          Optional[datetime] = None

    class Config:
        from_attributes = True
