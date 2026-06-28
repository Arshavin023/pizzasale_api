from fastapi import Depends
from fastapi_jwt_auth2 import AuthJWT
from uuid import UUID


def get_current_user_id(Authorize: AuthJWT = Depends()) -> UUID:
    """
    Verifies the JWT and extracts the user_id claim.
    Returns the user_id so route handlers can scope operations
    to the authenticated user — a user can only see/modify their
    own cart and orders.

    Note: user_id is stored as a custom claim since auth-service
    currently uses username as the JWT subject. See the known
    limitation in the README — embedding user_id directly in
    claims would be more direct.
    """
    Authorize.jwt_required()
    claims = Authorize.get_raw_jwt()
    user_id = claims.get("user_id")
    if not user_id:
        # Fallback: if user_id claim isn't present yet (auth-service
        # doesn't embed it today), raise a clear error rather than
        # silently using None as the user identifier.
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail="JWT is missing user_id claim. auth-service must be updated to embed user_id."
        )
    return UUID(user_id)
