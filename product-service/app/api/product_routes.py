from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from app.schemas.product_schema import ProductCreate, ProductUpdate, ProductResponse
from app.services.product_service import ProductService
from app.db.session import get_db
from app.core.auth import require_staff

router = APIRouter(prefix="/products", tags=["Products"])


def _parse_uuid(value: str, field: str = "id") -> UUID:
    """Cast a path parameter string to UUID, returning 422 on malformed input."""
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {field} format")


@router.get("", response_model=list[ProductResponse])
async def list_products(
    category_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    # Cast category_id query param if provided — same reasoning as path params
    uid = _parse_uuid(category_id, "category_id") if category_id else None
    return await ProductService.list_products(db, category_id=uid)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    uid = _parse_uuid(product_id, "product_id")
    product = await ProductService.get_product(db, uid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=ProductResponse, status_code=201, dependencies=[Depends(require_staff)])
async def create_product(data: ProductCreate, db: AsyncSession = Depends(get_db)):
    payload = data.model_dump()
    return await ProductService.create_product(db, payload)


@router.patch("/{product_id}", response_model=ProductResponse, dependencies=[Depends(require_staff)])
async def update_product(product_id: str, updates: ProductUpdate, db: AsyncSession = Depends(get_db)):
    uid = _parse_uuid(product_id, "product_id")
    product = await ProductService.get_product(db, uid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return await ProductService.update_product(db, product, updates.model_dump(exclude_unset=True))


@router.delete("/{product_id}", status_code=204, dependencies=[Depends(require_staff)])
async def delete_product(product_id: str, db: AsyncSession = Depends(get_db)):
    uid = _parse_uuid(product_id, "product_id")
    product = await ProductService.get_product(db, uid)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await ProductService.delete_product(db, product)