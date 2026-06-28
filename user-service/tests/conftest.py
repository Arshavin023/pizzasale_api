import os
import pytest
import pytest_asyncio

# Set env vars BEFORE any app import
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-key-for-ci"
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# Import app.main NOW — this triggers jwt_config.py which registers
# @AuthJWT.load_config with JWT_SECRET already set above.
# Do NOT register load_config again here; two registrations conflict.
from app.main import app
from app.db.session import get_db

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport
from app.db.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Patch the session module's engine so the app uses SQLite
import app.db.session as _session_module
_session_module.engine = _test_engine
_session_module.SessionLocal = sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


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

def make_token(username: str = "uche", is_staff: bool = False) -> str:
    from fastapi_jwt_auth2 import AuthJWT
    from datetime import timedelta
    auth = AuthJWT()
    token = auth.create_access_token(
        subject=username,
        expires_time=timedelta(hours=1),
        user_claims={"is_staff": is_staff},
    )
    # fastapi-jwt-auth2 returns bytes — decode to str for use in headers
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token