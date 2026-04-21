import logging
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.ports.llm_port import ILLMPort

logger = logging.getLogger(__name__)


class FallbackLLMClient(ILLMPort):
    """Try primary LLM first; on any error, fall back to secondary."""

    def __init__(self, primary: ILLMPort, secondary: ILLMPort):
        self._primary = primary
        self._secondary = secondary

    async def extract_invoice(self, content: str) -> tuple[list[InvoiceItem], list[InvoiceLineItem]]:
        try:
            return await self._primary.extract_invoice(content)
        except Exception as exc:
            logger.warning("Primary LLM failed (%s), falling back to secondary", exc)
            return await self._secondary.extract_invoice(content)
