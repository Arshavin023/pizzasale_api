# from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
# from sqlalchemy.orm import sessionmaker
# import os

# DATABASE_URL = os.getenv("DATABASE_URL")
# if not DATABASE_URL:
#     raise RuntimeError("DATABASE_URL is missing inside container")

# engine = create_async_engine(
#     DATABASE_URL,
#     echo=False,
#     pool_size=10,
#     max_overflow=20,
#     pool_pre_ping=True,
#     pool_recycle=300
# )

# AsyncSessionLocal = sessionmaker(
#     bind=engine,
#     class_=AsyncSession,
#     expire_on_commit=False
# )

# async def get_db():
#     async with AsyncSessionLocal() as session:
#         yield session

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing inside container")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=300
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# Indirection layer for code that needs to open a DB session outside the
# normal FastAPI request lifecycle — e.g. a BackgroundTask running after
# the HTTP response has already been sent, where Depends(get_db) is no
# longer valid (the request-scoped session is closed).
#
# This is a function returning the session factory, not the factory itself,
# specifically so tests can monkeypatch get_session_factory() to point at
# a test database engine instead of the real one — the same way
# app.dependency_overrides works for Depends(get_db), but for code paths
# that don't go through FastAPI's dependency injection at all.
def get_session_factory():
    return AsyncSessionLocal