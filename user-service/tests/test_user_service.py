"""
Unit/integration tests for UserProfileService.
"""
import uuid
import pytest
import pytest_asyncio

from app.models.user import UserProfile
from app.services.user_service import UserProfileService


def _uuid() -> uuid.UUID:
    # Returns a native UUID object so SQLAlchemy can process .hex smoothly
    return uuid.uuid4()


# ── create_profile_from_event ─────────────────────────────────────────────────

@pytest.mark.asyncio
class TestCreateProfileFromEvent:

    async def test_creates_profile_returns_true(self, db):
        uid = _uuid()
        result = await UserProfileService.create_profile_from_event(
            db, user_id=uid, email="uche@example.com", username="uche"
        )
        assert result is True

    async def test_profile_fields_stored_correctly(self, db):
        uid = _uuid()
        await UserProfileService.create_profile_from_event(
            db, user_id=uid, email="uche@example.com", username="uche"
        )
        profile = await UserProfileService.get_profile_by_user_id(db, uid)
        assert profile is not None
        assert profile.email == "uche@example.com"
        assert profile.username == "uche"

    async def test_duplicate_event_returns_false(self, db):
        uid = _uuid()
        await UserProfileService.create_profile_from_event(
            db, user_id=uid, email="uche@example.com", username="uche"
        )
        result = await UserProfileService.create_profile_from_event(
            db, user_id=uid, email="uche@example.com", username="uche"
        )
        assert result is False

    async def test_duplicate_does_not_create_second_row(self, db):
        from sqlalchemy.future import select
        uid = _uuid()
        await UserProfileService.create_profile_from_event(
            db, user_id=uid, email="uche@example.com", username="uche"
        )
        await UserProfileService.create_profile_from_event(
            db, user_id=uid, email="uche@example.com", username="uche"
        )
        rows = (await db.execute(
            select(UserProfile).where(UserProfile.user_id == uid)
        )).scalars().all()
        assert len(rows) == 1


# ── get_profile_by_user_id ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetProfile:

    async def test_returns_none_for_unknown_user_id(self, db):
        result = await UserProfileService.get_profile_by_user_id(db, _uuid())
        assert result is None

    async def test_returns_profile_for_known_user_id(self, db):
        uid = _uuid()
        await UserProfileService.create_profile_from_event(
            db, user_id=uid, email="uche@example.com", username="uche"
        )
        profile = await UserProfileService.get_profile_by_user_id(db, uid)
        assert profile is not None
        assert profile.user_id == uid


# ── update_profile ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestUpdateProfile:

    @pytest_asyncio.fixture(autouse=True)
    async def seed(self, db):
        self.uid = _uuid()
        await UserProfileService.create_profile_from_event(
            db, user_id=self.uid, email="uche@example.com", username="uche"
        )

    async def test_full_name_updated(self, db):
        profile = await UserProfileService.get_profile_by_user_id(db, self.uid)
        updated = await UserProfileService.update_profile(
            db, profile, {"full_name": "Uche Nnodim"}
        )
        assert updated.full_name == "Uche Nnodim"

    async def test_partial_update_leaves_other_fields_unchanged(self, db):
        profile = await UserProfileService.get_profile_by_user_id(db, self.uid)
        await UserProfileService.update_profile(db, profile, {"phone": "+2348000000000"})

        profile = await UserProfileService.get_profile_by_user_id(db, self.uid)
        assert profile.phone == "+2348000000000"
        assert profile.full_name is None

    async def test_json_fields_stored(self, db):
        profile = await UserProfileService.get_profile_by_user_id(db, self.uid)
        prefs = {"allergens": ["nuts"], "vegan": False}
        updated = await UserProfileService.update_profile(
            db, profile, {"dietary_preferences": prefs}
        )
        assert updated.dietary_preferences == prefs

    async def test_multiple_fields_updated_atomically(self, db):
        profile = await UserProfileService.get_profile_by_user_id(db, self.uid)
        updated = await UserProfileService.update_profile(
            db, profile, {"full_name": "Uche", "delivery_address": "Abuja, FCT"}
        )
        assert updated.full_name == "Uche"
        assert updated.delivery_address == "Abuja, FCT"