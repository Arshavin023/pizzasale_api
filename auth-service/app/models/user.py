import uuid
import uuid6
from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class UserAuth(Base):
    __tablename__ = "users_auth"    
    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid6.uuid7())
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    is_staff = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())