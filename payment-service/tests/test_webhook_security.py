"""
Unit tests for webhook signature verification (app/utils/webhook.py).

These test the verify_webhook_signature function directly — no HTTP layer,
no DB, just the cryptographic verification logic itself.
"""
import os
import hmac
import hashlib
import pytest

from app.utils.webhook import verify_webhook_signature

# Must match the actual PAYSTACK_SECRET_KEY the container uses.
TEST_SECRET = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_paystack_secret_for_testing")


def _sign(body: bytes, secret: str = TEST_SECRET) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha512,
    ).hexdigest()


class TestVerifyWebhookSignature:

    def test_valid_signature_returns_true(self):
        body = b'{"event":"charge.success","data":{"reference":"PIZZA-123"}}'
        sig = _sign(body)
        assert verify_webhook_signature(body, sig) is True

    def test_wrong_signature_returns_false(self):
        body = b'{"event":"charge.success","data":{"reference":"PIZZA-123"}}'
        assert verify_webhook_signature(body, "wrong_signature") is False

    def test_tampered_body_returns_false(self):
        body = b'{"event":"charge.success","data":{"reference":"PIZZA-123"}}'
        sig = _sign(body)
        tampered = b'{"event":"charge.failure","data":{"reference":"PIZZA-123"}}'
        assert verify_webhook_signature(tampered, sig) is False

    def test_empty_body_with_correct_signature_returns_true(self):
        body = b""
        sig = _sign(body)
        assert verify_webhook_signature(body, sig) is True

    def test_empty_signature_returns_false(self):
        body = b'{"event":"charge.success"}'
        assert verify_webhook_signature(body, "") is False

    def test_signature_from_different_secret_returns_false(self):
        body = b'{"event":"charge.success","data":{"reference":"PIZZA-123"}}'
        wrong_sig = _sign(body, "sk_test_different_secret")
        assert verify_webhook_signature(body, wrong_sig) is False

    def test_is_constant_time_comparison(self):
        """
        verify_webhook_signature must use hmac.compare_digest, not ==,
        to prevent timing attacks. We test that the function handles
        signatures of different lengths without raising.
        """
        body = b'{"event":"charge.success"}'
        # These would raise ValueError with == comparison on some implementations
        assert verify_webhook_signature(body, "short") is False
        assert verify_webhook_signature(body, "a" * 128) is False

    def test_whitespace_change_in_body_invalidates_signature(self):
        """Even a single extra space changes the HMAC."""
        body = b'{"event":"charge.success"}'
        sig = _sign(body)
        body_with_space = b'{"event": "charge.success"}'
        assert verify_webhook_signature(body_with_space, sig) is False