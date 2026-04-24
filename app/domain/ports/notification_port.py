from abc import ABC, abstractmethod


class INotificationPort(ABC):
    @abstractmethod
    async def notify_new_invoice(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        """Thông báo hóa đơn mới cần xem xét."""

    @abstractmethod
    async def notify_confirmed(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        """Thông báo hóa đơn đã được xác nhận."""

    @abstractmethod
    async def notify_rejected(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        """Thông báo hóa đơn đã bị từ chối."""