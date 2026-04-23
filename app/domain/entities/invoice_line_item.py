from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
import uuid


@dataclass
class InvoiceLineItem:
    invoice_symbol: str
    invoice_number: str
    invoice_date: date
    seller_name: str
    seller_address: str
    seller_tax_code: str
    ten_hang_hoa: str
    don_vi_tinh: str
    so_luong: Decimal
    don_gia: Decimal
    thanh_tien: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
