import os
import json
import logging
import pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL is not set")

EXCHANGE_NAME = "user_events"
EXCHANGE_TYPE = "topic"
ROUTING_KEY_USER_REGISTERED = "user.registered"


def _get_connection() -> pika.BlockingConnection:
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def _declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    """
    Declares the exchange this service publishes to. Idempotent —
    safe to call on every publish; RabbitMQ no-ops if it already
    exists with matching settings.

    Only the exchange is declared here, not the queue. Queues are
    owned by whoever consumes from them (user-service declares its
    own queue and binds it) — the publisher shouldn't need to know
    who's listening or how many consumers exist.
    """
    channel.exchange_declare(
        exchange=EXCHANGE_NAME,
        exchange_type=EXCHANGE_TYPE,
        durable=True,  # survives a RabbitMQ restart
    )


def publish_user_registered(user_id: str, email: str, username: str) -> None:
    """
    Publishes a user.registered event. Other services (user-service,
    eventually notification-service, etc.) can independently bind a
    queue to this exchange to react to it.

    Failure here is logged, not raised — a notification problem
    should never roll back or fail a successful registration. The
    auth account is the source of truth; a missed event can be
    recovered later (e.g. a reconciliation job, or simply re-publishing).
    """
    try:
        connection = _get_connection()
        channel = connection.channel()
        _declare_topology(channel)

        message = {
            "event": "user.registered",
            "user_id": str(user_id),
            "email": email,
            "username": username,
        }

        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=ROUTING_KEY_USER_REGISTERED,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent — survives a broker restart
                content_type="application/json",
            ),
        )

        connection.close()
        logger.info(f"Published user.registered event for user_id={user_id}")

    except Exception as e:
        logger.error(f"Failed to publish user.registered event for user_id={user_id}: {e}")