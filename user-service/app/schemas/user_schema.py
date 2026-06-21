from pydantic import BaseModel
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class UserProfileResponse(BaseModel):
    user_id: UUID
    email: str
    username: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    delivery_address: Optional[str] = None
    dietary_preferences: Optional[Any] = None
    favorite_order: Optional[Any] = None
    notification_settings: Optional[Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """
    All fields optional — this is a PATCH (partial update) schema.
    Only fields the client actually includes get changed; everything
    else on the existing profile is left untouched.
    """
    full_name: Optional[str] = None
    phone: Optional[str] = None
    delivery_address: Optional[str] = None
    dietary_preferences: Optional[Any] = None
    favorite_order: Optional[Any] = None
    notification_settings: Optional[Any] = None