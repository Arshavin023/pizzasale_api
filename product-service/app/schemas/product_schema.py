from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum


class SizeEnum(str, Enum):
    small = "small"
    medium = "medium"
    large = "large"


# ---- Category ----

class CategoryCreate(BaseModel):
    name: str
    display_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    display_order: int
    is_active: bool

    class Config:
        from_attributes = True


# ---- Product Variant ----

class ProductVariantCreate(BaseModel):
    size: SizeEnum
    price: Decimal = Field(gt=0, decimal_places=2)
    is_available: bool = True


class ProductVariantUpdate(BaseModel):
    price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    is_available: Optional[bool] = None


class ProductVariantResponse(BaseModel):
    id: UUID
    size: SizeEnum
    price: Decimal
    is_available: bool

    class Config:
        from_attributes = True


# ---- Product ----

class ProductCreate(BaseModel):
    category_id: UUID
    name: str
    description: Optional[str] = None
    is_available: bool = True
    variants: List[ProductVariantCreate]


class ProductUpdate(BaseModel):
    category_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_available: Optional[bool] = None


class ProductResponse(BaseModel):
    id: UUID
    category_id: UUID
    name: str
    description: Optional[str] = None
    is_available: bool
    variants: List[ProductVariantResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True