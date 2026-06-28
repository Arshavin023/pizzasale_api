"""
End-to-end tests for user-service HTTP routes.
"""
import uuid
import pytest
import pytest_asyncio

from app.services.user_service import UserProfileService

USERS_URL = "/users"


class SQLStringUUID(str):
    """
    A string subclass that tricks SQLAlchemy into thinking it's a native UUID object 
    by mimicking the `.hex` property, returning the underlying clean string value.
    """
    @property
    def hex(self) -> str:
        # If there are hyphens, remove them to behave exactly like uuid.UUID().hex
        return self.replace("-", "")


def _uuid():
    return SQLStringUUID(str(uuid.uuid4()))


async def _seed_profile(db, uid=None, username="uche"):
    uid_str = uid or _uuid()
    # Pass it cleanly as our string wrapper so SQLAlchemy can call .hex
    await UserProfileService.create_profile_from_event(
        db, user_id=uid_str, email=f"{username}@example.com", username=username
    )
    return uid_str


# ── GET /users/{user_id} ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetUserProfile:

    async def test_get_own_profile_200(self, client, db):
        uid = await _seed_profile(db, username="uche")
        from conftest import make_token
        token = make_token(username="uche")

        resp = await client.get(
            f"{USERS_URL}/{uid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "uche"
        assert data["email"] == "uche@example.com"

    async def test_get_profile_unauthenticated_401(self, client, db):
        uid = await _seed_profile(db)
        resp = await client.get(f"{USERS_URL}/{uid}")
        assert resp.status_code == 401

    async def test_get_other_users_profile_403(self, client, db):
        uid = await _seed_profile(db, username="victim")
        from conftest import make_token
        token = make_token(username="attacker")

        resp = await client.get(
            f"{USERS_URL}/{uid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_get_nonexistent_profile_404(self, client, db):
        from conftest import make_token
        token = make_token(username="uche")
        resp = await client.get(
            f"{USERS_URL}/{_uuid()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ── PATCH /users/{user_id} ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestUpdateUserProfile:

    async def test_update_full_name_200(self, client, db):
        uid = await _seed_profile(db, username="uche")
        from conftest import make_token
        token = make_token(username="uche")

        resp = await client.patch(
            f"{USERS_URL}/{uid}",
            json={"full_name": "Uche Nnodim"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Uche Nnodim"

    async def test_patch_is_partial_other_fields_unchanged(self, client, db):
        uid = await _seed_profile(db, username="uche")
        from conftest import make_token
        token = make_token(username="uche")

        patch_resp = await client.patch(
            f"{USERS_URL}/{uid}",
            json={"full_name": "Uche Nnodim"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp.status_code == 200

        patch_resp2 = await client.patch(
            f"{USERS_URL}/{uid}",
            json={"delivery_address": "Abuja, FCT"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert patch_resp2.status_code == 200
        data = patch_resp2.json()
        assert data["delivery_address"] == "Abuja, FCT"
        assert data["full_name"] == "Uche Nnodim"   

    async def test_update_json_field(self, client, db):
        uid = await _seed_profile(db, username="uche")
        from conftest import make_token
        token = make_token(username="uche")

        prefs = {"vegan": True, "allergens": ["gluten"]}
        resp = await client.patch(
            f"{USERS_URL}/{uid}",
            json={"dietary_preferences": prefs},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["dietary_preferences"] == prefs

    async def test_update_other_users_profile_403(self, client, db):
        uid = await _seed_profile(db, username="victim")
        from conftest import make_token
        token = make_token(username="attacker")

        resp = await client.patch(
            f"{USERS_URL}/{uid}",
            json={"full_name": "Hacked"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_update_unauthenticated_401(self, client, db):
        uid = await _seed_profile(db, username="uche")
        resp = await client.patch(f"{USERS_URL}/{uid}", json={"full_name": "X"})
        assert resp.status_code == 401

    async def test_update_nonexistent_profile_404(self, client, db):
        from conftest import make_token
        token = make_token(username="uche")
        resp = await client.patch(
            f"{USERS_URL}/{_uuid()}",
            json={"full_name": "Ghost"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ── GET /health ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}