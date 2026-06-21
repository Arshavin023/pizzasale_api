from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.product_schema import ProductCreate, ProductUpdate, ProductResponse
from app.services.product_service import ProductService
from app.db.session import get_db
from app.core.auth import require_staff

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=list[ProductResponse])
async def list_products(
    category_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await ProductService.list_products(db, category_id=category_id)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    product = await ProductService.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=ProductResponse, status_code=201, dependencies=[Depends(require_staff)])
async def create_product(data: ProductCreate, db: AsyncSession = Depends(get_db)):
    payload = data.model_dump()
    return await ProductService.create_product(db, payload)


@router.patch("/{product_id}", response_model=ProductResponse, dependencies=[Depends(require_staff)])
async def update_product(product_id: str, updates: ProductUpdate, db: AsyncSession = Depends(get_db)):
    product = await ProductService.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return await ProductService.update_product(db, product, updates.model_dump(exclude_unset=True))


@router.delete("/{product_id}", status_code=204, dependencies=[Depends(require_staff)])
async def delete_product(product_id: str, db: AsyncSession = Depends(get_db)):
    product = await ProductService.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await ProductService.delete_product(db, product)