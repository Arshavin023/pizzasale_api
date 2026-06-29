import os
import httpx
import logging

logger = logging.getLogger(__name__)

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")


async def update_order_status(order_id: str, status: str) -> bool:
    """
    Notify order-service of a payment outcome so it can update the order status.
    payment.succeeded → order becomes 'paid'
    payment.failed    → order becomes 'cancelled'

    Returns True on success, False on failure (logged but not raised —
    the payment record is already written; order status update is best-effort
    here, with the RabbitMQ event as the durable fallback).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{ORDER_SERVICE_URL}/orders/{order_id}/status",
                json={"status": status},
            )
        if resp.status_code == 200:
            return True
        logger.error(
            f"order-service returned {resp.status_code} updating order {order_id} to {status}"
        )
        return False
    except httpx.RequestError as e:
        logger.error(f"Could not reach order-service to update order {order_id}: {e}")
        return False
