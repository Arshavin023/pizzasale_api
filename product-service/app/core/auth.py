from fastapi import Depends, HTTPException
from fastapi_jwt_auth2 import AuthJWT


def require_staff(Authorize: AuthJWT = Depends()) -> None:
    """
    FastAPI dependency enforcing that the caller's JWT carries
    is_staff=True. Use on any write endpoint (create/update/delete).
    Read endpoints stay public — don't apply this dependency there.
    """
    Authorize.jwt_required()
    claims = Authorize.get_raw_jwt()

    if not claims.get("is_staff", False):
        raise HTTPException(status_code=403, detail="Staff access required")