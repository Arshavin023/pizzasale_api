import os
import uuid as _uuid_mod
import pytest
import pytest_asyncio

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-key-for-ci"

# ── Patch Uuid.bind_processor BEFORE any model import ────────────────────────
# postgresql.UUID(as_uuid=True) inherits bind_processor from sqlalchemy.sql.sqltypes.Uuid.
# For non-native-uuid dialects (SQLite), it returns a closure that calls value.hex —
# but SQLite round-trips UUIDs as strings, so .hex fails.
# We replace bind_processor with one that safely handles both UUID objects and strings.
from sqlalchemy.sql.sqltypes import Uuid as _SA_Uuid

def _safe_bind_processor(self, dialect):
    character_based = not getattr(dialect, "supports_native_uuid", True) or not self.native_uuid
    if character_based and self.as_uuid:
        def process(value):
            if value is None:
                return None
            if isinstance(value, _uuid_mod.UUID):
                return value.hex
            # already a string (e.g. returned from SQLite) — strip dashes
            return str(value).replace("-", "")
        return process
    # Fall back to original logic for everything else
    return None

_SA_Uuid.bind_processor = _safe_bind_processor

# Also patch SizeEnum (postgresql.ENUM) bind for SQLite
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

_orig_enum_create = PG_ENUM.create.__func__ if hasattr(PG_ENUM.create, '__func__') else None

# Prevent postgresql ENUM from trying to CREATE TYPE on SQLite
def _noop_create(self, bind=None, checkfirst=False):
    pass

def _noop_drop(self, bind=None, checkfirst=False):
    pass

PG_ENUM.create = _noop_create
PG_ENUM.drop = _noop_drop

# ── Engine + session setup ────────────────────────────────────────────────────
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

import app.db.session as _session_module
_session_module.engine = _test_engine
_session_module.AsyncSessionLocal = sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Import app AFTER patching — triggers jwt_config.py with JWT_SECRET already set
from app.main import app
from app.db.session import get_db
from app.db.base import Base


@pytest_asyncio.fixture(scope="function")
async def engine():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _test_engine
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db(engine):
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(engine):
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def _decode(token) -> str:
    return token.decode("utf-8") if isinstance(token, bytes) else token


def make_staff_token() -> str:
    from fastapi_jwt_auth2 import AuthJWT
    from datetime import timedelta
    auth = AuthJWT()
    return _decode(auth.create_access_token(
        subject="staffuser",
        expires_time=timedelta(hours=1),
        user_claims={"is_staff": True},
    ))


def make_user_token() -> str:
    from fastapi_jwt_auth2 import AuthJWT
    from datetime import timedelta
    auth = AuthJWT()
    return _decode(auth.create_access_token(
        subject="regularuser",
        expires_time=timedelta(hours=1),
        user_claims={"is_staff": False},
    ))


async def create_category(client, name="Pizzas", display_order=1):
    token = make_staff_token()
    resp = await client.post(
        "/categories",
        json={"name": name, "display_order": display_order, "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_product(client, category_id: str, name="Margherita"):
    token = make_staff_token()
    resp = await client.post(
        "/products",
        json={
            "category_id": category_id,
            "name": name,
            "description": "Classic pizza",
            "is_available": True,
            "variants": [
                {"size": "small", "price": "8.99", "is_available": True},
                {"size": "large", "price": "14.99", "is_available": True},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()