import json
from datetime import date
from decimal import Decimal
import uuid
import httpx
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.ports.llm_port import ILLMPort

EXTRACTION_PROMPT = """Phân tích hóa đơn điện tử Việt Nam sau đây và trích xuất thông tin chi tiết.

Nội dung hóa đơn:
{content}

Hướng dẫn:
- Hóa đơn có thể chứa NHIỀU dòng hàng hóa/dịch vụ (STT 1, 2, 3,...)
- Nhóm các dòng cùng mức thuế suất (TSuat) vào một phần tử
- Cộng dồn ThTien (cước suất/giá tiền) và VATAmount (thuế) theo từng mức thuế
- Trích xuất từ TTChung: KHHDon (ký hiệu), SHDon (số hóa đơn), NLap (ngày)
- Người bán từ NBan: Ten, MST
- Mô tả từ THHDVu của từng dòng; tổng hợp lại xem các dòng đó thuộc loại hàng hóa gì trong các loại mặt hàng sau đây:
    + vật tư
    + nhiên liệu
    + hàng hóa/dịch vụ
    + điện nước
    + Tiếp khách, ăn uống
- Nếu một dòng có SLuong=0, bỏ qua nó (dòng chỉ mục)

Trả về JSON với cấu trúc sau (một phần tử per mức thuế suất):
{{
  "items": [
    {{
      "invoice_symbol": "ký hiệu hóa đơn (vd: C26TAA)",
      "invoice_number": "số hóa đơn",
      "invoice_date": "DD/MM/YYYY",
      "seller_name": "tên người bán",
      "seller_tax_code": "mã số thuế người bán",
      "description": "mô tả hàng hóa (loại mặt hàng)",
      "price_before_tax": "giá trước thuế (vd: 445000000)",
      "tax_rate": "thuế suất (vd: 0.08)",
      "price_after_tax": "giá sau thuế (vd: 35600000)"
    }}
  ]
}}

Chỉ trả về JSON thuần túy, không có markdown hay giải thích. Giá trị số là số nguyên hoặc số thập phân."""


class OllamaLLMClient(ILLMPort):
    def __init__(self, base_url: str, model: str):
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def extract_invoice(self, content: str) -> list[InvoiceItem]:
        prompt = EXTRACTION_PROMPT.format(content=content)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
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