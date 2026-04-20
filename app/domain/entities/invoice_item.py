from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
import uuid

@dataclass
class InvoiceItem:
    invoice_symbol: str # Ký hiệu hóa đơn
    invoice_number: str # Số hóa đơn
    invoice_date: date # Ngày lập hóa đơn
    seller_name: str # Tên đơn vị bán hàng
    seller_tax_code: str # Mã số thuế
    description: str # Diễn giải
    price_before_tax: Decimal # Giá trước thuế
    tax_rate: Decimal # Thuế suất
    price_after_tax: Decimal # Giá sau thuế
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    