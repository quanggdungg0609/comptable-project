from pydantic import BaseModel
from decimal import Decimal
from datetime import date, datetime
from typing import Optional

class InvoiceItemSchema(BaseModel):
    id: str
    invoice_symbol: str
    invoice_number: str
    invoice_date: date
    seller_name: str
    seller_address: str = ""
    seller_tax_code: str
    description: str
    price_before_tax: Decimal
    tax_rate: Decimal
    price_after_tax: Decimal

class InvoiceLineItemSchema(BaseModel):
    id: str
    invoice_symbol: str
    invoice_number: str
    invoice_date: date
    seller_name: str
    seller_address: str = ""
    seller_tax_code: str
    ten_hang_hoa: str
    don_vi_tinh: str
    so_luong: Decimal
    don_gia: Decimal
    thanh_tien: Decimal
    tax_rate: Decimal
    tax_amount: Decimal

class JobResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    created_at: datetime
    extracted_items: list[InvoiceItemSchema]
    extracted_line_items: list[InvoiceLineItemSchema]
    source_paths: list[str]
    error: Optional[str]

class ReviewRequest(BaseModel):
    items: list[InvoiceItemSchema]