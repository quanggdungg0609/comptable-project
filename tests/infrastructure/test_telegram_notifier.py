import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.notifications.telegram_notifier import TelegramNotifier


@pytest.fixture
def notifier():
    return TelegramNotifier(
        bot_token="test-token",
        chat_id="-123456",
        app_base_url="http://localhost:8000",
    )


@pytest.mark.asyncio
async def test_notify_new_invoice_calls_telegram_api(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_new_invoice("job-1", "hd001.xml", "Cty ABC", "0001")

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "sendMessage" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert payload["chat_id"] == "-123456"
        assert "hd001.xml" in payload["text"]
        assert "Cty ABC" in payload["text"]
        assert "0001" in payload["text"]
        assert "http://localhost:8000/jobs/job-1/review" in payload["text"]


@pytest.mark.asyncio
async def test_notify_confirmed_calls_telegram_api(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_confirmed("job-1", "hd001.xml", "Cty ABC", "0001")

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert "xác nhận" in payload["text"]
        assert "hd001.xml" in payload["text"]


@pytest.mark.asyncio
async def test_notify_rejected_calls_telegram_api(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_rejected("job-1", "hd001.xml", "Cty ABC", "0001")

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert "từ chối" in payload["text"]


@pytest.mark.asyncio
async def test_telegram_api_error_does_not_raise(notifier):
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        # Không được raise exception
        await notifier.notify_new_invoice("job-1", "hd001.xml", "Cty ABC", "0001")


@pytest.mark.asyncio
async def test_missing_seller_info_shows_fallback(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_new_invoice("job-1", "hd001.xml", "", "")

        payload = mock_client.post.call_args[1]["json"]
        assert "Chưa xác định" in payload["text"]
