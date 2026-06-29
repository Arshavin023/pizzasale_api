"""
Unit tests for PaymentService.

initialize_transaction, verify_transaction, update_order_status, and
event publishers are all mocked — no real Paystack API or RabbitMQ needed.
"""
import uuid
import pytest
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.payment import Payment, PaymentStatus
from app.services.payment_service import PaymentService
from app.utils.paystack import PaystackError


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _str_uuid() -> str:
    return str(uuid.uuid4())


def _paystack_init_response(reference: str = "PIZZA-ABC123") -> dict:
    return {
        "authorization_url": "https://checkout.paystack.com/test123",
        "access_code": "test_access_code",
        "reference": reference,
    }


def _paystack_verify_response(status: str = "success") -> dict:
    return {
        "status": status,
        "reference": "PIZZA-ABC123",
        "amount": 1499,
        "currency": "NGN",
        "gateway_response": "Approved",
    }


# ── initialize ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPaymentServiceInitialize:

    async def test_creates_pending_payment_record(self, db):
        order_id = _str_uuid()
        user_id = _str_uuid()

        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.return_value = _paystack_init_response()

            payment = await PaymentService.initialize(
                db=db,
                order_id=order_id,
                user_id=user_id,
                email="test@example.com",
                amount_ngn=Decimal("14.99"),
            )

        assert payment.status == PaymentStatus.pending
        assert str(payment.order_id) == order_id
        assert str(payment.user_id) == user_id
        assert payment.amount == Decimal("14.99")
        assert payment.currency == "NGN"

    async def test_stores_paystack_reference(self, db):
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.return_value = _paystack_init_response("PIZZA-XYZ999")

            payment = await PaymentService.initialize(
                db=db,
                order_id=_str_uuid(),
                user_id=_str_uuid(),
                email="test@example.com",
                amount_ngn=Decimal("14.99"),
            )

        assert payment.paystack_reference == "PIZZA-XYZ999"

    async def test_stores_authorization_url(self, db):
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.return_value = _paystack_init_response()

            payment = await PaymentService.initialize(
                db=db,
                order_id=_str_uuid(),
                user_id=_str_uuid(),
                email="test@example.com",
                amount_ngn=Decimal("14.99"),
            )

        assert payment.authorization_url == "https://checkout.paystack.com/test123"

    async def test_raises_paystack_error_on_api_failure(self, db):
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.side_effect = PaystackError("Invalid Email Address")

            with pytest.raises(PaystackError):
                await PaymentService.initialize(
                    db=db,
                    order_id=_str_uuid(),
                    user_id=_str_uuid(),
                    email="bad-email",
                    amount_ngn=Decimal("14.99"),
                )

    async def test_does_not_persist_on_paystack_failure(self, db):
        from sqlalchemy.future import select
        with patch("app.services.payment_service.initialize_transaction",
                   new_callable=AsyncMock) as mock_init:
            mock_init.side_effect = PaystackError("API error")

            with pytest.raises(PaystackError):
                await PaymentService.initialize(
                    db=db,
                    order_id=_str_uuid(),
                    user_id=_str_uuid(),
                    email="test@example.com",
                    amount_ngn=Decimal("14.99"),
                )

        result = await db.execute(select(Payment))
        assert result.scalars().all() == []


# ── handle_webhook — charge.success ──────────────────────────────

@pytest.mark.asyncio
class TestHandleWebhookSuccess:

    async def _seed_payment(self, db, reference: str = "PIZZA-TEST123") -> Payment:
        payment = Payment(
            order_id=_uuid(),
            user_id=_uuid(),
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

    async def test_updates_payment_status_to_succeeded(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_succeeded"):
            mock_verify.return_value = _paystack_verify_response("success")

            await PaymentService.handle_webhook(
                db, "charge.success", {"reference": payment.paystack_reference}
            )

        await db.refresh(payment)
        assert payment.status == PaymentStatus.succeeded

    async def test_re_verifies_with_paystack_api(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_succeeded"):
            mock_verify.return_value = _paystack_verify_response("success")

            await PaymentService.handle_webhook(
                db, "charge.success", {"reference": payment.paystack_reference}
            )

        mock_verify.assert_called_once_with(payment.paystack_reference)

    async def test_calls_order_service_with_paid_status(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock) as mock_update, \
             patch("app.services.payment_service.publish_payment_succeeded"):
            mock_verify.return_value = _paystack_verify_response("success")

            await PaymentService.handle_webhook(
                db, "charge.success", {"reference": payment.paystack_reference}
            )

        mock_update.assert_called_once_with(str(payment.order_id), "paid")

    async def test_publishes_payment_succeeded_event(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_succeeded") as mock_pub:
            mock_verify.return_value = _paystack_verify_response("success")

            await PaymentService.handle_webhook(
                db, "charge.success", {"reference": payment.paystack_reference}
            )

        mock_pub.assert_called_once()

    async def test_does_not_update_if_verification_returns_non_success(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock) as mock_update, \
             patch("app.services.payment_service.publish_payment_succeeded"):
            mock_verify.return_value = _paystack_verify_response("failed")

            await PaymentService.handle_webhook(
                db, "charge.success", {"reference": payment.paystack_reference}
            )

        await db.refresh(payment)
        assert payment.status == PaymentStatus.pending
        mock_update.assert_not_called()

    async def test_does_not_update_if_verification_raises(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock) as mock_update:
            mock_verify.side_effect = PaystackError("API timeout")

            await PaymentService.handle_webhook(
                db, "charge.success", {"reference": payment.paystack_reference}
            )

        await db.refresh(payment)
        assert payment.status == PaymentStatus.pending
        mock_update.assert_not_called()

    async def test_ignores_unknown_reference(self, db):
        # Should not raise — just log and return
        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify:
            await PaymentService.handle_webhook(
                db, "charge.success", {"reference": "UNKNOWN-REF-999"}
            )

        mock_verify.assert_not_called()

    async def test_ignores_missing_reference(self, db):
        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify:
            await PaymentService.handle_webhook(db, "charge.success", {})

        mock_verify.assert_not_called()


# ── handle_webhook — charge.failure ──────────────────────────────

@pytest.mark.asyncio
class TestHandleWebhookFailure:

    async def _seed_payment(self, db, reference: str = "PIZZA-FAIL123") -> Payment:
        payment = Payment(
            order_id=_uuid(),
            user_id=_uuid(),
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

    async def test_updates_payment_status_to_failed(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_failed"):
            await PaymentService.handle_webhook(
                db, "charge.failure",
                {"reference": payment.paystack_reference,
                 "gateway_response": "Declined"}
            )

        await db.refresh(payment)
        assert payment.status == PaymentStatus.failed

    async def test_calls_order_service_with_cancelled_status(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock) as mock_update, \
             patch("app.services.payment_service.publish_payment_failed"):
            await PaymentService.handle_webhook(
                db, "charge.failure",
                {"reference": payment.paystack_reference}
            )

        mock_update.assert_called_once_with(str(payment.order_id), "cancelled")

    async def test_publishes_payment_failed_event(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_failed") as mock_pub:
            await PaymentService.handle_webhook(
                db, "charge.failure",
                {"reference": payment.paystack_reference,
                 "gateway_response": "Insufficient funds"}
            )

        mock_pub.assert_called_once()

    async def test_does_not_call_verify_on_failure(self, db):
        payment = await self._seed_payment(db)

        with patch("app.services.payment_service.verify_transaction",
                   new_callable=AsyncMock) as mock_verify, \
             patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock), \
             patch("app.services.payment_service.publish_payment_failed"):
            await PaymentService.handle_webhook(
                db, "charge.failure",
                {"reference": payment.paystack_reference}
            )

        mock_verify.assert_not_called()


# ── handle_webhook — unhandled events ────────────────────────────

@pytest.mark.asyncio
class TestHandleWebhookUnhandledEvents:

    async def test_ignores_unknown_event_types(self, db):
        with patch("app.services.payment_service.update_order_status",
                   new_callable=AsyncMock) as mock_update:
            await PaymentService.handle_webhook(
                db, "transfer.success", {"reference": "REF123"}
            )

        mock_update.assert_not_called()


# ── get_payment_by_order ──────────────────────────────────────────

@pytest.mark.asyncio
class TestGetPaymentByOrder:

    async def test_returns_payment_for_existing_order(self, db):
        order_id = _uuid()
        payment = Payment(
            order_id=order_id,
            user_id=_uuid(),
            amount=Decimal("14.99"),
            currency="NGN",
            status=PaymentStatus.pending,
            paystack_reference="PIZZA-LOOKUP123",
        )
        db.add(payment)
        await db.commit()

        result = await PaymentService.get_payment_by_order(db, str(order_id))
        assert result is not None
        assert result.paystack_reference == "PIZZA-LOOKUP123"

    async def test_returns_none_for_unknown_order(self, db):
        result = await PaymentService.get_payment_by_order(db, str(_uuid()))
        assert result is None
