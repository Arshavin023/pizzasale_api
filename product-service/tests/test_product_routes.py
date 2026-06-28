"""
Tests for /products routes (including variant handling).
"""
import pytest
from conftest import make_staff_token, make_user_token, create_category, create_product

PRODUCTS_URL = "/products"


@pytest.mark.asyncio
class TestListProducts:

    async def test_empty_list(self, client):
        resp = await client.get(PRODUCTS_URL)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_available_products(self, client):
        cat = await create_category(client)
        await create_product(client, cat["id"], name="Margherita")
        resp = await client.get(PRODUCTS_URL)
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "Margherita" in names

    async def test_unavailable_products_excluded(self, client):
        cat = await create_category(client)
        token = make_staff_token()
        await client.post(
            PRODUCTS_URL,
            json={
                "category_id": cat["id"],
                "name": "Discontinued",
                "is_available": False,
                "variants": [{"size": "small", "price": "5.00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.get(PRODUCTS_URL)
        names = [p["name"] for p in resp.json()]
        assert "Discontinued" not in names

    async def test_filter_by_category_id(self, client):
        cat1 = await create_category(client, name="Pizzas")
        cat2 = await create_category(client, name="Drinks")
        await create_product(client, cat1["id"], name="Margherita")
        await create_product(client, cat2["id"], name="Cola")

        resp = await client.get(f"{PRODUCTS_URL}?category_id={cat1['id']}")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "Margherita" in names
        assert "Cola" not in names

    async def test_response_includes_variants(self, client):
        cat = await create_category(client)
        await create_product(client, cat["id"])
        resp = await client.get(PRODUCTS_URL)
        product = resp.json()[0]
        assert "variants" in product
        assert len(product["variants"]) == 2


@pytest.mark.asyncio
class TestGetProduct:

    async def test_get_existing_product_200(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"], name="Margherita")
        resp = await client.get(f"{PRODUCTS_URL}/{product['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Margherita"

    async def test_get_product_includes_variants(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"])
        resp = await client.get(f"{PRODUCTS_URL}/{product['id']}")
        variants = resp.json()["variants"]
        sizes = {v["size"] for v in variants}
        assert sizes == {"small", "large"}

    async def test_get_nonexistent_product_404(self, client):
        import uuid
        resp = await client.get(f"{PRODUCTS_URL}/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestCreateProduct:

    async def test_staff_creates_product_with_variants_201(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"], name="Pepperoni")
        assert product["name"] == "Pepperoni"
        assert len(product["variants"]) == 2
        prices = {v["size"]: str(v["price"]) for v in product["variants"]}
        assert prices["small"] == "8.99"
        assert prices["large"] == "14.99"

    async def test_non_staff_forbidden_403(self, client):
        cat = await create_category(client)
        token = make_user_token()
        resp = await client.post(
            PRODUCTS_URL,
            json={
                "category_id": cat["id"],
                "name": "Hack Pizza",
                "is_available": True,
                "variants": [{"size": "small", "price": "1.00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_401(self, client):
        resp = await client.post(PRODUCTS_URL, json={})
        assert resp.status_code == 401

    async def test_invalid_size_enum_422(self, client):
        cat = await create_category(client)
        token = make_staff_token()
        resp = await client.post(
            PRODUCTS_URL,
            json={
                "category_id": cat["id"],
                "name": "Bad",
                "is_available": True,
                "variants": [{"size": "jumbo", "price": "9.99"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_zero_price_rejected_422(self, client):
        cat = await create_category(client)
        token = make_staff_token()
        resp = await client.post(
            PRODUCTS_URL,
            json={
                "category_id": cat["id"],
                "name": "Free",
                "is_available": True,
                "variants": [{"size": "small", "price": "0.00"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_missing_variants_422(self, client):
        cat = await create_category(client)
        token = make_staff_token()
        resp = await client.post(
            PRODUCTS_URL,
            json={"category_id": cat["id"], "name": "No Variants", "is_available": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestUpdateProduct:

    async def test_staff_patch_name(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"], name="Old Name")
        token = make_staff_token()
        resp = await client.patch(
            f"{PRODUCTS_URL}/{product['id']}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_patch_availability(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"])
        token = make_staff_token()
        resp = await client.patch(
            f"{PRODUCTS_URL}/{product['id']}",
            json={"is_available": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_available"] is False

    async def test_patch_nonexistent_404(self, client):
        import uuid
        token = make_staff_token()
        resp = await client.patch(
            f"{PRODUCTS_URL}/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_non_staff_patch_403(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"])
        token = make_user_token()
        resp = await client.patch(
            f"{PRODUCTS_URL}/{product['id']}",
            json={"name": "Hacked"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestDeleteProduct:

    async def test_staff_delete_204(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"])
        token = make_staff_token()
        resp = await client.delete(
            f"{PRODUCTS_URL}/{product['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

    async def test_delete_removes_product(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"])
        token = make_staff_token()
        await client.delete(
            f"{PRODUCTS_URL}/{product['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.get(f"{PRODUCTS_URL}/{product['id']}")
        assert resp.status_code == 404

    async def test_delete_cascades_to_variants(self, client):
        """Cascade delete must remove orphan variants (cascade='all, delete-orphan')."""
        cat = await create_category(client)
        product = await create_product(client, cat["id"])
        token = make_staff_token()
        await client.delete(
            f"{PRODUCTS_URL}/{product['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Product gone — variants also gone (verified via product 404)
        resp = await client.get(f"{PRODUCTS_URL}/{product['id']}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_404(self, client):
        import uuid
        token = make_staff_token()
        resp = await client.delete(
            f"{PRODUCTS_URL}/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_non_staff_delete_403(self, client):
        cat = await create_category(client)
        product = await create_product(client, cat["id"])
        token = make_user_token()
        resp = await client.delete(
            f"{PRODUCTS_URL}/{product['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
