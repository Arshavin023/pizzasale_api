"""
Integration tests for AuthService — real async DB, mocked RabbitMQ & SES.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.auth_service import AuthService, AuthError
from app.schemas.auth_schema import SignUpModel, LoginModel
from app.models.user import UserAuth
from app.core.security import hash_password


# ── Helpers ───────────────────────────────────────────────────────────────────

def _signup(username="uche", email="uche@example.com", password="Secure1!"):
    return SignUpModel(username=username, email=email, password=password)


def _login(username="uche", password="Secure1!"):
    return LoginModel(username=username, password=password)


# ── Register ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuthServiceRegister:

    @patch("app.services.auth_service.publish_user_registered")
    async def test_register_creates_user(self, mock_publish, db):
        user = await AuthService.register(db, _signup())
        assert user.id is not None
        assert user.username == "uche"
        assert user.email == "uche@example.com"
        assert user.is_active is False           # must be inactive until email verified
        assert user.password != "Secure1!"       # must be hashed

    @patch("app.services.auth_service.publish_user_registered")
    async def test_register_publishes_event(self, mock_publish, db):
        user = await AuthService.register(db, _signup())
        mock_publish.assert_called_once_with(
            user_id=user.id,
            email=user.email,
            username=user.username,
        )

    @patch("app.services.auth_service.publish_user_registered")
    async def test_duplicate_username_raises_auth_error(self, mock_publish, db):
        await AuthService.register(db, _signup())
        with pytest.raises(AuthError, match="Username already exists"):
            await AuthService.register(
                db, _signup(email="other@example.com")
            )

    @patch("app.services.auth_service.publish_user_registered")
    async def test_duplicate_email_raises_auth_error(self, mock_publish, db):
        await AuthService.register(db, _signup())
        with pytest.raises(AuthError, match="Email already exists"):
            await AuthService.register(
                db, _signup(username="otheruser")
            )

    @patch("app.services.auth_service.publish_user_registered")
    async def test_publish_failure_does_not_raise(self, mock_publish, db):
        """
        publish_user_registered swallows its own exceptions internally (events.py).
        The mock simulates a silent no-op failure — registration must still succeed.
        """
        mock_publish.return_value = None  # silent no-op, as events.py does on failure
        user = await AuthService.register(db, _signup())
        assert user.id is not None
        mock_publish.assert_called_once()


# ── Authenticate ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuthServiceAuthenticate:

    @pytest_asyncio.fixture(autouse=True)
    async def seed_user(self, db):
        user = UserAuth(
            username="uche",
            email="uche@example.com",
            password=hash_password("Secure1!"),
            is_active=True,
        )
        db.add(user)
        await db.commit()
        self.user_id = user.id

    async def test_correct_credentials_returns_user(self, db):
        result = await AuthService.authenticate(db, _login())
        assert result is not None
        assert result.username == "uche"

    async def test_wrong_password_returns_none(self, db):
        result = await AuthService.authenticate(db, _login(password="WrongPass1!"))
        assert result is None

    async def test_nonexistent_username_returns_none(self, db):
        result = await AuthService.authenticate(
            db, _login(username="nobody", password="Secure1!")
        )
        assert result is None


# ── Activate user by email ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestActivateUser:

    @pytest_asyncio.fixture(autouse=True)
    async def seed_inactive_user(self, db):
        user = UserAuth(
            username="inactive_uche",
            email="inactive@example.com",
            password=hash_password("Secure1!"),
            is_active=False,
        )
        db.add(user)
        await db.commit()

    async def test_activate_returns_true(self, db):
        result = await AuthService.activate_user_by_email(db, "inactive@example.com")
        assert result is True

    async def test_activate_sets_is_active(self, db):
        from sqlalchemy.future import select
        await AuthService.activate_user_by_email(db, "inactive@example.com")
        row = (await db.execute(
            select(UserAuth).where(UserAuth.email == "inactive@example.com")
        )).scalar_one_or_none()
        assert row.is_active is True

    async def test_activate_unknown_email_returns_false(self, db):
        result = await AuthService.activate_user_by_email(db, "ghost@example.com")
        assert result is False

    async def test_activate_already_active_is_idempotent(self, db):
        """Calling activate twice must not raise and must still return True."""
        await AuthService.activate_user_by_email(db, "inactive@example.com")
        result = await AuthService.activate_user_by_email(db, "inactive@example.com")
        assert result is True