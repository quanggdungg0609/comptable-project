import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from datetime import date
from app.application.use_cases.review_and_confirm import ReviewAndConfirmUseCase
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus

def make_item():
    return InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("8344000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("834400"),
    )

def make_line_item():
    return InvoiceLineItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", ten_hang_hoa="Thép tấm",
        don_vi_tinh="Kg", so_luong=Decimal("298"), don_gia=Decimal("28000"),
        thanh_tien=Decimal("8344000"), tax_rate=Decimal("0.10"),
        tax_amount=Decimal("834400"),
    )

@pytest.fixture
def use_case():
    repo = AsyncMock()
    repo.find_duplicate = AsyncMock(return_value=None)
    storage = AsyncMock()
    excel = AsyncMock()
    excel_detail = AsyncMock()

    job = ProcessingJob(
        id="job-1", filename="hd049.xml", file_type=FileType.XML,
        status=InvoiceStatus.AWAITING_REVIEW,
        created_at=__import__("datetime").datetime.now(),
        pending_file_path=None,
    )
    repo.get.return_value = job
    storage.download_file.side_effect = Exception("not found")
    excel.append_rows.return_value = ("Bang_ke_thue_2026_03.xlsx", b"xls-bytes")
    excel_detail.append_rows.return_value = ("Chi_tiet_hoa_don_T3_2026.xlsx", b"detail-bytes")

    uc = ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices="invoices", bucket_exports="exports",
    )
    return uc, repo, storage, excel, excel_detail

@pytest.mark.asyncio
async def test_confirm_calls_detail_writer(use_case):
    uc, repo, storage, excel, excel_detail = use_case
    line_items = [make_line_item()]
    await uc.confirm(job_id="job-1", updated_items=[make_item()], updated_line_items=line_items)
    excel_detail.append_rows.assert_called_once()
    call_args = excel_detail.append_rows.call_args[0]
    assert call_args[0] == line_items  # items passed correctly

@pytest.mark.asyncio
async def test_confirm_uploads_detail_excel(use_case):
    uc, repo, storage, excel, excel_detail = use_case
    await uc.confirm(job_id="job-1", updated_items=[make_item()], updated_line_items=[make_line_item()])
    upload_calls = storage.upload_file.call_args_list
    uploaded_keys = [c[0][1] for c in upload_calls]
    assert any("Chi_tiet" in k for k in uploaded_keys)
