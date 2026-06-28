"""
Tests for /categories routes.
"""
import pytest
from conftest import make_staff_token, make_user_token, create_category

CATEGORIES_URL = "/categories"


@pytest.mark.asyncio
class TestListCategories:

    async def test_empty_list(self, client):
        resp = await client.get(CATEGORIES_URL)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_active_categories(self, client):
        await create_category(client, name="Pizzas")
        resp = await client.get(CATEGORIES_URL)
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert "Pizzas" in names

    async def test_inactive_categories_excluded(self, client):
        token = make_staff_token()
        # Create inactive category
        await client.post(
            CATEGORIES_URL,
            json={"name": "Archived", "display_order": 99, "is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.get(CATEGORIES_URL)
        names = [c["name"] for c in resp.json()]
        assert "Archived" not in names

    async def test_ordered_by_display_order(self, client):
        await create_category(client, name="Drinks", display_order=2)
        await create_category(client, name="Pizzas", display_order=1)
        resp = await client.get(CATEGORIES_URL)
        names = [c["name"] for c in resp.json()]
        assert names.index("Pizzas") < names.index("Drinks")


@pytest.mark.asyncio
class TestGetCategory:

    async def test_get_existing_category_200(self, client):
        cat = await create_category(client)
        resp = await client.get(f"{CATEGORIES_URL}/{cat['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == cat["name"]

    async def test_get_nonexistent_category_404(self, client):
        import uuid
        resp = await client.get(f"{CATEGORIES_URL}/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestCreateCategory:

    async def test_staff_can_create_201(self, client):
        token = make_staff_token()
        resp = await client.post(
            CATEGORIES_URL,
            json={"name": "Burgers", "display_order": 3, "is_active": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Burgers"
        assert "id" in data

    async def test_non_staff_forbidden_403(self, client):
        token = make_user_token()
        resp = await client.post(
            CATEGORIES_URL,
            json={"name": "Burgers", "display_order": 3, "is_active": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_401(self, client):
        resp = await client.post(
            CATEGORIES_URL,
            json={"name": "Burgers", "display_order": 3, "is_active": True},
        )
        assert resp.status_code == 401

    async def test_missing_name_422(self, client):
        token = make_staff_token()
        resp = await client.post(
            CATEGORIES_URL,
            json={"display_order": 1, "is_active": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestUpdateCategory:

    async def test_staff_can_patch(self, client):
        cat = await create_category(client, name="Old Name")
        token = make_staff_token()
        resp = await client.patch(
            f"{CATEGORIES_URL}/{cat['id']}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_patch_partial_leaves_other_fields(self, client):
        cat = await create_category(client, name="Pizzas", display_order=5)
        token = make_staff_token()
        await client.patch(
            f"{CATEGORIES_URL}/{cat['id']}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.get(f"{CATEGORIES_URL}/{cat['id']}")
        data = resp.json()
        assert data["display_order"] == 5   # unchanged
        assert data["is_active"] is False

    async def test_patch_nonexistent_404(self, client):
        import uuid
        token = make_staff_token()
        resp = await client.patch(
            f"{CATEGORIES_URL}/{uuid.uuid4()}",
            json={"name": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_non_staff_patch_403(self, client):
        cat = await create_category(client)
        token = make_user_token()
        resp = await client.patch(
            f"{CATEGORIES_URL}/{cat['id']}",
            json={"name": "Hacked"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestDeleteCategory:

    async def test_staff_can_delete_204(self, client):
        cat = await create_category(client)
        token = make_staff_token()
        resp = await client.delete(
            f"{CATEGORIES_URL}/{cat['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

    async def test_delete_removes_category(self, client):
        cat = await create_category(client)
        token = make_staff_token()
        await client.delete(
            f"{CATEGORIES_URL}/{cat['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.get(f"{CATEGORIES_URL}/{cat['id']}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_404(self, client):
        import uuid
        token = make_staff_token()
        resp = await client.delete(
            f"{CATEGORIES_URL}/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_non_staff_delete_403(self, client):
        cat = await create_category(client)
        token = make_user_token()
        resp = await client.delete(
            f"{CATEGORIES_URL}/{cat['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
