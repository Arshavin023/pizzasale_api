import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is not set")

VERIFICATION_SALT = "email-verification"
VERIFICATION_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24  # 24 hours

_serializer = URLSafeTimedSerializer(JWT_SECRET)


def generate_verification_token(email: str) -> str:
    return _serializer.dumps(email, salt=VERIFICATION_SALT)


def confirm_verification_token(token: str) -> str | None:
    """
    Returns the email the token was issued for, or None if the token
    is invalid or expired. Caller decides how to respond either way —
    keep this function side-effect free.
    """
    try:
        return _serializer.loads(
            token,
            salt=VERIFICATION_SALT,
            max_age=VERIFICATION_TOKEN_MAX_AGE_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        return None
