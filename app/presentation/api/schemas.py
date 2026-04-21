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
    seller_tax_code: str
    description: str
    price_before_tax: Decimal
    tax_rate: Decimal
    price_after_tax: Decimal

class JobResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    created_at: datetime
    extracted_items: list[InvoiceItemSchema]
    source_paths: list[str]
    error: Optional[str]

class ReviewRequest(BaseModel):
    items: list[InvoiceItemSchema]