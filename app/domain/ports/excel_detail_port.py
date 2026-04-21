from abc import ABC, abstractmethod
from app.domain.entities.invoice_line_item import InvoiceLineItem

class IExcelDetailPort(ABC):
    @abstractmethod
    async def append_rows(
        self,
        items: list[InvoiceLineItem],
        year: int,
        month: int,
        existing_data: bytes,
    ) -> tuple[str, bytes]: ...
