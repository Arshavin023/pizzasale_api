"""
Direct service-layer tests for CategoryService and ProductService.
"""
import uuid
import pytest
import pytest_asyncio
from decimal import Decimal

from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant, SizeEnum
from app.services.category_service import CategoryService
from app.services.product_service import ProductService


def _uid():
    return uuid.uuid4()


@pytest.mark.asyncio
class TestCategoryService:

    async def test_create_and_retrieve(self, db):
        cat = await CategoryService.create_category(
            db, {"name": "Pizzas", "display_order": 1, "is_active": True}
        )
        assert cat.id is not None
        fetched = await CategoryService.get_category(db, str(cat.id))
        assert fetched.name == "Pizzas"

    async def test_list_returns_only_active(self, db):
        await CategoryService.create_category(
            db, {"name": "Active", "display_order": 1, "is_active": True}
        )
        await CategoryService.create_category(
            db, {"name": "Inactive", "display_order": 2, "is_active": False}
        )
        cats = await CategoryService.list_categories(db, active_only=True)
        names = [c.name for c in cats]
        assert "Active" in names
        assert "Inactive" not in names

    async def test_list_without_filter_includes_inactive(self, db):
        await CategoryService.create_category(
            db, {"name": "Active", "display_order": 1, "is_active": True}
        )
        await CategoryService.create_category(
            db, {"name": "Inactive", "display_order": 2, "is_active": False}
        )
        cats = await CategoryService.list_categories(db, active_only=False)
        names = [c.name for c in cats]
        assert "Active" in names
        assert "Inactive" in names

    async def test_list_ordered_by_display_order(self, db):
        await CategoryService.create_category(
            db, {"name": "B", "display_order": 2, "is_active": True}
        )
        await CategoryService.create_category(
            db, {"name": "A", "display_order": 1, "is_active": True}
        )
        cats = await CategoryService.list_categories(db)
        assert cats[0].name == "A"

    async def test_update_category(self, db):
        cat = await CategoryService.create_category(
            db, {"name": "Old", "display_order": 1, "is_active": True}
        )
        updated = await CategoryService.update_category(db, cat, {"name": "New"})
        assert updated.name == "New"

    async def test_delete_category(self, db):
        cat = await CategoryService.create_category(
            db, {"name": "ToDelete", "display_order": 1, "is_active": True}
        )
        await CategoryService.delete_category(db, cat)
        fetched = await CategoryService.get_category(db, str(cat.id))
        assert fetched is None

    async def test_get_nonexistent_returns_none(self, db):
        result = await CategoryService.get_category(db, str(_uid()))
        assert result is None


@pytest.mark.asyncio
class TestProductService:

    @pytest_asyncio.fixture(autouse=True)
    async def seed_category(self, db):
        self.category = await CategoryService.create_category(
            db, {"name": "Pizzas", "display_order": 1, "is_active": True}
        )

    def _product_data(self, name="Margherita"):
        return {
            "category_id": self.category.id,
            "name": name,
            "description": "Classic",
            "is_available": True,
            "variants": [
                {"size": SizeEnum.small, "price": Decimal("8.99"), "is_available": True},
                {"size": SizeEnum.large, "price": Decimal("14.99"), "is_available": True},
            ],
        }

    async def test_create_product_with_variants(self, db):
        product = await ProductService.create_product(db, self._product_data())
        assert product.id is not None
        assert len(product.variants) == 2

    async def test_list_returns_available_only(self, db):
        await ProductService.create_product(db, self._product_data("Available"))
        unavailable = {**self._product_data("Unavailable"), "is_available": False}
        await ProductService.create_product(db, unavailable)

        products = await ProductService.list_products(db, available_only=True)
        names = [p.name for p in products]
        assert "Available" in names
        assert "Unavailable" not in names

    async def test_list_filter_by_category(self, db):
        cat2 = await CategoryService.create_category(
            db, {"name": "Drinks", "display_order": 2, "is_active": True}
        )
        await ProductService.create_product(db, self._product_data("Pizza"))
        drink_data = {**self._product_data("Cola"), "category_id": cat2.id}
        await ProductService.create_product(db, drink_data)

        products = await ProductService.list_products(
            db, category_id=str(self.category.id)
        )
        names = [p.name for p in products]
        assert "Pizza" in names
        assert "Cola" not in names

    async def test_get_product_includes_variants(self, db):
        created = await ProductService.create_product(db, self._product_data())
        fetched = await ProductService.get_product(db, str(created.id))
        assert len(fetched.variants) == 2

    async def test_get_nonexistent_returns_none(self, db):
        result = await ProductService.get_product(db, str(_uid()))
        assert result is None

    async def test_update_product(self, db):
        product = await ProductService.create_product(db, self._product_data())
        updated = await ProductService.update_product(
            db, product, {"name": "BBQ Chicken", "is_available": False}
        )
        assert updated.name == "BBQ Chicken"
        assert updated.is_available is False

    async def test_delete_product(self, db):
        product = await ProductService.create_product(db, self._product_data())
        await ProductService.delete_product(db, product)
        result = await ProductService.get_product(db, str(product.id))
        assert result is None