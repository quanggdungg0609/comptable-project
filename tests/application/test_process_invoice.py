import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import date
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.domain.value_objects.file_type import FileType

def make_item():
    return InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_address="123 Nguyen Hue St", seller_tax_code="0901212659",
        description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )

@pytest.fixture
def use_case():
    repo = AsyncMock()
    llm = AsyncMock()
    notification = AsyncMock()
    llm.extract_invoice.return_value = ([make_item()], [])
    repo.find_duplicate = AsyncMock(return_value=None)
    return ProcessInvoiceUseCase(repo=repo, llm=llm, notification=notification), repo, llm, notification

async def test_xml_file_creates_job_awaiting_review(use_case):
    uc, repo, llm, notification = use_case
    job = await uc.execute(
        filename="hd049.xml",
        file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        paired_pdf=None,
    )
    assert job.status == InvoiceStatus.AWAITING_REVIEW
    assert len(job.extracted_items) == 1
    repo.save.assert_called_once()
    repo.save_items.assert_called_once()
    notification.notify_new_invoice.assert_called_once_with(
        job.id, "hd049.xml", "Cty XYZ", "49"
    )

async def test_pdf_only_file_creates_job_awaiting_review(use_case):
    uc, repo, llm, notification = use_case
    job = await uc.execute(
        filename="hd049.pdf",
        file_data=b"%PDF-1.4",  # minimal placeholder
        paired_pdf=None,
    )
    assert job.file_type == FileType.PDF

async def test_notification_failure_does_not_fail_job(use_case):
    uc, repo, llm, notification = use_case
    notification.notify_new_invoice.side_effect = Exception("Telegram timeout")
    job = await uc.execute(
        filename="hd049.xml",
        file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        paired_pdf=None,
    )
    # Job still succeeds even when notification fails
    assert job.status == InvoiceStatus.AWAITING_REVIEW

async def test_llm_failure_sets_failed_status(use_case):
    uc, repo, llm, notification = use_case
    llm.extract_invoice.side_effect = Exception("LLM timeout")
    job = await uc.execute(
        filename="hd049.xml",
        file_data=b"<HDon/>",
        paired_pdf=None,
    )
    assert job.status == InvoiceStatus.FAILED
    assert "LLM timeout" in job.error


async def test_duplicate_job_sets_duplicate_status(use_case):
    uc, repo, llm, notification = use_case
    existing_job = ProcessingJob.create("hd049_original.xml", FileType.XML)
    existing_job.status = InvoiceStatus.CONFIRMED
    repo.find_duplicate = AsyncMock(return_value=existing_job)

    job = await uc.execute(
        filename="hd049_copy.xml",
        file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        paired_pdf=None,
    )

    assert job.status == InvoiceStatus.DUPLICATE
    assert job.duplicate_of == existing_job.id


async def test_duplicate_job_does_not_notify(use_case):
    uc, repo, llm, notification = use_case
    existing_job = ProcessingJob.create("hd049_original.xml", FileType.XML)
    existing_job.status = InvoiceStatus.CONFIRMED
    repo.find_duplicate = AsyncMock(return_value=existing_job)

    await uc.execute(
        filename="hd049_copy.xml",
        file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        paired_pdf=None,
    )

    notification.notify_new_invoice.assert_not_called()


async def test_non_duplicate_job_still_notifies(use_case):
    uc, repo, llm, notification = use_case
    repo.find_duplicate = AsyncMock(return_value=None)

    job = await uc.execute(
        filename="hd049.xml",
        file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        paired_pdf=None,
    )

    assert job.status == InvoiceStatus.AWAITING_REVIEW
    notification.notify_new_invoice.assert_called_once()


async def test_find_duplicate_exception_does_not_fail_job(use_case):
    uc, repo, llm, notification = use_case
    repo.find_duplicate = AsyncMock(side_effect=Exception("DB error"))

    job = await uc.execute(
        filename="hd049.xml",
        file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        paired_pdf=None,
    )

    assert job.status == InvoiceStatus.AWAITING_REVIEW