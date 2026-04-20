from abc import ABC, abstractmethod
from app.domain.entities.invoice_item import InvoiceItem

class ILLMPort(ABC):
    @abstractmethod
    async def extract_invoice(self, content: str) -> list[InvoiceItem]:
        """Extract invoice fields from text content. Returns one item per tax-rate group."""