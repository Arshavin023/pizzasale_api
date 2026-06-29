import os
import httpx
from decimal import Decimal

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
if not PAYSTACK_SECRET_KEY:
    raise RuntimeError("PAYSTACK_SECRET_KEY is not set")

PAYSTACK_BASE_URL = "https://api.paystack.co"

HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type": "application/json",
}


class PaystackError(Exception):
    """Raised when Paystack API returns an error."""
    pass


async def initialize_transaction(
    email: str,
    amount_ngn: Decimal,
    order_id: str,
    reference: str,
) -> dict:
    """
    Initialize a Paystack transaction.
    Returns { authorization_url, reference, access_code }

    Amount must be in kobo (NGN × 100).
    We pass order_id as metadata so the webhook can identify which order
    this payment is for without relying solely on the reference.
    """
    amount_kobo = int(amount_ngn * 100)

    payload = {
        "email": email,
        "amount": amount_kobo,
        "currency": "NGN",
        "reference": reference,
        "metadata": {
            "order_id": order_id,
            "cancel_action": "http://localhost:8004",
        },
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{PAYSTACK_BASE_URL}/transaction/initialize",
            json=payload,
            headers=HEADERS,
        )

    data = resp.json()

    if not data.get("status"):
        raise PaystackError(
            f"Paystack initialization failed: {data.get('message', 'unknown error')}"
        )

    return data["data"]


async def verify_transaction(reference: str) -> dict:
    """
    Verify a Paystack transaction by reference.
    Returns the full transaction data from Paystack.
    Called after webhook fires to confirm the payment status.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=HEADERS,
        )

    data = resp.json()

    if not data.get("status"):
        raise PaystackError(
            f"Paystack verification failed: {data.get('message', 'unknown error')}"
        )

    return data["data"]
