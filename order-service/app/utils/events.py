import os
import json
import logging
import pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL is not set")

EXCHANGE_NAME = "order_events"
EXCHANGE_TYPE = "topic"
ROUTING_KEY_ORDER_PLACED = "order.placed"


def publish_order_placed(order_id: str, user_id: str, total_amount: str, items: list) -> None:
    """
    Publishes an order.placed event so payment-service (and any future
    service) can react independently without order-service calling them.
    Failure is logged but does not fail the checkout — the order has
    already been confirmed in the DB. A reconciliation job or retry
    mechanism can handle missed events in production.
    """
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type=EXCHANGE_TYPE,
            durable=True,
        )

        message = {
            "event": "order.placed",
            "order_id": order_id,
            "user_id": user_id,
            "total_amount": total_amount,
            "items": items,
        }

        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=ROUTING_KEY_ORDER_PLACED,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

        connection.close()
        logger.info(f"Published order.placed event for order_id={order_id}")

    except Exception as e:
        logger.error(f"Failed to publish order.placed for order_id={order_id}: {e}")
