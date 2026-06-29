import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
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


@router.post("/webhook", status_code=200)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_paystack_signature: Optional[str] = Header(default=None),
):
    """
    Paystack webhook receiver. Paystack sends charge.success or charge.failure
    events here after a payment attempt.

    Security: we verify the HMAC-SHA512 signature on every request before
    processing — unauthenticated requests are rejected with 401.
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
    data  = payload.get("data", {})

    logger.info(f"Received Paystack webhook: {event}")

    # Process asynchronously — Paystack expects a fast 200 response.
    # If processing fails internally, we still return 200 to prevent
    # Paystack from retrying with the same payload repeatedly.
    try:
        await PaymentService.handle_webhook(db, event, data)
    except Exception as e:
        logger.error(f"Webhook processing error for event {event}: {e}")

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
