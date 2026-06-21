# from pydantic import BaseModel, EmailStr
# from typing import Optional

# class SignUpModel(BaseModel):
#     username: str
#     email: EmailStr
#     password: str

# class LoginModel(BaseModel):
#     username: str
#     password: str

# class TokenResponse(BaseModel):
#     access: str
#     refresh: str
#     token_type: str = "bearer"

import re
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional


def validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one number")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\/;'`~]", password):
        raise ValueError("Password must contain at least one special character")
    return password


class SignUpModel(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class LoginModel(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access: str
    refresh: str
    token_type: str = "bearer"


class RefreshResponse(BaseModel):
    access: str
    token_type: str = "bearer"
