import os
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")

# Retry configuration — money correctness justifies retrying before giving up.
# 3 attempts with exponential backoff (1s, 2s, 4s) covers transient network
# blips and brief order-service restarts without holding the webhook response
# open for an unreasonable amount of time (Paystack expects a fast response).
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 5.0


async def update_order_status(order_id: str, status: str) -> bool:
    """
    Notify order-service of a payment outcome so it can update the order status.
    payment.succeeded → order becomes 'paid'
    payment.failed    → order becomes 'cancelled'

    This is the money-correctness-critical call: a payment must never be marked
    succeeded in payment_service_db while the corresponding order is silently
    left in pending_payment. We retry with exponential backoff before giving up,
    and the caller is responsible for surfacing a hard failure (e.g. via
    reconciliation) if all retries are exhausted — this function does not
    raise, since the payment record itself must still be written regardless.

    Returns True on success, False if all retries are exhausted.
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.patch(
                    f"{ORDER_SERVICE_URL}/orders/{order_id}/status",
                    json={"status": status},
                )
            if resp.status_code == 200:
                if attempt > 1:
                    logger.info(
                        f"order-service status update succeeded on attempt {attempt} "
                        f"for order {order_id} -> {status}"
                    )
                return True

            last_error = f"order-service returned {resp.status_code}: {resp.text}"
            logger.warning(
                f"Attempt {attempt}/{MAX_RETRIES} failed updating order {order_id} "
                f"to {status}: {last_error}"
            )

        except httpx.RequestError as e:
            last_error = str(e)
            logger.warning(
                f"Attempt {attempt}/{MAX_RETRIES} - could not reach order-service "
                f"for order {order_id}: {last_error}"
            )

        if attempt < MAX_RETRIES:
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            await asyncio.sleep(delay)

    # All retries exhausted - this is a genuine inconsistency between
    # payment_service_db and order_service_db. Log loudly; reconciliation
    # (see scripts/reconcile_payments.py) is the safety net that catches this.
    logger.error(
        f"CRITICAL: exhausted {MAX_RETRIES} retries updating order {order_id} "
        f"to {status}. Payment is recorded but order status is now INCONSISTENT. "
        f"Last error: {last_error}. Reconciliation job must catch this."
    )
    return False