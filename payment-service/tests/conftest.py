"""
Shared fixtures for payment-service tests.

Uses SQLite in-memory DB. JSONB columns (paystack_response) are replaced
with Text for SQLite compatibility — same UUID patching pattern as order-service.
PAYSTACK_SECRET_KEY is set to a known test value so webhook signature
tests can compute correct HMAC without hitting the real Paystack API.
"""
import os
import uuid
import hmac
import hashlib
import pytest
import pytest_asyncio
from datetime import datetime

# Set env vars before any app imports
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("ORDER_SERVICE_URL", "http://order-service:8000")
# Do NOT override PAYSTACK_SECRET_KEY — the container already has it from .env
# and webhook.py reads it at module import time. We read it back here so
# our test signatures match what verify_webhook_signature computes.
TEST_SECRET = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_paystack_secret_for_testing")

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient, ASGITransport

from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ── SQLite type compatibility ──────────────────────────────────────

class UUIDasStr(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        try:
            return uuid.UUID(str(value)) if value is not None else None
        except (ValueError, AttributeError):
            return value


class JSONasText(TypeDecorator):
    """Store JSONB as Text in SQLite."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        import json
        return json.dumps(value) if value is not None else None

    def process_result_value(self, value, dialect):
        import json
        try:
            return json.loads(value) if value is not None else None
        except (ValueError, TypeError):
            return value


def _patch_columns():
    patched = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, PG_UUID):
                col.type = UUIDasStr()
                patched.append((col, "uuid"))
            elif isinstance(col.type, JSONB):
                col.type = JSONasText()
                patched.append((col, "jsonb"))
    return patched


def _restore_columns(patched):
    for col, kind in patched:
        if kind == "uuid":
            col.type = PG_UUID(as_uuid=True)
        elif kind == "jsonb":
            col.type = JSONB()


# ── Fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def db():
    patched = _patch_columns()

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
        # Stash the session_factory on the session object itself so the
        # client fixture can retrieve it without needing a second fixture
        # — keeps the existing `db` fixture signature unchanged for tests
        # that only use it directly.
        session._test_session_factory = session_factory
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
    _restore_columns(patched)


@pytest_asyncio.fixture(scope="function")
async def client(db, monkeypatch):
    async def override_get_db():
        yield db

    # Background tasks (e.g. webhook processing after the HTTP response is
    # sent) open their own session via get_session_factory() rather than
    # Depends(get_db) — it's a plain function call inside payment_routes.py,
    # not a FastAPI dependency, so app.dependency_overrides can't intercept
    # it. We monkeypatch the function directly so it returns a factory bound
    # to the same in-memory SQLite engine the rest of the test uses, making
    # background-task writes visible to assertions made against `db`.
    test_session_factory = db._test_session_factory
    monkeypatch.setattr(
        "app.api.payment_routes.get_session_factory",
        lambda: test_session_factory,
    )

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Webhook signature helper ──────────────────────────────────────

def make_webhook_signature(body: bytes) -> str:
    """
    Compute the correct HMAC-SHA512 signature for a webhook body
    using the test secret key — matches what verify_webhook_signature expects.
    """
    return hmac.new(
        TEST_SECRET.encode("utf-8"),
        body,
        hashlib.sha512,
    ).hexdigest()


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()