import os
import json
import logging
import pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL is not set")

EXCHANGE_NAME = "payment_events"
EXCHANGE_TYPE = "topic"


def _publish(routing_key: str, message: dict) -> None:
    try:
        params = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type=EXCHANGE_TYPE,
            durable=True,
        )

        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

        connection.close()
        logger.info(f"Published {routing_key} for order_id={message.get('order_id')}")

    except Exception as e:
        # Event publish failure must not affect the payment record already
        # written to the DB. Log and move on — a reconciliation job can
        # pick up missed events in production.
        logger.error(f"Failed to publish {routing_key}: {e}")


def publish_payment_succeeded(order_id: str, user_id: str, amount: str, reference: str) -> None:
    _publish("payment.succeeded", {
        "event": "payment.succeeded",
        "order_id": order_id,
        "user_id": user_id,
        "amount": amount,
        "reference": reference,
    })


def publish_payment_failed(order_id: str, user_id: str, reference: str, reason: str) -> None:
    _publish("payment.failed", {
        "event": "payment.failed",
        "order_id": order_id,
        "user_id": user_id,
        "reference": reference,
        "reason": reason,
    })
