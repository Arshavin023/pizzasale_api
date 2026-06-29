"""
Shared fixtures for order-service tests.
"""
import os
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only")
os.environ.setdefault("PRODUCT_SERVICE_URL", "http://product-service:8000")

from sqlalchemy import String, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from uuid import UUID
from httpx import AsyncClient, ASGITransport

from app.db.base import Base
from app.db.session import get_db
from app.core.auth import get_current_user_id
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class UUIDasStr(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value


def _patch_uuid_columns():
    patched = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, PG_UUID):
                col.type = UUIDasStr()
                patched.append(col)
    return patched


def _restore_uuid_columns(patched):
    for col in patched:
        col.type = PG_UUID(as_uuid=True)


@pytest_asyncio.fixture(scope="function")
async def db():
    patched = _patch_uuid_columns()

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
    _restore_uuid_columns(patched)


@pytest_asyncio.fixture(scope="function")
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def make_token(user_id: str, username: str = "testuser", is_staff: bool = False) -> str:
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


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()