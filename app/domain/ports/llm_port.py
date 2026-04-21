from abc import ABC, abstractmethod
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem

class ILLMPort(ABC):
    @abstractmethod
    async def extract_invoice(self, content: str) -> tuple[list[InvoiceItem], list[InvoiceLineItem]]: ...
