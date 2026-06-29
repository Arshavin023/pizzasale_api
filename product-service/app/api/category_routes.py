from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.schemas.product_schema import CategoryCreate, CategoryUpdate, CategoryResponse
from app.services.category_service import CategoryService
from app.db.session import get_db
from app.core.auth import require_staff

router = APIRouter(prefix="/categories", tags=["Categories"])


def _parse_uuid(value: str, field: str = "id") -> UUID:
    """Cast a path parameter string to UUID, returning 422 on malformed input."""
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {field} format")


@router.get("", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await CategoryService.list_categories(db)


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: str, db: AsyncSession = Depends(get_db)):
    uid = _parse_uuid(category_id, "category_id")
    category = await CategoryService.get_category(db, uid)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post("", response_model=CategoryResponse, status_code=201, dependencies=[Depends(require_staff)])
async def create_category(data: CategoryCreate, db: AsyncSession = Depends(get_db)):
    return await CategoryService.create_category(db, data.model_dump())


@router.patch("/{category_id}", response_model=CategoryResponse, dependencies=[Depends(require_staff)])
async def update_category(category_id: str, updates: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    uid = _parse_uuid(category_id, "category_id")
    category = await CategoryService.get_category(db, uid)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return await CategoryService.update_category(db, category, updates.model_dump(exclude_unset=True))


@router.delete("/{category_id}", status_code=204, dependencies=[Depends(require_staff)])
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db)):
    uid = _parse_uuid(category_id, "category_id")
    category = await CategoryService.get_category(db, uid)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    await CategoryService.delete_category(db, category)