import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from app.schemas.auth_schema import SignUpModel, LoginModel, TokenResponse, RefreshResponse
from app.services.auth_service import AuthService, AuthError
from app.db.session import get_db
from app.utils.verification import generate_verification_token, confirm_verification_token
from app.utils.email import send_verification_email
from fastapi_jwt_auth2 import AuthJWT

router = APIRouter(prefix="/auth", tags=["Auth"])

# Base URL the verification link points back to. In this local-dev
# setup, the link targets auth-service directly. Once there's an API
# gateway or public-facing domain, point this there instead.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8001")


@router.post("/register")
async def register(user: SignUpModel, db: AsyncSession = Depends(get_db)):
    try:
        created_user = await AuthService.register(db, user)
    except AuthError as e:
        raise HTTPException(status_code=409, detail=str(e))

    token = generate_verification_token(created_user.email)
    verification_link = f"{APP_BASE_URL}/auth/verify-email?token={token}"

    try:
        send_verification_email(created_user.email, verification_link)
    except RuntimeError as e:
        # The user account was already created successfully — don't
        # roll that back just because the email failed to send (e.g.
        # SES sandbox mode rejecting an unverified recipient). Surface
        # this clearly rather than silently swallowing it, since the
        # user otherwise has no way to verify their account.
        print("SEND VERIFICATION EMAIL ERROR:", str(e))
        raise HTTPException(
            status_code=201,
            detail="Account created, but the verification email could not be sent. Contact support.",
        )

    return {"message": "User created. Check your email to verify your account."}


@router.get("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    email = confirm_verification_token(token)

    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    activated = await AuthService.activate_user_by_email(db, email)

    if not activated:
        raise HTTPException(status_code=404, detail="No account found for this verification link")

    return {"message": "Email verified. You can now log in."}


@router.post("/login", response_model=TokenResponse)
async def login(
    user: LoginModel,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends()
    ):
    db_user = await AuthService.authenticate(db, user)

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not db_user.is_active:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")

    access = Authorize.create_access_token(
        subject=db_user.username,
        expires_time=timedelta(minutes=15),
        user_claims={"is_staff": db_user.is_staff}
    )

    refresh = Authorize.create_refresh_token(subject=db_user.username)

    return {"access": access,
            "refresh": refresh,
            "token_type": "bearer"
            }


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(Authorize: AuthJWT = Depends()):
    Authorize.jwt_refresh_token_required()

    current_user = Authorize.get_jwt_subject()
    new_access = Authorize.create_access_token(
        subject=current_user,
        expires_time=timedelta(minutes=15),
    )

    return {"access": new_access, "token_type": "bearer"}
