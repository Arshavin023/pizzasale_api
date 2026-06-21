from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.product import Product
from app.models.product_variant import ProductVariant


class ProductService:

    @staticmethod
    async def list_products(
        db: AsyncSession,
        category_id: str | None = None,
        available_only: bool = True,
    ):
        query = select(Product).options(selectinload(Product.variants))

        if available_only:
            query = query.where(Product.is_available == True)  # noqa: E712
        if category_id:
            query = query.where(Product.category_id == category_id)

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_product(db: AsyncSession, product_id: str) -> Product | None:
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_product(db: AsyncSession, data: dict) -> Product:
        variants_data = data.pop("variants")

        product = Product(**data)
        db.add(product)
        await db.flush()  # assigns product.id without committing yet

        for variant_data in variants_data:
            variant = ProductVariant(product_id=product.id, **variant_data)
            db.add(variant)

        await db.commit()
        await db.refresh(product)

        # Reload with variants eagerly loaded for the response
        return await ProductService.get_product(db, str(product.id))

    @staticmethod
    async def update_product(db: AsyncSession, product: Product, updates: dict) -> Product:
        for field, value in updates.items():
            setattr(product, field, value)
        await db.commit()
        await db.refresh(product)
        return await ProductService.get_product(db, str(product.id))

    @staticmethod
    async def delete_product(db: AsyncSession, product: Product) -> None:
        await db.delete(product)
        await db.commit()