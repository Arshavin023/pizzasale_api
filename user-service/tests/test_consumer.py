"""
Unit tests for the RabbitMQ consumer (_process_message).
No real broker needed — we call the async function directly and mock the DB.
"""
import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


async def _call(body: bytes) -> bool:
    """Import here so env vars are set by conftest first."""
    from app.workers.consumer import _process_message
    return await _process_message(body)


# ── _process_message ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestProcessMessage:

    def _valid_body(self, user_id=None) -> bytes:
        return json.dumps({
            "event": "user.registered",
            "user_id": user_id or str(uuid.uuid4()),
            "email": "uche@example.com",
            "username": "uche",
        }).encode()

    @patch("app.workers.consumer.UserProfileService.create_profile_from_event", new_callable=AsyncMock)
    @patch("app.workers.consumer.AsyncSessionLocal")
    async def test_valid_message_acked(self, mock_session_cls, mock_create):
        mock_create.return_value = True
        # AsyncSessionLocal used as async context manager
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        result = await _call(self._valid_body())
        assert result is True

    @patch("app.workers.consumer.UserProfileService.create_profile_from_event", new_callable=AsyncMock)
    @patch("app.workers.consumer.AsyncSessionLocal")
    async def test_duplicate_event_still_acked(self, mock_session_cls, mock_create):
        """Duplicate (idempotent) events must be acked — not requeued."""
        mock_create.return_value = False
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        result = await _call(self._valid_body())
        assert result is True

    async def test_malformed_json_acked_not_requeued(self):
        """Unparseable body can never succeed on retry — drop it (ack)."""
        result = await _call(b"this is not json {{{")
        assert result is True

    async def test_missing_user_id_acked(self):
        body = json.dumps({"email": "uche@example.com", "username": "uche"}).encode()
        result = await _call(body)
        assert result is True

    async def test_missing_email_acked(self):
        body = json.dumps({"user_id": str(uuid.uuid4()), "username": "uche"}).encode()
        result = await _call(body)
        assert result is True

    async def test_missing_username_acked(self):
        body = json.dumps({"user_id": str(uuid.uuid4()), "email": "x@x.com"}).encode()
        result = await _call(body)
        assert result is True

    async def test_empty_body_acked(self):
        result = await _call(b"")
        assert result is True

    @patch("app.workers.consumer.UserProfileService.create_profile_from_event", new_callable=AsyncMock)
    @patch("app.workers.consumer.AsyncSessionLocal")
    async def test_db_transient_error_nacked(self, mock_session_cls, mock_create):
        """Transient DB failure → nack so RabbitMQ redelivers."""
        mock_create.side_effect = Exception("DB connection refused")
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        result = await _call(self._valid_body())
        assert result is False

    @patch("app.workers.consumer.UserProfileService.create_profile_from_event", new_callable=AsyncMock)
    @patch("app.workers.consumer.AsyncSessionLocal")
    async def test_create_called_with_correct_args(self, mock_session_cls, mock_create):
        mock_create.return_value = True
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        uid = str(uuid.uuid4())
        await _call(json.dumps({
            "user_id": uid, "email": "uche@example.com", "username": "uche"
        }).encode())

        mock_create.assert_called_once_with(
            mock_session, user_id=uid, email="uche@example.com", username="uche"
        )
