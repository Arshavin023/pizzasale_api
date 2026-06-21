import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

from app.db.base import Base
from app.models import user



# Alembic config
config = context.config

# logging setup (kept standard)
# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)


# ----------------------------
# DATABASE URL HANDLING
# ----------------------------
DATABASE_URL = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set for Alembic")

# Convert async URL → sync URL for migrations
SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

# IMPORTANT: Alembic must use SYNC URL
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)


# ----------------------------
# METADATA (for autogenerate)
# ----------------------------
target_metadata = Base.metadata


# ----------------------------
# OFFLINE MODE
# ----------------------------
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


# ----------------------------
# ONLINE MODE
# ----------------------------
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


# ----------------------------
# ENTRY POINT
# ----------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()