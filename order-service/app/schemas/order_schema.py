from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum


class CartItemAdd(BaseModel):
    product_id: UUID
    variant_id: UUID
    product_name: str
    size: str
    unit_price: Decimal = Field(gt=0, decimal_places=2)
    quantity: int = Field(ge=1, default=1)


class CartItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    variant_id: UUID
    product_name: str
    size: str
    unit_price: Decimal
    quantity: int
    added_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    id: UUID
    status: str
    items: List[CartItemResponse] = []

    class Config:
        from_attributes = True


class OrderStatusEnum(str, Enum):
    draft = "draft"
    confirmed = "confirmed"
    paid = "paid"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class OrderItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    variant_id: UUID
    product_name: str
    size: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: UUID
    status: OrderStatusEnum
    total_amount: Decimal
    items: List[OrderItemResponse] = []
    price_changes: List[Any] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
