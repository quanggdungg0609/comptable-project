from abc import ABC, abstractmethod
from app.domain.entities.invoice_item import InvoiceItem

class IExcelPort(ABC):
    @abstractmethod
    async def append_rows(self, items: list[InvoiceItem], year: int, month: int) -> bytes:
        """Append items to monthly XLS and return the updated file as bytes."""