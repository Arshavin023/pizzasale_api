from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_jwt_auth2 import AuthJWT

from app.schemas.user_schema import UserProfileResponse, UserProfileUpdate
from app.services.user_service import UserProfileService
from app.db.session import get_db

router = APIRouter(prefix="/users", tags=["Users"])


def _require_self_or_403(authenticated_username: str, profile_username: str) -> None:
    """
    The JWT only carries a username (and is_staff), not the user_id
    itself — auth-service issues tokens with `subject=username`. This
    checks the caller's token-username against the profile's username
    to enforce "you can only access your own profile" until a richer
    authorization scheme (staff/admin override, etc.) is needed.
    """
    if authenticated_username != profile_username:
        raise HTTPException(status_code=403, detail="Not authorized to access this profile")


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends(),
):
    Authorize.jwt_required()
    current_username = Authorize.get_jwt_subject()

    profile = await UserProfileService.get_profile_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    _require_self_or_403(current_username, profile.username)

    return profile


@router.patch("/{user_id}", response_model=UserProfileResponse)
async def update_user_profile(
    user_id: str,
    updates: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends(),
):
    Authorize.jwt_required()
    current_username = Authorize.get_jwt_subject()

    profile = await UserProfileService.get_profile_by_user_id(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    _require_self_or_403(current_username, profile.username)

    # exclude_unset=True: only fields the client actually sent are
    # included — a field omitted from the request body is left alone,
    # not overwritten with None. This is what makes it a real PATCH.
    update_data = updates.model_dump(exclude_unset=True)

    updated_profile = await UserProfileService.update_profile(db, profile, update_data)
    return updated_profile