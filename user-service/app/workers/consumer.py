import os
import json
import logging
import asyncio
import pika

from app.db.session import SessionLocal as AsyncSessionLocal
from app.services.user_service import UserProfileService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL is not set")

EXCHANGE_NAME = "user_events"
EXCHANGE_TYPE = "topic"
QUEUE_NAME = "user_service.user_registered"
ROUTING_KEY = "user.registered"


async def _process_message(body: bytes) -> bool:
    """
    Parses and handles one user.registered event.
    Returns True if it should be acknowledged (success or known
    duplicate), False if it should be retried/requeued (transient
    failure, e.g. database temporarily unreachable).
    """
    try:
        message = json.loads(body)
    except json.JSONDecodeError:
        # Malformed message — retrying won't fix this. Log and ack so
        # it doesn't loop forever; a malformed message stuck in an
        # infinite redelivery loop is worse than dropping one bad event.
        logger.error(f"Received unparseable message, dropping: {body!r}")
        return True

    user_id = message.get("user_id")
    email = message.get("email")
    username = message.get("username")

    if not all([user_id, email, username]):
        logger.error(f"Received malformed user.registered event, dropping: {message}")
        return True

    async with AsyncSessionLocal() as db:
        try:
            created = await UserProfileService.create_profile_from_event(
                db, user_id=user_id, email=email, username=username
            )
            if created:
                logger.info(f"Created profile for user_id={user_id}")
            return True
        except Exception as e:
            # Genuine transient failure (e.g. DB connection issue) —
            # don't ack, let RabbitMQ redeliver.
            logger.error(f"Failed to process event for user_id={user_id}: {e}")
            return False


def _on_message(channel, method_frame, properties, body, loop: asyncio.AbstractEventLoop):
    should_ack = loop.run_until_complete(_process_message(body))

    if should_ack:
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
    else:
        # requeue=True: put it back for another attempt rather than
        # discarding — appropriate for transient failures only.
        channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=True)


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.exchange_declare(
        exchange=EXCHANGE_NAME,
        exchange_type=EXCHANGE_TYPE,
        durable=True,
    )

    # This consumer owns and declares its own queue — it doesn't rely
    # on auth-service (or anyone else) to have created it. Durable so
    # the queue itself survives a RabbitMQ restart; messages inside it
    # survive too, since the publisher sends them as persistent
    # (delivery_mode=2).
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(
        exchange=EXCHANGE_NAME,
        queue=QUEUE_NAME,
        routing_key=ROUTING_KEY,
    )

    # prefetch_count=1: only hand this consumer one message at a time
    # before it acks/nacks. Keeps things simple and predictable for
    # now — revisit if throughput ever actually demands batching.
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=lambda ch, method, props, body: _on_message(ch, method, props, body, loop),
        auto_ack=False,  # manual ack — this is what makes at-least-once delivery meaningful
    )

    logger.info(f"Consumer started. Listening on queue '{QUEUE_NAME}' bound to '{EXCHANGE_NAME}'...")

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()
        loop.close()


if __name__ == "__main__":
    main()