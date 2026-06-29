# """
# Route-level tests for order-service HTTP endpoints.

# Tests the full HTTP layer — auth enforcement, request/response shapes,
# status codes — with product_client and events mocked so no real
# product-service or RabbitMQ is needed.
# """
# import uuid
# import pytest
# from decimal import Decimal
# from datetime import datetime, timedelta
# from unittest.mock import patch, AsyncMock

# from app.services.cart_service import CartService

# CART_URL = "/cart"
# CART_ITEMS_URL = "/cart/items"
# CHECKOUT_URL = "/checkout"
# ORDERS_URL = "/orders"


# # ── Local helpers (defined here so no cross-file import needed) ───────────

# def new_uuid() -> uuid.UUID:
#     return uuid.uuid4()


# def make_token(user_id: str, username: str = "testuser", is_staff: bool = False) -> str:
#     import os
#     import jwt as pyjwt
#     secret = os.environ.get("JWT_SECRET", "test-secret-key-for-testing-only")
#     payload = {
#         "sub": username,
#         "user_id": str(user_id),
#         "is_staff": is_staff,
#         "type": "access",
#         "fresh": False,
#         "iat": datetime.utcnow(),
#         "nbf": datetime.utcnow(),
#         "exp": datetime.utcnow() + timedelta(minutes=30),
#         "jti": str(uuid.uuid4()),
#     }
#     token = pyjwt.encode(payload, secret, algorithm="HS256")
#     # PyJWT < 2.0 returns bytes; ensure we always return a string
#     if isinstance(token, bytes):
#         token = token.decode("utf-8")
#     return token


# def _live_variant(price: str = "14.99", is_available: bool = True) -> dict:
#     return {
#         "product_name": "Margherita",
#         "size": "large",
#         "unit_price": price,
#         "is_available": is_available,
#     }


# # ── GET /cart ─────────────────────────────────────────────────────────────

# @pytest.mark.asyncio
# class TestGetCart:

#     async def test_get_cart_creates_new_cart(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         resp = await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})
#         assert resp.status_code == 200
#         data = resp.json()
#         assert data["status"] == "active"
#         assert data["items"] == []

#     async def test_get_cart_returns_existing_cart(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")

#         # First call creates it
#         resp1 = await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})
#         cart_id_1 = resp1.json()["id"]

#         # Second call returns same cart
#         resp2 = await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})
#         cart_id_2 = resp2.json()["id"]

#         assert cart_id_1 == cart_id_2

#     async def test_get_cart_unauthenticated_401(self, client, db):
#         resp = await client.get(CART_URL)
#         assert resp.status_code == 401


# # ── POST /cart/items ──────────────────────────────────────────────────────

# @pytest.mark.asyncio
# class TestAddToCart:

#     def _item_payload(self, product_id=None, variant_id=None):
#         return {
#             "product_id": product_id or str(new_uuid()),
#             "variant_id": variant_id or str(new_uuid()),
#             "product_name": "Margherita",
#             "size": "large",
#             "unit_price": 14.99,
#             "quantity": 2,
#         }

#     async def test_add_item_returns_201(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         resp = await client.post(
#             CART_ITEMS_URL,
#             json=self._item_payload(),
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 201

#     async def test_add_item_unauthenticated_401(self, client, db):
#         resp = await client.post(CART_ITEMS_URL, json=self._item_payload())
#         assert resp.status_code == 401

#     async def test_add_item_missing_required_field_422(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         # Missing product_name
#         payload = {
#             "product_id": str(new_uuid()),
#             "variant_id": str(new_uuid()),
#             "unit_price": 14.99,
#             "quantity": 1,
#         }
#         resp = await client.post(
#             CART_ITEMS_URL,
#             json=payload,
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 422

#     async def test_add_item_negative_price_422(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         payload = self._item_payload()
#         payload["unit_price"] = -5.00
#         resp = await client.post(
#             CART_ITEMS_URL,
#             json=payload,
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 422

#     async def test_add_item_zero_quantity_422(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         payload = self._item_payload()
#         payload["quantity"] = 0
#         resp = await client.post(
#             CART_ITEMS_URL,
#             json=payload,
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 422


# # ── DELETE /cart/items/{item_id} ──────────────────────────────────────────

# @pytest.mark.asyncio
# class TestRemoveFromCart:

#     async def _add_item(self, client, token, product_id=None, variant_id=None):
#         payload = {
#             "product_id": product_id or str(new_uuid()),
#             "variant_id": variant_id or str(new_uuid()),
#             "product_name": "Margherita",
#             "size": "large",
#             "unit_price": 14.99,
#             "quantity": 1,
#         }
#         resp = await client.post(
#             CART_ITEMS_URL,
#             json=payload,
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         return resp.json()

#     async def test_remove_item_returns_204(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")

#         await self._add_item(client, token)

#         # Re-fetch cart via GET to get populated items list
#         cart_data = (await client.get(
#             CART_URL,
#             headers={"Authorization": f"Bearer {token}"},
#         )).json()
#         item_id = cart_data["items"][0]["id"]

#         resp = await client.delete(
#             f"{CART_ITEMS_URL}/{item_id}",
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 204

#     async def test_remove_nonexistent_item_404(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         # Create cart first
#         await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})

#         resp = await client.delete(
#             f"{CART_ITEMS_URL}/{new_uuid()}",
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 404

#     async def test_remove_item_unauthenticated_401(self, client, db):
#         resp = await client.delete(f"{CART_ITEMS_URL}/{new_uuid()}")
#         assert resp.status_code == 401

#     async def test_remove_item_invalid_uuid_422(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         resp = await client.delete(
#             f"{CART_ITEMS_URL}/not-a-valid-uuid",
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 422


# # ── POST /checkout ─────────────────────────────────────────────────────────

# @pytest.mark.asyncio
# class TestCheckout:

#     async def _setup_cart_with_item(self, client, token):
#         await client.post(
#             CART_ITEMS_URL,
#             json={
#                 "product_id": str(new_uuid()),
#                 "variant_id": str(new_uuid()),
#                 "product_name": "Margherita",
#                 "size": "large",
#                 "unit_price": 14.99,
#                 "quantity": 2,
#             },
#             headers={"Authorization": f"Bearer {token}"},
#         )

#     async def test_checkout_returns_201_confirmed_order(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         await self._setup_cart_with_item(client, token)

#         with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
#              patch("app.services.order_service.publish_order_placed"):
#             mock_gv.return_value = _live_variant()
#             resp = await client.post(
#                 CHECKOUT_URL,
#                 headers={"Authorization": f"Bearer {token}"},
#             )

#         assert resp.status_code == 201
#         data = resp.json()
#         assert data["status"] == "confirmed"
#         assert len(data["items"]) == 1
#         assert data["total_amount"] == "29.98"

#     async def test_checkout_unauthenticated_401(self, client, db):
#         resp = await client.post(CHECKOUT_URL)
#         assert resp.status_code == 401

#     async def test_checkout_empty_cart_400(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         # Create cart but don't add items
#         await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})

#         resp = await client.post(
#             CHECKOUT_URL,
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 400

#     async def test_checkout_unavailable_product_400(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         await self._setup_cart_with_item(client, token)

#         with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
#              patch("app.services.order_service.publish_order_placed"):
#             mock_gv.return_value = None  # product no longer exists
#             resp = await client.post(
#                 CHECKOUT_URL,
#                 headers={"Authorization": f"Bearer {token}"},
#             )

#         assert resp.status_code == 400

#     async def test_checkout_product_service_down_503(self, client, db):
#         from app.utils.product_client import ProductServiceError
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         await self._setup_cart_with_item(client, token)

#         with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
#              patch("app.services.order_service.publish_order_placed"):
#             mock_gv.side_effect = ProductServiceError("Connection refused")
#             resp = await client.post(
#                 CHECKOUT_URL,
#                 headers={"Authorization": f"Bearer {token}"},
#             )

#         assert resp.status_code == 400

#     async def test_checkout_includes_price_changes_in_response(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         await self._setup_cart_with_item(client, token)

#         with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
#              patch("app.services.order_service.publish_order_placed"):
#             mock_gv.return_value = _live_variant(price="19.99")  # price changed
#             resp = await client.post(
#                 CHECKOUT_URL,
#                 headers={"Authorization": f"Bearer {token}"},
#             )

#         assert resp.status_code == 201
#         data = resp.json()
#         assert len(data["price_changes"]) == 1


# # ── GET /orders ───────────────────────────────────────────────────────────

# @pytest.mark.asyncio
# class TestListOrders:

#     async def _place_order(self, client, token):
#         await client.post(
#             CART_ITEMS_URL,
#             json={
#                 "product_id": str(new_uuid()),
#                 "variant_id": str(new_uuid()),
#                 "product_name": "Margherita",
#                 "size": "large",
#                 "unit_price": 14.99,
#                 "quantity": 1,
#             },
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
#              patch("app.services.order_service.publish_order_placed"):
#             mock_gv.return_value = _live_variant()
#             return await client.post(
#                 CHECKOUT_URL,
#                 headers={"Authorization": f"Bearer {token}"},
#             )

#     async def test_list_orders_returns_200(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         await self._place_order(client, token)

#         resp = await client.get(ORDERS_URL, headers={"Authorization": f"Bearer {token}"})
#         assert resp.status_code == 200
#         assert len(resp.json()) == 1

#     async def test_list_orders_empty_for_new_user(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         resp = await client.get(ORDERS_URL, headers={"Authorization": f"Bearer {token}"})
#         assert resp.status_code == 200
#         assert resp.json() == []

#     async def test_list_orders_unauthenticated_401(self, client, db):
#         resp = await client.get(ORDERS_URL)
#         assert resp.status_code == 401

#     async def test_list_orders_isolated_between_users(self, client, db):
#         user_a_id = str(new_uuid())
#         user_b_id = str(new_uuid())
#         token_a = make_token(user_id=user_a_id, username="user_a")
#         token_b = make_token(user_id=user_b_id, username="user_b")

#         await self._place_order(client, token_a)

#         resp = await client.get(ORDERS_URL, headers={"Authorization": f"Bearer {token_b}"})
#         assert resp.json() == []


# # ── GET /orders/{order_id} ─────────────────────────────────────────────────

# @pytest.mark.asyncio
# class TestGetOrder:

#     async def _place_order(self, client, token):
#         await client.post(
#             CART_ITEMS_URL,
#             json={
#                 "product_id": str(new_uuid()),
#                 "variant_id": str(new_uuid()),
#                 "product_name": "Margherita",
#                 "size": "large",
#                 "unit_price": 14.99,
#                 "quantity": 1,
#             },
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
#              patch("app.services.order_service.publish_order_placed"):
#             mock_gv.return_value = _live_variant()
#             resp = await client.post(
#                 CHECKOUT_URL,
#                 headers={"Authorization": f"Bearer {token}"},
#             )
#         return resp.json()

#     async def test_get_own_order_200(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         order = await self._place_order(client, token)

#         resp = await client.get(
#             f"{ORDERS_URL}/{order['id']}",
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 200
#         assert resp.json()["id"] == order["id"]

#     async def test_get_other_users_order_404(self, client, db):
#         user_a_id = str(new_uuid())
#         user_b_id = str(new_uuid())
#         token_a = make_token(user_id=user_a_id, username="user_a")
#         token_b = make_token(user_id=user_b_id, username="user_b")

#         order = await self._place_order(client, token_a)

#         resp = await client.get(
#             f"{ORDERS_URL}/{order['id']}",
#             headers={"Authorization": f"Bearer {token_b}"},
#         )
#         assert resp.status_code == 404

#     async def test_get_nonexistent_order_404(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         resp = await client.get(
#             f"{ORDERS_URL}/{new_uuid()}",
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 404

#     async def test_get_order_unauthenticated_401(self, client, db):
#         resp = await client.get(f"{ORDERS_URL}/{new_uuid()}")
#         assert resp.status_code == 401

#     async def test_get_order_invalid_uuid_422(self, client, db):
#         user_id = str(new_uuid())
#         token = make_token(user_id=user_id, username="testuser")
#         resp = await client.get(
#             f"{ORDERS_URL}/not-a-valid-uuid",
#             headers={"Authorization": f"Bearer {token}"},
#         )
#         assert resp.status_code == 422


# # ── GET /health ───────────────────────────────────────────────────────────

# @pytest.mark.asyncio
# async def test_health_check(client):
#     resp = await client.get("/health")
#     assert resp.status_code == 200
#     assert resp.json() == {"status": "ok"}

"""
Route-level tests for order-service HTTP endpoints.

Tests the full HTTP layer — auth enforcement, request/response shapes,
status codes — with product_client and events mocked so no real
product-service or RabbitMQ is needed.
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from app.services.cart_service import CartService

CART_URL = "/cart"
CART_ITEMS_URL = "/cart/items"
CHECKOUT_URL = "/checkout"
ORDERS_URL = "/orders"


# ── Local helpers (defined here so no cross-file import needed) ───────────

def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def make_token(user_id: str, username: str = "testuser", is_staff: bool = False) -> str:
    import os
    import jwt as pyjwt
    secret = os.environ.get("JWT_SECRET", "test-secret-key-for-testing-only")
    payload = {
        "sub": username,
        "user_id": str(user_id),
        "is_staff": is_staff,
        "type": "access",
        "fresh": False,
        "iat": datetime.utcnow(),
        "nbf": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "jti": str(uuid.uuid4()),
    }
    token = pyjwt.encode(payload, secret, algorithm="HS256")
    # PyJWT < 2.0 returns bytes; ensure we always return a string
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def _live_variant(price: str = "14.99", is_available: bool = True) -> dict:
    return {
        "product_name": "Margherita",
        "size": "large",
        "unit_price": price,
        "is_available": is_available,
    }


# ── GET /cart ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetCart:

    async def test_get_cart_creates_new_cart(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        resp = await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["items"] == []

    async def test_get_cart_returns_existing_cart(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")

        # First call creates it
        resp1 = await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})
        cart_id_1 = resp1.json()["id"]

        # Second call returns same cart
        resp2 = await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})
        cart_id_2 = resp2.json()["id"]

        assert cart_id_1 == cart_id_2

    async def test_get_cart_unauthenticated_401(self, client, db):
        resp = await client.get(CART_URL)
        assert resp.status_code == 401


# ── POST /cart/items ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAddToCart:

    def _item_payload(self, product_id=None, variant_id=None):
        return {
            "product_id": product_id or str(new_uuid()),
            "variant_id": variant_id or str(new_uuid()),
            "product_name": "Margherita",
            "size": "large",
            "unit_price": 14.99,
            "quantity": 2,
        }

    async def test_add_item_returns_201(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        resp = await client.post(
            CART_ITEMS_URL,
            json=self._item_payload(),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    async def test_add_item_unauthenticated_401(self, client, db):
        resp = await client.post(CART_ITEMS_URL, json=self._item_payload())
        assert resp.status_code == 401

    async def test_add_item_missing_required_field_422(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        # Missing product_name
        payload = {
            "product_id": str(new_uuid()),
            "variant_id": str(new_uuid()),
            "unit_price": 14.99,
            "quantity": 1,
        }
        resp = await client.post(
            CART_ITEMS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_add_item_negative_price_422(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        payload = self._item_payload()
        payload["unit_price"] = -5.00
        resp = await client.post(
            CART_ITEMS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    async def test_add_item_zero_quantity_422(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        payload = self._item_payload()
        payload["quantity"] = 0
        resp = await client.post(
            CART_ITEMS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


# ── DELETE /cart/items/{item_id} ──────────────────────────────────────────

@pytest.mark.asyncio
class TestRemoveFromCart:

    async def _add_item(self, client, token, product_id=None, variant_id=None):
        payload = {
            "product_id": product_id or str(new_uuid()),
            "variant_id": variant_id or str(new_uuid()),
            "product_name": "Margherita",
            "size": "large",
            "unit_price": 14.99,
            "quantity": 1,
        }
        resp = await client.post(
            CART_ITEMS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.json()

    async def test_remove_item_returns_204(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")

        await self._add_item(client, token)

        # Re-fetch cart via GET to get the populated items list
        cart_data = (await client.get(
            CART_URL,
            headers={"Authorization": f"Bearer {token}"},
        )).json()
        item_id = cart_data["items"][0]["id"]

        resp = await client.delete(
            f"{CART_ITEMS_URL}/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

    async def test_remove_nonexistent_item_404(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        # Create cart first
        await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})

        resp = await client.delete(
            f"{CART_ITEMS_URL}/{new_uuid()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_remove_item_unauthenticated_401(self, client, db):
        resp = await client.delete(f"{CART_ITEMS_URL}/{new_uuid()}")
        assert resp.status_code == 401

    async def test_remove_item_invalid_uuid_422(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        resp = await client.delete(
            f"{CART_ITEMS_URL}/not-a-valid-uuid",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


# ── POST /checkout ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestCheckout:

    async def _setup_cart_with_item(self, client, token):
        await client.post(
            CART_ITEMS_URL,
            json={
                "product_id": str(new_uuid()),
                "variant_id": str(new_uuid()),
                "product_name": "Margherita",
                "size": "large",
                "unit_price": 14.99,
                "quantity": 2,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    async def test_checkout_returns_201_confirmed_order(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        await self._setup_cart_with_item(client, token)

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"), \
             patch("app.services.order_service.initialize_payment", new_callable=AsyncMock) as mock_pay:
            mock_gv.return_value = _live_variant()
            mock_pay.return_value = {
                "authorization_url": "https://checkout.paystack.com/test",
                "reference": "PIZZA-TEST123",
            }
            resp = await client.post(
                CHECKOUT_URL,
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending_payment"
        assert len(data["items"]) == 1
        assert data["total_amount"] == "29.98"

    async def test_checkout_unauthenticated_401(self, client, db):
        resp = await client.post(CHECKOUT_URL)
        assert resp.status_code == 401

    async def test_checkout_empty_cart_400(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        # Create cart but don't add items
        await client.get(CART_URL, headers={"Authorization": f"Bearer {token}"})

        resp = await client.post(
            CHECKOUT_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    async def test_checkout_unavailable_product_400(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        await self._setup_cart_with_item(client, token)

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = None  # product no longer exists
            resp = await client.post(
                CHECKOUT_URL,
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 400

    async def test_checkout_product_service_down_503(self, client, db):
        from app.utils.product_client import ProductServiceError
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        await self._setup_cart_with_item(client, token)

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.side_effect = ProductServiceError("Connection refused")
            resp = await client.post(
                CHECKOUT_URL,
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 400

    async def test_checkout_includes_price_changes_in_response(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        await self._setup_cart_with_item(client, token)

        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant(price="19.99")  # price changed
            resp = await client.post(
                CHECKOUT_URL,
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert len(data["price_changes"]) == 1


# ── GET /orders ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestListOrders:

    async def _place_order(self, client, token):
        await client.post(
            CART_ITEMS_URL,
            json={
                "product_id": str(new_uuid()),
                "variant_id": str(new_uuid()),
                "product_name": "Margherita",
                "size": "large",
                "unit_price": 14.99,
                "quantity": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant()
            return await client.post(
                CHECKOUT_URL,
                headers={"Authorization": f"Bearer {token}"},
            )

    async def test_list_orders_returns_200(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        await self._place_order(client, token)

        resp = await client.get(ORDERS_URL, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_list_orders_empty_for_new_user(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        resp = await client.get(ORDERS_URL, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_orders_unauthenticated_401(self, client, db):
        resp = await client.get(ORDERS_URL)
        assert resp.status_code == 401

    async def test_list_orders_isolated_between_users(self, client, db):
        user_a_id = str(new_uuid())
        user_b_id = str(new_uuid())
        token_a = make_token(user_id=user_a_id, username="user_a")
        token_b = make_token(user_id=user_b_id, username="user_b")

        await self._place_order(client, token_a)

        resp = await client.get(ORDERS_URL, headers={"Authorization": f"Bearer {token_b}"})
        assert resp.json() == []


# ── GET /orders/{order_id} ─────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetOrder:

    async def _place_order(self, client, token):
        await client.post(
            CART_ITEMS_URL,
            json={
                "product_id": str(new_uuid()),
                "variant_id": str(new_uuid()),
                "product_name": "Margherita",
                "size": "large",
                "unit_price": 14.99,
                "quantity": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        with patch("app.services.order_service.get_variant", new_callable=AsyncMock) as mock_gv, \
             patch("app.services.order_service.publish_order_placed"):
            mock_gv.return_value = _live_variant()
            resp = await client.post(
                CHECKOUT_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
        return resp.json()

    async def test_get_own_order_200(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        order = await self._place_order(client, token)

        resp = await client.get(
            f"{ORDERS_URL}/{order['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == order["id"]

    async def test_get_other_users_order_404(self, client, db):
        user_a_id = str(new_uuid())
        user_b_id = str(new_uuid())
        token_a = make_token(user_id=user_a_id, username="user_a")
        token_b = make_token(user_id=user_b_id, username="user_b")

        order = await self._place_order(client, token_a)

        resp = await client.get(
            f"{ORDERS_URL}/{order['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404

    async def test_get_nonexistent_order_404(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        resp = await client.get(
            f"{ORDERS_URL}/{new_uuid()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_get_order_unauthenticated_401(self, client, db):
        resp = await client.get(f"{ORDERS_URL}/{new_uuid()}")
        assert resp.status_code == 401

    async def test_get_order_invalid_uuid_422(self, client, db):
        user_id = str(new_uuid())
        token = make_token(user_id=user_id, username="testuser")
        resp = await client.get(
            f"{ORDERS_URL}/not-a-valid-uuid",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422


# ── GET /health ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}