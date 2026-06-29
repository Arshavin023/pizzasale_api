"""
Unit tests for OrderService.

product_client.get_variant and events.publish_order_placed are mocked
so tests don't need a real product-service or RabbitMQ running.
"""
import uuid
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from app.models.cart import CartStatus
from app.models.order import OrderStatus
from app.services.cart_service import CartService
from app.services.order_service import OrderService, CheckoutError
from app.utils.product_client import ProductServiceError


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _str_uuid() -> str:
    return str(uuid.uuid4())


def _live_variant(
    product_name: str = "Margherita",
    size: str = "large",
    price: str = "14.99",
    is_available: bool = True,
) -> dict:
    """Helper that returns the shape get_variant returns when product-service is up."""
    return {
        "product_name": product_name,
        "size": size,
        "unit_price": price,
        "is_available": is_available,
    }


async def _seed_cart(db, user_id: uuid.UUID, items: list[dict]) -> object:
    """Create a cart with items for a given user."""
    cart = await CartService.get_or_create_cart(db, user_id)
    for item in items:
        await CartService.add_item(
            db, cart,
            product_id=item["product_id"],
            variant_id=item["variant_id"],
            product_name=item["product_name"],
            size=item["size"],
            unit_price=Decimal(item["unit_price"]),
            quantity=item.get("quantity", 1),
        )
    # Reload with items
    return await CartService.get_active_cart(db, user_id)


# ── checkout — happy path ─────────────────────────────────────────────────

@pytest.mark.asyncio
class TestCheckoutHappyPath:

    async def test_checkout_creates_confirmed_order(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 2,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed") as mock_pub:
            mock_gv.return_value = _live_variant()
            mock_pub.return_value = None

            order = await OrderService.checkout(db, cart, user_id)

        assert order.status == OrderStatus.confirmed
        assert order.user_id == user_id

    async def test_checkout_locks_price_from_product_service(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        # product-service returns a different (live) price
        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant(price="16.99")

            order = await OrderService.checkout(db, cart, user_id)

        # Order must use the live price, not the cart snapshot price
        assert order.total_amount == Decimal("16.99")
        assert order.items[0].unit_price == Decimal("16.99")

    async def test_checkout_records_price_change(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant(price="16.99")

            order = await OrderService.checkout(db, cart, user_id)

        assert len(order._price_changes) == 1
        assert order._price_changes[0]["old_price"] == "14.99"
        assert order._price_changes[0]["new_price"] == "16.99"

    async def test_checkout_no_price_changes_when_price_matches(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant(price="14.99")

            order = await OrderService.checkout(db, cart, user_id)

        assert order._price_changes == []

    async def test_checkout_calculates_correct_total(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 3,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant(price="14.99")

            order = await OrderService.checkout(db, cart, user_id)

        assert order.total_amount == Decimal("44.97")

    async def test_checkout_creates_order_items(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 2,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant()

            order = await OrderService.checkout(db, cart, user_id)

        assert len(order.items) == 1
        assert order.items[0].quantity == 2
        assert order.items[0].subtotal == Decimal("29.98")

    async def test_checkout_marks_cart_as_checked_out(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant()
            await OrderService.checkout(db, cart, user_id)

        # Active cart should no longer exist after checkout
        active = await CartService.get_active_cart(db, user_id)
        assert active is None

    async def test_checkout_publishes_order_placed_event(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed") as mock_pub:
            mock_gv.return_value = _live_variant()
            await OrderService.checkout(db, cart, user_id)

        mock_pub.assert_called_once()
        call_kwargs = mock_pub.call_args
        assert call_kwargs is not None


# ── checkout — failure cases ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestCheckoutFailures:

    async def test_empty_cart_raises_checkout_error(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)

        with pytest.raises(CheckoutError, match="empty cart"):
            await OrderService.checkout(db, cart, user_id)

    async def test_unavailable_product_raises_checkout_error(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            # product-service returns None — product doesn't exist
            mock_gv.return_value = None

            with pytest.raises(CheckoutError):
                await OrderService.checkout(db, cart, user_id)

    async def test_out_of_stock_variant_raises_checkout_error(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant(is_available=False)

            with pytest.raises(CheckoutError, match="out of stock"):
                await OrderService.checkout(db, cart, user_id)

    async def test_product_service_unreachable_raises_checkout_error(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.side_effect = ProductServiceError("Connection refused")

            with pytest.raises(CheckoutError, match="Connection refused"):
                await OrderService.checkout(db, cart, user_id)

    async def test_failed_checkout_does_not_create_order(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = None
            with pytest.raises(CheckoutError):
                await OrderService.checkout(db, cart, user_id)

        # No order should have been written
        orders = await OrderService.list_orders(db, user_id)
        assert len(orders) == 0

    async def test_failed_checkout_leaves_cart_active(self, db):
        user_id = _uuid()
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = None
            with pytest.raises(CheckoutError):
                await OrderService.checkout(db, cart, user_id)

        # Cart must remain active so user can fix and retry
        active = await CartService.get_active_cart(db, user_id)
        assert active is not None


# ── get_order / list_orders ───────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetAndListOrders:

    async def _place_order(self, db, user_id):
        cart = await _seed_cart(db, user_id, [{
            "product_id": _str_uuid(), "variant_id": _str_uuid(),
            "product_name": "Margherita", "size": "large",
            "unit_price": "14.99", "quantity": 1,
        }])
        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant()
            return await OrderService.checkout(db, cart, user_id)

    async def test_get_order_returns_own_order(self, db):
        user_id = _uuid()
        order = await self._place_order(db, user_id)
        result = await OrderService.get_order(db, order.id, user_id)
        assert result is not None
        assert result.id == order.id

    async def test_get_order_returns_none_for_other_users_order(self, db):
        user_a = _uuid()
        user_b = _uuid()
        order = await self._place_order(db, user_a)

        # user_b tries to access user_a's order
        result = await OrderService.get_order(db, order.id, user_b)
        assert result is None

    async def test_get_order_returns_none_for_nonexistent_order(self, db):
        user_id = _uuid()
        result = await OrderService.get_order(db, _uuid(), user_id)
        assert result is None

    async def test_list_orders_returns_only_own_orders(self, db):
        user_a = _uuid()
        user_b = _uuid()
        await self._place_order(db, user_a)
        await self._place_order(db, user_b)

        orders_a = await OrderService.list_orders(db, user_a)
        assert len(orders_a) == 1
        assert all(o.user_id == user_a for o in orders_a)

    async def test_list_orders_returns_empty_for_new_user(self, db):
        orders = await OrderService.list_orders(db, _uuid())
        assert orders == []
