import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db, get_session_factory
from app.schemas.payment_schema import (
    InitializePaymentRequest,
    InitializePaymentResponse,
    PaymentResponse,
)
from app.services.payment_service import PaymentService
from app.utils.paystack import PaystackError
from app.utils.webhook import verify_webhook_signature

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/initialize", response_model=InitializePaymentResponse, status_code=201)
async def initialize_payment(
    data: InitializePaymentRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by order-service at checkout to initialize a Paystack transaction.
    Returns the authorization_url to redirect the user to Paystack's payment page.
    """
    try:
        payment = await PaymentService.initialize(
            db=db,
            order_id=str(data.order_id),
            user_id=str(data.user_id),
            email=data.email,
            amount_ngn=data.amount,
        )
    except PaystackError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return InitializePaymentResponse(
        payment_id=payment.id,
        order_id=payment.order_id,
        authorization_url=payment.authorization_url,
        reference=payment.paystack_reference,
        amount=payment.amount,
        currency=payment.currency,
        status=payment.status,
    )


async def _process_webhook_in_background(event: str, data: dict) -> None:
    """
    Runs after the HTTP response has already been sent to Paystack.

    This is the structurally correct fix for webhook handling: Paystack
    times out each delivery attempt after 30 seconds and will treat a slow
    or failed response as a delivery failure, retrying the whole webhook
    (live: every 3 min for 4 tries, then hourly for 72h; test: hourly for
    10h). By acknowledging immediately with 200 right after signature
    verification, we decouple "Paystack got our acknowledgment" from "we
    finished updating order-service" — the retry-with-backoff against
    order-service can now take as long as it genuinely needs (within
    reason) without risking Paystack re-delivering the same webhook and
    causing duplicate processing.

    Opens its own DB session via get_session_factory() since the
    request-scoped session from Depends(get_db) is closed by the time
    this runs. Using the factory function (not a direct import) means
    tests can monkeypatch get_session_factory() to point at the test
    database instead of production.
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            await PaymentService.handle_webhook(db, event, data)
        except Exception as e:
            logger.error(f"Background webhook processing error for event {event}: {e}")


@router.post("/webhook", status_code=200)
async def paystack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_paystack_signature: Optional[str] = Header(default=None),
):
    """
    Paystack webhook receiver. Paystack sends charge.success or charge.failure
    events here after a payment attempt.

    Security: we verify the HMAC-SHA512 signature on every request before
    accepting it — unauthenticated/forged requests are rejected with 401
    and are NOT queued for background processing.

    Once the signature is verified and the payload is valid JSON, we
    acknowledge with 200 immediately and hand off the actual processing
    (Paystack re-verification, DB updates, retry-to-order-service, event
    publishing) to a background task. This keeps our response time
    independent of how long downstream calls take.
    """
    raw_body = await request.body()

    if not x_paystack_signature:
        logger.warning("Webhook received without signature header — rejecting")
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    if not verify_webhook_signature(raw_body, x_paystack_signature):
        logger.warning("Webhook signature verification failed — possible forgery")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event")
    data = payload.get("data", {})

    logger.info(f"Received and verified Paystack webhook: {event} — queuing for background processing")

    background_tasks.add_task(_process_webhook_in_background, event, data)

    return {"status": "ok"}


@router.get("/order/{order_id}", response_model=PaymentResponse)
async def get_payment_by_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get payment record for a given order."""
    payment = await PaymentService.get_payment_by_order(db, order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found for this order")
    return payment