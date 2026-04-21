import json
from datetime import date
from decimal import Decimal
import uuid
import httpx
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.ports.llm_port import ILLMPort

EXTRACTION_PROMPT = """Trích xuất hóa đơn điện tử Việt Nam. Nhóm các dòng theo TSuat (thuế suất).

Dữ liệu:
{content}

Phân loại mô tả thành một trong: vật tư | nhiên liệu | hàng hóa/dịch vụ | điện nước | tiếp khách ăn uống

Trả về JSON (một item per mức thuế suất, cộng dồn ThTien và TThue):
{{"items":[{{"invoice_symbol":"KHHDon","invoice_number":"SHDon","invoice_date":"DD/MM/YYYY","seller_name":"NBan.Ten","seller_tax_code":"NBan.MST","description":"loại mặt hàng","price_before_tax":0,"tax_rate":0.08,"price_after_tax":0}}]}}"""


LlamaCppClient = None  # kept for import compatibility

class OllamaLLMClient(ILLMPort):
    def __init__(self, base_url: str, model: str):
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def extract_invoice(self, content: str) -> list[InvoiceItem]:
        prompt = EXTRACTION_PROMPT.format(content=content)
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "think": False,
                    "options": {"num_ctx": 4096, "num_predict": 512},
                },
            )
            resp.raise_for_status()
        raw = resp.json()["message"]["content"]
        data = json.loads(raw)
        return [_parse_item(i) for i in data.get("items", [])]


def _parse_item(d: dict) -> InvoiceItem:
    invoice_date_raw = d.get("invoice_date", "")
    try:
        # Handle DD/MM/YYYY format as specified in prompt
        parts = invoice_date_raw.split("/")
        if len(parts) == 3:
            day, month, year = map(int, parts)
            invoice_date = date(year, month, day)
        else:
            invoice_date = date.fromisoformat(invoice_date_raw)
    except (ValueError, TypeError, AttributeError):
        invoice_date = date.today()
    return InvoiceItem(
        id=str(uuid.uuid4()) if "id" not in d else d["id"], # Added UUID if not present
        invoice_symbol=str(d.get("invoice_symbol", "")),
        invoice_number=str(d.get("invoice_number", "")),
        invoice_date=invoice_date,
        seller_name=str(d.get("seller_name", "")),
        seller_tax_code=str(d.get("seller_tax_code", "")),
        description=str(d.get("description", "")),
        price_before_tax=Decimal(str(d.get("price_before_tax", 0))),
        tax_rate=Decimal(str(d.get("tax_rate", 0))),
        price_after_tax=Decimal(str(d.get("price_after_tax", 0))),
    )