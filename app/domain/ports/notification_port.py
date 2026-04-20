from abc import ABC, abstractmethod

class INotificationPort(ABC):
    @abstractmethod
    async def notify_new_invoice(self, job_id: str, filename: str) -> None:
        """Notify staff that a new invoice is awaiting review."""