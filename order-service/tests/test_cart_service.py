"""
Unit tests for CartService.

Tests run against an in-memory SQLite database — no real PostgreSQL or
RabbitMQ needed. Each test gets a fresh database via the db fixture.
"""
import uuid
import pytest
import pytest_asyncio
from decimal import Decimal

from app.models.cart import Cart, CartItem, CartStatus
from app.services.cart_service import CartService


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _str_uuid() -> str:
    return str(uuid.uuid4())


# ── get_active_cart ───────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetActiveCart:

    async def test_returns_none_when_no_cart_exists(self, db):
        result = await CartService.get_active_cart(db, _uuid())
        assert result is None

    async def test_returns_active_cart_for_user(self, db):
        user_id = _uuid()
        cart = Cart(user_id=user_id, status=CartStatus.active)
        db.add(cart)
        await db.commit()

        result = await CartService.get_active_cart(db, user_id)
        assert result is not None
        assert result.user_id == user_id

    async def test_does_not_return_checked_out_cart(self, db):
        user_id = _uuid()
        cart = Cart(user_id=user_id, status=CartStatus.checked_out)
        db.add(cart)
        await db.commit()

        result = await CartService.get_active_cart(db, user_id)
        assert result is None

    async def test_returns_only_the_requesting_users_cart(self, db):
        user_a = _uuid()
        user_b = _uuid()
        cart_a = Cart(user_id=user_a, status=CartStatus.active)
        db.add(cart_a)
        await db.commit()

        result = await CartService.get_active_cart(db, user_b)
        assert result is None


# ── get_or_create_cart ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetOrCreateCart:

    async def test_creates_cart_when_none_exists(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)

        assert cart is not None
        assert cart.user_id == user_id
        assert cart.status == CartStatus.active

    async def test_returns_existing_cart_when_one_exists(self, db):
        user_id = _uuid()
        first = await CartService.get_or_create_cart(db, user_id)
        second = await CartService.get_or_create_cart(db, user_id)

        assert first.id == second.id

    async def test_new_cart_has_empty_items(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)
        assert cart.items == []


# ── add_item ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAddItem:

    async def test_adds_item_to_cart(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)
        product_id = _str_uuid()
        variant_id = _str_uuid()

        item = await CartService.add_item(
            db, cart,
            product_id=product_id,
            variant_id=variant_id,
            product_name="Margherita",
            size="large",
            unit_price=Decimal("14.99"),
            quantity=1,
        )

        assert item.product_name == "Margherita"
        assert item.size == "large"
        assert item.unit_price == Decimal("14.99")
        assert item.quantity == 1

    async def test_duplicate_variant_merges_quantity(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)
        product_id = _str_uuid()
        variant_id = _str_uuid()

        await CartService.add_item(
            db, cart,
            product_id=product_id, variant_id=variant_id,
            product_name="Margherita", size="large",
            unit_price=Decimal("14.99"), quantity=1,
        )
        item = await CartService.add_item(
            db, cart,
            product_id=product_id, variant_id=variant_id,
            product_name="Margherita", size="large",
            unit_price=Decimal("14.99"), quantity=2,
        )

        # Should be merged into one row with quantity=3, not two separate rows
        assert item.quantity == 3

    async def test_different_variants_create_separate_rows(self, db):
        from sqlalchemy.future import select
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)
        product_id = _str_uuid()

        await CartService.add_item(
            db, cart,
            product_id=product_id, variant_id=_str_uuid(),
            product_name="Margherita", size="small",
            unit_price=Decimal("8.99"), quantity=1,
        )
        await CartService.add_item(
            db, cart,
            product_id=product_id, variant_id=_str_uuid(),
            product_name="Margherita", size="large",
            unit_price=Decimal("14.99"), quantity=1,
        )

        # Query items directly rather than via relationship reload
        # to avoid SQLite UUID comparison issues in get_active_cart
        result = await db.execute(
            select(CartItem).where(CartItem.cart_id == cart.id)
        )
        items = result.scalars().all()
        assert len(items) == 2


# ── remove_item ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRemoveItem:

    async def test_removes_existing_item_returns_true(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)
        item = await CartService.add_item(
            db, cart,
            product_id=_str_uuid(), variant_id=_str_uuid(),
            product_name="Margherita", size="large",
            unit_price=Decimal("14.99"), quantity=1,
        )

        result = await CartService.remove_item(db, cart, item.id)
        assert result is True

    async def test_removed_item_no_longer_in_cart(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)
        item = await CartService.add_item(
            db, cart,
            product_id=_str_uuid(), variant_id=_str_uuid(),
            product_name="Margherita", size="large",
            unit_price=Decimal("14.99"), quantity=1,
        )

        await CartService.remove_item(db, cart, item.id)
        fresh_cart = await CartService.get_active_cart(db, user_id)
        assert len(fresh_cart.items) == 0

    async def test_removing_nonexistent_item_returns_false(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)

        result = await CartService.remove_item(db, cart, _uuid())
        assert result is False

    async def test_cannot_remove_item_belonging_to_another_cart(self, db):
        user_a = _uuid()
        user_b = _uuid()
        cart_a = await CartService.get_or_create_cart(db, user_a)
        cart_b = await CartService.get_or_create_cart(db, user_b)

        item = await CartService.add_item(
            db, cart_a,
            product_id=_str_uuid(), variant_id=_str_uuid(),
            product_name="Margherita", size="large",
            unit_price=Decimal("14.99"), quantity=1,
        )

        # cart_b tries to remove cart_a's item — must return False
        result = await CartService.remove_item(db, cart_b, item.id)
        assert result is False


# ── mark_checked_out ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMarkCheckedOut:

    async def test_marks_cart_as_checked_out(self, db):
        user_id = _uuid()
        cart = await CartService.get_or_create_cart(db, user_id)

        await CartService.mark_checked_out(db, cart)

        fresh_cart = await CartService.get_active_cart(db, user_id)
        # Active cart no longer exists after checkout
        assert fresh_cart is None