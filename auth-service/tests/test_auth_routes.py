"""
End-to-end route tests for auth-service.
All external I/O (SES, RabbitMQ) is mocked at the module level.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.models.user import UserAuth
from app.core.security import hash_password


REGISTER_URL = "/auth/register"
LOGIN_URL = "/auth/login"
REFRESH_URL = "/auth/refresh"
VERIFY_URL = "/auth/verify-email"

VALID_PAYLOAD = {
    "username": "uche",
    "email": "uche@example.com",
    "password": "Secure1!",
}


# ── /auth/register ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRegisterRoute:

    @patch("app.api.auth_routes.send_verification_email")
    @patch("app.services.auth_service.publish_user_registered")
    async def test_register_success_201(self, mock_pub, mock_email, client):
        resp = await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        assert resp.status_code == 200
        assert "verify your account" in resp.json()["message"].lower()

    @patch("app.api.auth_routes.send_verification_email")
    @patch("app.services.auth_service.publish_user_registered")
    async def test_register_duplicate_username_409(self, mock_pub, mock_email, client):
        await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        resp = await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        assert resp.status_code == 409
        assert "Username already exists" in resp.json()["detail"]

    @patch("app.api.auth_routes.send_verification_email")
    @patch("app.services.auth_service.publish_user_registered")
    async def test_register_duplicate_email_409(self, mock_pub, mock_email, client):
        await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        other = {**VALID_PAYLOAD, "username": "other_uche"}
        resp = await client.post(REGISTER_URL, json=other)
        assert resp.status_code == 409
        assert "Email already exists" in resp.json()["detail"]

    @patch("app.api.auth_routes.send_verification_email")
    @patch("app.services.auth_service.publish_user_registered")
    async def test_register_email_failure_returns_201_with_detail(
        self, mock_pub, mock_email, client
    ):
        mock_email.side_effect = RuntimeError("SES sandbox error")
        resp = await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        # Account is created but email failed — route raises HTTPException(201)
        assert resp.status_code == 201
        assert "verification email could not be sent" in resp.json()["detail"]

    async def test_register_weak_password_422(self, client):
        resp = await client.post(
            REGISTER_URL, json={**VALID_PAYLOAD, "password": "weak"}
        )
        assert resp.status_code == 422

    async def test_register_invalid_email_422(self, client):
        resp = await client.post(
            REGISTER_URL, json={**VALID_PAYLOAD, "email": "not-an-email"}
        )
        assert resp.status_code == 422

    async def test_register_missing_field_422(self, client):
        resp = await client.post(REGISTER_URL, json={"username": "uche"})
        assert resp.status_code == 422


# ── /auth/verify-email ────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVerifyEmailRoute:

    @patch("app.api.auth_routes.send_verification_email")
    @patch("app.services.auth_service.publish_user_registered")
    async def test_verify_email_activates_user(self, mock_pub, mock_email, client):
        await client.post(REGISTER_URL, json=VALID_PAYLOAD)

        from app.utils.verification import generate_verification_token
        token = generate_verification_token(VALID_PAYLOAD["email"])

        resp = await client.get(f"{VERIFY_URL}?token={token}")
        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()

    async def test_verify_invalid_token_400(self, client):
        resp = await client.get(f"{VERIFY_URL}?token=bogus.token.value")
        assert resp.status_code == 400

    async def test_verify_unknown_email_token_404(self, client):
        """Token is valid but no matching user exists."""
        from app.utils.verification import generate_verification_token
        token = generate_verification_token("ghost@example.com")
        resp = await client.get(f"{VERIFY_URL}?token={token}")
        assert resp.status_code == 404


# ── /auth/login ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLoginRoute:

    @pytest.fixture(autouse=True)
    def _patch_externals(self):
        with patch("app.services.auth_service.publish_user_registered"), \
             patch("app.api.auth_routes.send_verification_email"):
            yield

    async def _register_and_activate(self, client):
        await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        from app.utils.verification import generate_verification_token
        token = generate_verification_token(VALID_PAYLOAD["email"])
        await client.get(f"{VERIFY_URL}?token={token}")

    async def test_login_returns_tokens(self, client):
        await self._register_and_activate(client)
        resp = await client.post(
            LOGIN_URL, json={"username": "uche", "password": "Secure1!"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access" in data
        assert "refresh" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password_401(self, client):
        await self._register_and_activate(client)
        resp = await client.post(
            LOGIN_URL, json={"username": "uche", "password": "Wrong1!"}
        )
        assert resp.status_code == 401

    async def test_login_unverified_user_403(self, client):
        """User registered but email not yet verified → 403."""
        await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        resp = await client.post(
            LOGIN_URL, json={"username": "uche", "password": "Secure1!"}
        )
        assert resp.status_code == 403
        assert "verify your email" in resp.json()["detail"].lower()

    async def test_login_nonexistent_user_401(self, client):
        resp = await client.post(
            LOGIN_URL, json={"username": "ghost", "password": "Secure1!"}
        )
        assert resp.status_code == 401


# ── /auth/refresh ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRefreshRoute:

    @pytest.fixture(autouse=True)
    def _patch_externals(self):
        with patch("app.services.auth_service.publish_user_registered"), \
             patch("app.api.auth_routes.send_verification_email"):
            yield

    async def _get_tokens(self, client):
        await client.post(REGISTER_URL, json=VALID_PAYLOAD)
        from app.utils.verification import generate_verification_token
        token = generate_verification_token(VALID_PAYLOAD["email"])
        await client.get(f"{VERIFY_URL}?token={token}")
        resp = await client.post(
            LOGIN_URL, json={"username": "uche", "password": "Secure1!"}
        )
        return resp.json()

    async def test_refresh_returns_new_access_token(self, client):
        tokens = await self._get_tokens(client)
        resp = await client.post(
            REFRESH_URL,
            headers={"Authorization": f"Bearer {tokens['refresh']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access" in data
        assert data["token_type"] == "bearer"

    async def test_refresh_with_access_token_fails(self, client):
        """Passing an access token to /refresh must be rejected."""
        tokens = await self._get_tokens(client)
        resp = await client.post(
            REFRESH_URL,
            headers={"Authorization": f"Bearer {tokens['access']}"},
        )
        assert resp.status_code == 422

    async def test_refresh_without_token_fails(self, client):
        resp = await client.post(REFRESH_URL)
        assert resp.status_code == 401
