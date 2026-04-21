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
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
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