import pytest
from decimal import Decimal
from datetime import date, datetime
from uuid import UUID
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus

def test_invoice_item_creation():
    item = InvoiceItem(
        invoice_symbol="1C26TAA",
        invoice_number="49",
        invoice_date=date(2026, 3, 12),
        seller_name="Công ty TNHH XYZ",
        seller_tax_code="0901212659",
        description="Mua vật tư",
        price_before_tax=Decimal("29030000"),
        tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )
    assert item.invoice_number == "49"
    assert item.tax_rate == Decimal("0.10")

def test_processing_job_default_status():
    job = ProcessingJob.create(filename="hd001.xml", file_type=FileType.XML)
    assert job.status == InvoiceStatus.PENDING
    assert isinstance(job.id, str)
    assert job.extracted_items == []
    assert job.error is None

def test_processing_job_id_is_uuid():
    job = ProcessingJob.create(filename="hd001.pdf", file_type=FileType.PDF)
    UUID(job.id)  # raises ValueError if not valid UUID