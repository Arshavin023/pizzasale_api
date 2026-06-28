import logging
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderItem, OrderStatus
from app.utils.product_client import get_variant, ProductServiceError
from app.utils.events import publish_order_placed

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """User-facing checkout failure — price changed, item unavailable, etc."""
    pass


class OrderService:

    @staticmethod
    async def checkout(db: AsyncSession, cart: Cart, user_id: UUID) -> Order:
        """
        The core checkout flow:
        1. Re-verify each cart item's price and availability against product-service.
        2. Create an immutable order with locked prices.
        3. Mark the cart as checked_out.
        4. Publish order.placed event for payment-service to consume later.
        """
        # Reload cart with items eagerly — never trust the passed-in cart
        # object's relationship state, since SQLAlchemy async doesn't support
        # lazy loading and the items collection may not be populated.
        result = await db.execute(
            select(Cart)
            .options(selectinload(Cart.items))
            .where(Cart.id == cart.id)
        )
        cart = result.scalar_one_or_none()

        if not cart or not cart.items:
            raise CheckoutError("Cannot checkout an empty cart")

        # Phase 1: verify all items against product-service before
        # writing anything — fail fast if anything is unavailable.
        verified_items = []
        price_changes = []

        for cart_item in cart.items:
            try:
                live = await get_variant(
                    str(cart_item.product_id),
                    str(cart_item.variant_id),
                )
            except ProductServiceError as e:
                raise CheckoutError(str(e))

            if live is None:
                raise CheckoutError(
                    f"'{cart_item.product_name}' ({cart_item.size}) is no longer "
                    f"available. Please remove it from your cart and try again."
                )

            if not live["is_available"]:
                raise CheckoutError(
                    f"'{cart_item.product_name}' ({cart_item.size}) is currently "
                    f"out of stock."
                )

            live_price = Decimal(str(live["unit_price"]))
            if live_price != cart_item.unit_price:
                price_changes.append({
                    "item": cart_item.product_name,
                    "size": cart_item.size,
                    "old_price": str(cart_item.unit_price),
                    "new_price": str(live_price),
                })

            verified_items.append({
                "cart_item": cart_item,
                "live_price": live_price,
                "product_name": live["product_name"],
                "size": live["size"],
            })

        # Phase 2: all items verified — create the order with locked prices.
        total = sum(
            v["live_price"] * v["cart_item"].quantity
            for v in verified_items
        )

        order = Order(
            user_id=user_id,
            status=OrderStatus.confirmed,
            total_amount=total,
        )
        db.add(order)
        await db.flush()  # get order.id before creating items

        order_items_payload = []
        for v in verified_items:
            ci = v["cart_item"]
            subtotal = v["live_price"] * ci.quantity
            oi = OrderItem(
                order_id=order.id,
                product_id=ci.product_id,
                variant_id=ci.variant_id,
                product_name=v["product_name"],
                size=v["size"],
                unit_price=v["live_price"],
                quantity=ci.quantity,
                subtotal=subtotal,
            )
            db.add(oi)
            order_items_payload.append({
                "product_id": str(ci.product_id),
                "variant_id": str(ci.variant_id),
                "product_name": v["product_name"],
                "size": v["size"],
                "unit_price": str(v["live_price"]),
                "quantity": ci.quantity,
                "subtotal": str(subtotal),
            })

        # Phase 3: mark cart as checked out, all in one transaction.
        cart.status = "checked_out"
        await db.commit()
        # await db.refresh(order)

        result = await db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == order.id)
        )
        order = result.scalar_one()


        # Phase 4: publish event (outside the transaction — failure here
        # does not roll back the order).
        publish_order_placed(
            order_id=str(order.id),
            user_id=str(user_id),
            total_amount=str(total),
            items=order_items_payload,
        )

        order._price_changes = price_changes
        return order

    @staticmethod
    async def get_order(db: AsyncSession, order_id: str, user_id: UUID) -> Order | None:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == UUID(order_id), Order.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_orders(db: AsyncSession, user_id: UUID) -> list[Order]:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
        )
        return result.scalars().all()