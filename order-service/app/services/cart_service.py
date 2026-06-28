import logging
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.cart import Cart, CartItem, CartStatus

logger = logging.getLogger(__name__)


class CartService:

    @staticmethod
    async def get_active_cart(db: AsyncSession, user_id: UUID) -> Cart | None:
        result = await db.execute(
            select(Cart)
            .options(selectinload(Cart.items))
            .where(Cart.user_id == user_id, Cart.status == CartStatus.active)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_cart(db: AsyncSession, user_id: UUID) -> Cart:
        cart = await CartService.get_active_cart(db, user_id)
        if not cart:
            cart = Cart(user_id=user_id)
            db.add(cart)
            await db.commit()
            # Reload with selectinload rather than using db.refresh —
            # refresh doesn't eagerly load relationships, so accessing
            # cart.items after refresh would trigger a lazy load, which
            # raises MissingGreenlet in async SQLAlchemy.
            cart = await CartService.get_active_cart(db, user_id)
        return cart

    @staticmethod
    async def add_item(
        db: AsyncSession,
        cart: Cart,
        product_id: str,
        variant_id: str,
        product_name: str,
        size: str,
        unit_price: Decimal,
        quantity: int,
    ) -> CartItem:
        # If the same variant is already in the cart, increment quantity
        # rather than adding a second row for the same item.
        result = await db.execute(
            select(CartItem).where(
                CartItem.cart_id == cart.id,
                CartItem.variant_id == UUID(variant_id),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.quantity += quantity
            await db.commit()
            await db.refresh(existing)
            return existing

        item = CartItem(
            cart_id=cart.id,
            product_id=UUID(product_id),
            variant_id=UUID(variant_id),
            product_name=product_name,
            size=size,
            unit_price=unit_price,
            quantity=quantity,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def remove_item(db: AsyncSession, cart: Cart, item_id: str) -> bool:
        result = await db.execute(
            select(CartItem).where(
                CartItem.id == UUID(item_id),
                CartItem.cart_id == cart.id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return False
        await db.delete(item)
        await db.commit()
        return True

    @staticmethod
    async def clear_cart(db: AsyncSession, cart: Cart) -> None:
        for item in cart.items:
            await db.delete(item)
        await db.commit()

    @staticmethod
    async def mark_checked_out(db: AsyncSession, cart: Cart) -> None:
        cart.status = CartStatus.checked_out
        await db.commit()