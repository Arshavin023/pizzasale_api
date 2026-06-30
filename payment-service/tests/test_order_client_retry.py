"""
Unit tests for update_order_status retry-with-backoff logic.

httpx.AsyncClient.patch is mocked to simulate transient failures, permanent
failures, and eventual success after retries — no real order-service needed.
asyncio.sleep is also mocked so tests run instantly instead of waiting
through the real backoff delays.
"""
import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from app.utils.order_client import update_order_status, MAX_RETRIES


def _mock_response(status_code: int, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.mark.asyncio
class TestUpdateOrderStatusSuccess:

    async def test_succeeds_on_first_attempt(self):
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_patch.return_value = _mock_response(200)

            result = await update_order_status("order-123", "paid")

        assert result is True
        assert mock_patch.call_count == 1
        mock_sleep.assert_not_called()

    async def test_calls_correct_endpoint_and_payload(self):
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_patch.return_value = _mock_response(200)

            await update_order_status("order-456", "cancelled")

        call_args = mock_patch.call_args
        assert "order-456/status" in call_args[0][0]
        assert call_args[1]["json"] == {"status": "cancelled"}


@pytest.mark.asyncio
class TestUpdateOrderStatusRetry:

    async def test_succeeds_after_one_transient_failure(self):
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # First call: 500 error. Second call: success.
            mock_patch.side_effect = [
                _mock_response(500, "Internal Server Error"),
                _mock_response(200),
            ]

            result = await update_order_status("order-789", "paid")

        assert result is True
        assert mock_patch.call_count == 2
        mock_sleep.assert_called_once()

    async def test_succeeds_after_two_transient_failures(self):
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_patch.side_effect = [
                _mock_response(503, "Service Unavailable"),
                _mock_response(500, "Internal Server Error"),
                _mock_response(200),
            ]

            result = await update_order_status("order-abc", "paid")

        assert result is True
        assert mock_patch.call_count == 3
        assert mock_sleep.call_count == 2

    async def test_retries_use_exponential_backoff(self):
        from app.utils.order_client import BASE_DELAY_SECONDS

        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_patch.side_effect = [
                _mock_response(500),
                _mock_response(500),
                _mock_response(200),
            ]

            await update_order_status("order-xyz", "paid")

        delays = [call[0][0] for call in mock_sleep.call_args_list]
        # Exponential: BASE_DELAY_SECONDS × 2^0, then × 2^1
        expected = [BASE_DELAY_SECONDS, BASE_DELAY_SECONDS * 2]
        assert delays == expected

    async def test_recovers_from_network_error(self):
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_patch.side_effect = [
                httpx.ConnectError("Connection refused"),
                _mock_response(200),
            ]

            result = await update_order_status("order-net", "paid")

        assert result is True
        assert mock_patch.call_count == 2


@pytest.mark.asyncio
class TestUpdateOrderStatusExhaustedRetries:

    async def test_returns_false_after_max_retries_all_failing(self):
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_patch.return_value = _mock_response(500, "Internal Server Error")

            result = await update_order_status("order-fail", "paid")

        assert result is False
        assert mock_patch.call_count == MAX_RETRIES

    async def test_returns_false_when_order_service_always_unreachable(self):
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_patch.side_effect = httpx.ConnectError("Connection refused")

            result = await update_order_status("order-unreachable", "paid")

        assert result is False
        assert mock_patch.call_count == MAX_RETRIES

    async def test_does_not_retry_beyond_max_retries(self):
        """Even if every attempt fails, we must not retry forever."""
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_patch.return_value = _mock_response(500)

            await update_order_status("order-cap", "paid")

        # MAX_RETRIES attempts, MAX_RETRIES - 1 sleeps between them
        assert mock_patch.call_count == MAX_RETRIES
        assert mock_sleep.call_count == MAX_RETRIES - 1

    async def test_logs_critical_on_exhausted_retries(self, caplog):
        import logging
        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_patch.return_value = _mock_response(500, "boom")

            with caplog.at_level(logging.ERROR):
                await update_order_status("order-critical", "paid")

        assert any("CRITICAL" in record.message for record in caplog.records)