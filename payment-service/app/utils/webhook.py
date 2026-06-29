import os
import hmac
import hashlib

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify that an incoming webhook request genuinely came from Paystack.

    Paystack signs every webhook body with your secret key using HMAC-SHA512
    and sends the signature in the 'x-paystack-signature' header. We compute
    the expected signature from the raw request body and compare — if they
    don't match, the request is forged and must be rejected.

    IMPORTANT: We must use the raw bytes of the request body, not a parsed
    version — even a single whitespace difference changes the hash entirely.
    """
    expected = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
