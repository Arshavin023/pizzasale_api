"""
Auth-service test fixtures.
"""
import os
import pytest
import pytest_asyncio

# ── Set env vars BEFORE any app module is imported ───────────────────────────
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-ci")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("SES_SENDER_EMAIL", "no-reply@test.example")
# Point the app's own session module at SQLite before it's imported
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from fastapi_jwt_auth2 import AuthJWT
from pydantic import BaseModel

# 1. Define the JWT Settings schema expected by fastapi-jwt-auth2
class JWTSettings(BaseModel):
    authjwt_secret_key: str = os.getenv("JWT_SECRET", "test-secret-key-for-ci")

# 2. Register the configuration callback hook
@AuthJWT.load_config
def get_cookie_status():
    return JWTSettings()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event as sa_event
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport

from app.db.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine():
    """
    SQLite-compatible engine.
    StaticPool: single shared in-memory DB across all connections in one test.
    No pool_size/max_overflow — those are Postgres-only args.
    """
    return create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest_asyncio.fixture(scope="function")
async def engine():
    _engine = _make_engine()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(engine):
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(engine):
    from app.main import app
    from app.db.session import get_db

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


# ── Token helpers ─────────────────────────────────────────────────────────────

def make_staff_token() -> str:
    from fastapi_jwt_auth2 import AuthJWT
    from datetime import timedelta
    auth = AuthJWT()
    return auth.create_access_token(
        subject="staffuser",
        expires_time=timedelta(hours=1),
        user_claims={"is_staff": True},
    )

def make_token(user_id: str = "uche", is_staff: bool = False) -> str:
    from fastapi_jwt_auth2 import AuthJWT
    from datetime import timedelta
    auth = AuthJWT()
    return auth.create_access_token(
        subject=user_id,  # Now correctly embedding the UUID string
        expires_time=timedelta(hours=1),
        user_claims={"is_staff": is_staff},
    )