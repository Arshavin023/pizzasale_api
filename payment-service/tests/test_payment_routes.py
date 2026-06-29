"""
Route-level tests for payment-service HTTP endpoints.

Paystack API calls, order_client, and event publishers are all mocked.
Webhook signature is computed correctly using the test secret so security
tests prove the real verification logic works.
"""
import json
import uuid
import os
import hmac
import hashlib
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from app.models.payment import Payment, PaymentStatus
from app.utils.paystack import PaystackError

INITIALIZE_URL = "/payments/initialize"
WEBHOOK_URL = "/payments/webhook"
ORDER_URL = "/payments/order"

# Must match the actual PAYSTACK_SECRET_KEY the container uses —
# webhook.py reads it at import time so we can't override it in tests.
TEST_SECRET = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_paystack_secret_for_testing")


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _sign(body: bytes) -> str:
    return hmac.new(
        TEST_SECRET.encode("utf-8"),
        body,
        hashlib.sha512,
    ).hexdigest()


def _webhook_body(event: str, reference: str, **extra) -> bytes:
    payload = {"event": event, "data": {"reference": reference, **extra}}
    return json.dumps(payload).encode()


def _paystack_init_data(reference: str = "PIZZA-ROUTE123") -> dict:
    return {
        "authorization_url": "https://checkout.paystack.com/test",
        "access_code": "test_access",
        "reference": reference,
    }


# ── POST /payments/initialize ─────────────────────────────────────

@pytest.mark.asyncio
class TestInitializePayment:

    def _payload(self, **overrides):
        base = {
            "order_id": str(new_uuid()),
            "user_id":  str(new_uuid()),
            "email":    "test@example.com",
            "amount":   "14.99",
        }
        return {**base, **overrides}

    async def test_initialize_returns_201(self, client, db):
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.return_value = _paystack_init_data()
            resp = await client.post(INITIALIZE_URL, json=self._payload())

        assert resp.status_code == 201

    async def test_initialize_returns_authorization_url(self, client, db):
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.return_value = _paystack_init_data()
            resp = await client.post(INITIALIZE_URL, json=self._payload())

        data = resp.json()
        assert data["authorization_url"] == "https://checkout.paystack.com/test"
        assert data["status"] == "pending"

    async def test_initialize_returns_reference(self, client, db):
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.return_value = _paystack_init_data("PIZZA-MYREF")
            resp = await client.post(INITIALIZE_URL, json=self._payload())

        assert resp.json()["reference"] == "PIZZA-MYREF"

    async def test_initialize_missing_email_422(self, client, db):
        payload = self._payload()
        del payload["email"]
        resp = await client.post(INITIALIZE_URL, json=payload)
        assert resp.status_code == 422

    async def test_initialize_missing_amount_422(self, client, db):
        payload = self._payload()
        del payload["amount"]
        resp = await client.post(INITIALIZE_URL, json=payload)
        assert resp.status_code == 422

    async def test_initialize_paystack_error_returns_502(self, client, db):
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.side_effect = PaystackError("Invalid Email Address")
            resp = await client.post(INITIALIZE_URL, json=self._payload())

        assert resp.status_code == 502
        assert "Invalid Email Address" in resp.json()["detail"]


# ── POST /payments/webhook — security ────────────────────────────

@pytest.mark.asyncio
class TestWebhookSecurity:

    async def test_webhook_without_signature_returns_401(self, client, db):
        body = _webhook_body("charge.success", "PIZZA-TEST")
        resp = await client.post(
            WEBHOOK_URL,
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    async def test_webhook_with_wrong_signature_returns_401(self, client, db):
        body = _webhook_body("charge.success", "PIZZA-TEST")
        resp = await client.post(
            WEBHOOK_URL,
            content=body,
            headers={
                "Content-Type": "application/json",
                "x-paystack-signature": "wrong_signature_entirely",
            },
        )
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    async def test_webhook_with_correct_signature_returns_200(self, client, db):
        body = _webhook_body("transfer.success", "PIZZA-TEST")
        sig = _sign(body)
        resp = await client.post(
            WEBHOOK_URL,
            content=body,
            headers={
                "Content-Type": "application/json",
                "x-paystack-signature": sig,
            },
        )
        assert resp.status_code == 200

    async def test_tampered_body_with_original_signature_returns_401(self, client, db):
        """Changing even one byte of the body must invalidate the signature."""
        original_body = _webhook_body("charge.success", "PIZZA-TEST")
        sig = _sign(original_body)

        # Tamper: change amount in the body
        tampered_body = original_body.replace(b"charge.success", b"charge.failure")

        resp = await client.post(
            WEBHOOK_URL,
            content=tampered_body,
            headers={
                "Content-Type": "application/json",
                "x-paystack-signature": sig,
            },
        )
        assert resp.status_code == 401


# ── POST /payments/webhook — processing ──────────────────────────

@pytest.mark.asyncio
class TestWebhookProcessing:

    async def _seed_payment(self, db, reference: str) -> Payment:
        payment = Payment(
            order_id=new_uuid(),
            user_id=new_uuid(),
            amount=Decimal("14.99"),
            currency="NGN",
            status=PaymentStatus.pending,
            paystack_reference=reference,
            authorization_url="https://checkout.paystack.com/test",
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        return payment

    async def _post_webhook(self, client, body: bytes) -> object:
        sig = _sign(body)
        return await client.post(
            WEBHOOK_URL,
            content=body,
            headers={
                "Content-Type": "application/json",
                "x-paystack-signature": sig,
            },
        )

    async def test_charge_success_updates_payment_to_succeeded(self, client, db):
        payment = await self._seed_payment(db, "PIZZA-SUCC")
        body = _webhook_body("charge.success", "PIZZA-SUCC")

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_succeeded"):
            mock_verify.return_value = {"status": "success", "reference": "PIZZA-SUCC"}
            resp = await self._post_webhook(client, body)

        assert resp.status_code == 200
        await db.refresh(payment)
        assert payment.status == PaymentStatus.succeeded

    async def test_charge_failure_updates_payment_to_failed(self, client, db):
        payment = await self._seed_payment(db, "PIZZA-FAIL")
        body = _webhook_body("charge.failure", "PIZZA-FAIL",
                             gateway_response="Declined")

        with patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_failed"):
            resp = await self._post_webhook(client, body)

        assert resp.status_code == 200
        await db.refresh(payment)
        assert payment.status == PaymentStatus.failed

    async def test_unknown_event_returns_200_and_is_ignored(self, client, db):
        """Paystack expects 200 even for events we don't handle."""
        body = _webhook_body("subscription.create", "PIZZA-SUB")
        resp = await self._post_webhook(client, body)
        assert resp.status_code == 200

    async def test_webhook_always_returns_200_even_on_internal_error(self, client, db):
        """
        Paystack retries on non-200 responses. We must return 200 even
        if processing fails internally — the payment record was already
        written, and retry would duplicate the action.
        """
        body = _webhook_body("charge.success", "PIZZA-INTERNAL-ERR")
        sig = _sign(body)

        with patch("app.services.payment_service.PaymentService.handle_webhook",
                   new_callable=AsyncMock) as mock_handle:
            mock_handle.side_effect = Exception("unexpected internal error")

            resp = await client.post(
                WEBHOOK_URL,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "x-paystack-signature": sig,
                },
            )

        assert resp.status_code == 200


# ── GET /payments/order/{order_id} ───────────────────────────────

@pytest.mark.asyncio
class TestGetPaymentByOrder:

    async def test_returns_200_for_existing_payment(self, client, db):
        order_id = new_uuid()
        payment = Payment(
            order_id=order_id,
            user_id=new_uuid(),
            amount=Decimal("14.99"),
            currency="NGN",
            status=PaymentStatus.pending,
            paystack_reference="PIZZA-GET123",
        )
        db.add(payment)
        await db.commit()

        resp = await client.get(f"{ORDER_URL}/{order_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_returns_404_for_missing_order(self, client, db):
        resp = await client.get(f"{ORDER_URL}/{new_uuid()}")
        assert resp.status_code == 404


# ── GET /health ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}