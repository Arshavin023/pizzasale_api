import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import pool, create_engine
from alembic import context

from app.db.base import Base
from app.models import cart, order

config = context.config

DATABASE_URL = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set for Alembic")

SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=SYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(
        SYNC_DATABASE_URL,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
