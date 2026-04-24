import logging

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    async def notify_new_invoice(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        logger.info("[Notification] Hóa đơn mới cần xem xét: %s (NCC: %s, Số: %s, job: %s)", filename, seller_name, invoice_number, job_id)

    async def notify_confirmed(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        logger.info("[Notification] Hóa đơn đã xác nhận: %s (NCC: %s, Số: %s, job: %s)", filename, seller_name, invoice_number, job_id)

    async def notify_rejected(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        logger.info("[Notification] Hóa đơn đã từ chối: %s (NCC: %s, Số: %s, job: %s)", filename, seller_name, invoice_number, job_id)
