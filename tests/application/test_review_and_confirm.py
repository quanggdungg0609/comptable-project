import pytest
from unittest.mock import AsyncMock
from decimal import Decimal
from datetime import date
from app.application.use_cases.review_and_confirm import ReviewAndConfirmUseCase
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus

def make_job_with_items():
    job = ProcessingJob.create("hd049.xml", FileType.XML)
    job.status = InvoiceStatus.AWAITING_REVIEW
    job.extracted_items = [InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )]
    job.extracted_line_items = []
    return job

@pytest.mark.asyncio
async def test_confirm_job_sets_confirmed_status(tmp_path):
    repo = AsyncMock()
    repo.find_duplicate = AsyncMock(return_value=None)
    storage = AsyncMock()
    excel = AsyncMock()
    excel_detail = AsyncMock()
    excel.append_rows.return_value = ("Bang_ke_thue_2026_03.xlsx", b"xlsx_bytes")
    excel_detail.append_rows.return_value = ("Chi_tiet_hoa_don_T3_2026.xlsx", b"detail_bytes")
    storage.download_file.return_value = b""
    job = make_job_with_items()
    pending = tmp_path / f"{job.id}.xml"
    pending.write_bytes(b"<HDon/>")
    job.pending_file_path = str(pending)
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices="invoices", bucket_exports="exports",
    )
    result = await uc.confirm(
        job_id=job.id,
        updated_items=job.extracted_items,
        updated_line_items=[],
    )

    assert result.status == InvoiceStatus.CONFIRMED
    storage.upload_file.assert_called()
    excel.append_rows.assert_called_once()

@pytest.mark.asyncio
async def test_reject_job_sets_rejected_status():
    repo = AsyncMock()
    repo.find_duplicate = AsyncMock(return_value=None)
    job = make_job_with_items()
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(
        repo=repo, storage=AsyncMock(), excel=AsyncMock(), excel_detail=AsyncMock(),
        bucket_invoices="i", bucket_exports="e",
    )
    result = await uc.reject(job_id=job.id)
    assert result.status == InvoiceStatus.REJECTED
    repo.update_status.assert_called_with(job.id, InvoiceStatus.REJECTED)