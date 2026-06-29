import uuid
import logging
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.payment import Payment, PaymentStatus
from app.utils.paystack import initialize_transaction, verify_transaction, PaystackError
from app.utils.events import publish_payment_succeeded, publish_payment_failed
from app.utils.order_client import update_order_status

logger = logging.getLogger(__name__)


class PaymentService:

    @staticmethod
    async def initialize(
        db: AsyncSession,
        order_id: str,
        user_id: str,
        email: str,
        amount_ngn: Decimal,
    ) -> Payment:
        """
        Initialize a Paystack transaction and store a pending payment record.
        Returns the payment record containing the authorization_url to redirect
        the user to Paystack's hosted payment page.
        """
        # Generate a unique reference for this payment attempt.
        # Using uuid4 ensures it's unique even on retry.
        reference = f"PIZZA-{str(uuid.uuid4()).replace('-', '')[:16].upper()}"

        try:
            paystack_data = await initialize_transaction(
                email=email,
                amount_ngn=amount_ngn,
                order_id=order_id,
                reference=reference,
            )
        except PaystackError as e:
            raise

        payment = Payment(
            order_id=uuid.UUID(order_id),
            user_id=uuid.UUID(user_id),
            amount=amount_ngn,
            currency="NGN",
            status=PaymentStatus.pending,
            paystack_reference=paystack_data["reference"],
            authorization_url=paystack_data["authorization_url"],
            paystack_response=paystack_data,
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        return payment

    @staticmethod
    async def handle_webhook(db: AsyncSession, event: str, data: dict) -> None:
        """
        Process a Paystack webhook event.
        Only charge.success and charge.failure are handled — all other
        event types are acknowledged and ignored.

        On success:
          1. Verify transaction with Paystack API (don't trust the webhook body alone)
          2. Update payment record to succeeded
          3. Call order-service to update order status to 'paid'
          4. Publish payment.succeeded event

        On failure:
          1. Update payment record to failed
          2. Call order-service to update order status to 'cancelled'
          3. Publish payment.failed event
        """
        reference = data.get("reference")
        if not reference:
            logger.warning(f"Webhook {event} has no reference — ignoring")
            return

        # Find the payment record
        result = await db.execute(
            select(Payment).where(Payment.paystack_reference == reference)
        )
        payment = result.scalar_one_or_none()

        if not payment:
            logger.warning(f"No payment found for reference {reference}")
            return

        if event == "charge.success":
            # Re-verify with Paystack rather than trusting the webhook body —
            # this is the security best practice for payment webhooks.
            try:
                verified = await verify_transaction(reference)
                if verified.get("status") != "success":
                    logger.warning(f"Verification returned non-success for {reference}")
                    return
            except PaystackError as e:
                logger.error(f"Verification failed for {reference}: {e}")
                return

            payment.status = PaymentStatus.succeeded
            payment.paystack_response = verified
            await db.commit()

            order_id = str(payment.order_id)
            user_id  = str(payment.user_id)

            await update_order_status(order_id, "paid")
            publish_payment_succeeded(
                order_id=order_id,
                user_id=user_id,
                amount=str(payment.amount),
                reference=reference,
            )
            logger.info(f"Payment succeeded for order {order_id}")

        elif event == "charge.failure":
            payment.status = PaymentStatus.failed
            payment.paystack_response = data
            await db.commit()

            order_id = str(payment.order_id)
            user_id  = str(payment.user_id)

            await update_order_status(order_id, "cancelled")
            publish_payment_failed(
                order_id=order_id,
                user_id=user_id,
                reference=reference,
                reason=data.get("gateway_response", "Payment failed"),
            )
            logger.info(f"Payment failed for order {order_id}")

        else:
            logger.info(f"Unhandled Paystack event type: {event} — acknowledged")

    @staticmethod
    async def get_payment_by_order(db: AsyncSession, order_id: str) -> Payment | None:
        result = await db.execute(
            select(Payment).where(Payment.order_id == uuid.UUID(order_id))
        )
        return result.scalar_one_or_none()
