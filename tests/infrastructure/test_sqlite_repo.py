import pytest
import aiosqlite
from decimal import Decimal
from datetime import date, datetime
from app.domain.entities.processing_job import ProcessingJob
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository
from app.core.database import CREATE_JOBS_TABLE, CREATE_INVOICE_ITEMS_TABLE, CREATE_INVOICE_LINE_ITEMS_TABLE

@pytest.fixture
async def repo():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute(CREATE_JOBS_TABLE)
    await db.execute(CREATE_INVOICE_ITEMS_TABLE)
    await db.execute(CREATE_INVOICE_LINE_ITEMS_TABLE)
    await db.commit()
    yield SQLiteJobRepository(db)
    await db.close()

async def test_save_and_get_job(repo):
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job)
    fetched = await repo.get(job.id)
    assert fetched is not None
    assert fetched.filename == "hd001.xml"
    assert fetched.status == InvoiceStatus.PENDING

async def test_update_status(repo):
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job)
    await repo.update_status(job.id, InvoiceStatus.PROCESSING)
    fetched = await repo.get(job.id)
    assert fetched.status == InvoiceStatus.PROCESSING

async def test_save_and_get_items(repo):
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job)
    item = InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_address="123 Missing St", seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )
    await repo.save_items(job.id, [item])
    fetched = await repo.get(job.id)
    assert len(fetched.extracted_items) == 1
    assert fetched.extracted_items[0].invoice_number == "49"

async def test_list_all_with_status_filter(repo):
    job1 = ProcessingJob.create("hd001.xml", FileType.XML)
    job2 = ProcessingJob.create("hd002.pdf", FileType.PDF)
    await repo.save(job1)
    await repo.save(job2)
    await repo.update_status(job1.id, InvoiceStatus.CONFIRMED)
    confirmed = await repo.list_all(status=InvoiceStatus.CONFIRMED)
    assert len(confirmed) == 1
    assert confirmed[0].id == job1.id


async def test_find_duplicate_returns_confirmed_match(repo):
    # Job gốc đã CONFIRMED
    job1 = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job1)
    item1 = InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_address="123 Missing St", seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )
    await repo.save_items(job1.id, [item1])
    await repo.update_status(job1.id, InvoiceStatus.CONFIRMED)

    result = await repo.find_duplicate("1C26TAA", "49", "0901212659")
    assert result is not None
    assert result.id == job1.id


async def test_find_duplicate_returns_awaiting_review_match(repo):
    job1 = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job1)
    item1 = InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_address="123 Missing St", seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )
    await repo.save_items(job1.id, [item1])
    await repo.update_status(job1.id, InvoiceStatus.AWAITING_REVIEW)

    result = await repo.find_duplicate("1C26TAA", "49", "0901212659")
    assert result is not None
    assert result.id == job1.id


async def test_find_duplicate_ignores_non_matching_statuses(repo):
    for status in [InvoiceStatus.FAILED, InvoiceStatus.REJECTED, InvoiceStatus.PENDING,
                   InvoiceStatus.PROCESSING, InvoiceStatus.CONFIRMING, InvoiceStatus.DUPLICATE]:
        job = ProcessingJob.create("hd001.xml", FileType.XML)
        await repo.save(job)
        item = InvoiceItem(
            invoice_symbol="1C26TAA", invoice_number="49",
            invoice_date=date(2026, 3, 12), seller_address="123 Missing St", seller_name="Cty XYZ",
            seller_tax_code="0901212659", description="Mua vật tư",
            price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
            price_after_tax=Decimal("2903000"),
        )
        await repo.save_items(job.id, [item])
        await repo.update_status(job.id, status)

    result = await repo.find_duplicate("1C26TAA", "49", "0901212659")
    assert result is None


async def test_find_duplicate_returns_none_when_no_match(repo):
    result = await repo.find_duplicate("NOTEXIST", "999", "0000000000")
    assert result is None


async def test_update_duplicate_of(repo):
    job1 = ProcessingJob.create("hd001.xml", FileType.XML)
    job2 = ProcessingJob.create("hd001_copy.xml", FileType.XML)
    await repo.save(job1)
    await repo.save(job2)

    await repo.update_duplicate_of(job2.id, job1.id)

    fetched = await repo.get(job2.id)
    assert fetched.duplicate_of == job1.id


async def test_find_duplicate_excludes_job_id(repo):
    job1 = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job1)
    item1 = InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_address="123 Missing St", seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )
    await repo.save_items(job1.id, [item1])
    await repo.update_status(job1.id, InvoiceStatus.CONFIRMED)

    # Without exclusion: finds job1
    result = await repo.find_duplicate("1C26TAA", "49", "0901212659")
    assert result is not None
    assert result.id == job1.id

    # With exclusion: ignores job1, returns None
    result_excluded = await repo.find_duplicate("1C26TAA", "49", "0901212659", exclude_job_id=job1.id)
    assert result_excluded is None
