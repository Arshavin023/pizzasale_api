import os
import httpx
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8000")


class PaymentServiceError(Exception):
    """Raised when payment-service is unreachable or returns an error."""
    pass


async def initialize_payment(
    order_id: str,
    user_id: str,
    email: str,
    amount: Decimal,
) -> dict:
    """
    Call payment-service to initialize a Paystack transaction.
    Returns { payment_id, authorization_url, reference }
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{PAYMENT_SERVICE_URL}/payments/initialize",
                json={
                    "order_id": order_id,
                    "user_id": user_id,
                    "email": email,
                    "amount": str(amount),
                },
            )
    except httpx.RequestError as e:
        raise PaymentServiceError(f"Could not reach payment-service: {e}")

    if resp.status_code != 201:
        raise PaymentServiceError(
            f"payment-service returned {resp.status_code}: {resp.text}"
        )

    return resp.json()
