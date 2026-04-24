import logging
import httpx
from app.domain.ports.notification_port import INotificationPort

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier(INotificationPort):
    def __init__(self, bot_token: str, chat_id: str, app_base_url: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._app_base_url = app_base_url.rstrip("/")

    async def notify_new_invoice(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        seller = seller_name or "Chưa xác định"
        number = invoice_number or "Chưa xác định"
        text = (
            "📄 <b>Hóa đơn mới cần xem xét</b>\n\n"
            f"📁 File: {filename}\n"
            f"🏢 Nhà cung cấp: {seller}\n"
            f"🔢 Số hóa đơn: {number}\n"
            f"🔗 Xem xét: {self._app_base_url}/jobs/{job_id}/review"
        )
        await self._send(text)

    async def notify_confirmed(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        seller = seller_name or "Chưa xác định"
        number = invoice_number or "Chưa xác định"
        text = (
            "✅ <b>Hóa đơn đã được xác nhận</b>\n\n"
            f"📁 File: {filename}\n"
            f"🏢 Nhà cung cấp: {seller}\n"
            f"🔢 Số hóa đơn: {number}"
        )
        await self._send(text)

    async def notify_rejected(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        seller = seller_name or "Chưa xác định"
        number = invoice_number or "Chưa xác định"
        text = (
            "❌ <b>Hóa đơn đã bị từ chối</b>\n\n"
            f"📁 File: {filename}\n"
            f"🏢 Nhà cung cấp: {seller}\n"
            f"🔢 Số hóa đơn: {number}"
        )
        await self._send(text)

    async def _send(self, text: str) -> None:
        url = _TELEGRAM_API.format(token=self._bot_token)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                })
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("[TelegramNotifier] Gửi thông báo thất bại: %s", type(exc).__name__)
