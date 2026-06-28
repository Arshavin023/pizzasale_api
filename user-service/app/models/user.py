# import uuid6
# # 1. Add 'UUID' to the core sqlalchemy imports here:
# from sqlalchemy import Column, String, DateTime, func, JSON, UUID  
# # 2. DELETE OR COMMENT OUT THIS LINE:
# # from sqlalchemy.dialects.postgresql import UUID  

# from app.db.base import Base


# class UserProfile(Base):
#     __tablename__ = "user_profiles"

#     # In your model file:
#     id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())

#     # Change user_id to as_uuid=False so strings are passed directly to the DB layer
#     user_id = Column(UUID(as_uuid=False), unique=True, nullable=False, index=True)

#     # id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
#     # # Accepts clean text strings directly from events without casting overhead
#     # user_id = Column(UUID(as_uuid=False), unique=True, nullable=False, index=True)
#     username = Column(String(50), unique=True, nullable=False)
#     email = Column(String(255), unique=True, nullable=False)
#     full_name = Column(String(100), nullable=True)
#     avatar_url = Column(String(512), nullable=True)
#     phone = Column(String(20), nullable=True)
#     dietary_preferences = Column(JSON, nullable=True)
#     delivery_addresses = Column(JSON, nullable=True)
#     created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


import uuid6
from sqlalchemy import Column, String, Boolean, DateTime, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())

    # The auth-service user this profile belongs to. UNIQUE is what
    # makes the RabbitMQ consumer idempotent — a duplicate
    # user.registered event for the same user_id hits this constraint
    # and fails cleanly, instead of creating a second profile row.
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=False, index=True)

    email = Column(String(100), nullable=False)
    username = Column(String(50), nullable=False)

    full_name = Column(String(150), nullable=True)
    phone = Column(String(20), nullable=True)
    delivery_address = Column(String(255), nullable=True)

    dietary_preferences = Column(JSON, nullable=True)
    favorite_order = Column(JSON, nullable=True)
    notification_settings = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())