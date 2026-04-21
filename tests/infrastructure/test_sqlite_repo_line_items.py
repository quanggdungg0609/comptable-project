import pytest
import aiosqlite
from decimal import Decimal
from datetime import date
from app.domain.entities.processing_job import ProcessingJob
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.value_objects.file_type import FileType
from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository
from app.core.database import (
    CREATE_JOBS_TABLE, CREATE_INVOICE_ITEMS_TABLE, CREATE_INVOICE_LINE_ITEMS_TABLE
)

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

def make_line_item(**kwargs):
    defaults = dict(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", ten_hang_hoa="Thép tấm 10mm",
        don_vi_tinh="Kg", so_luong=Decimal("298"), don_gia=Decimal("28000"),
        thanh_tien=Decimal("8344000"), tax_rate=Decimal("0.10"),
        tax_amount=Decimal("834400"),
    )
    defaults.update(kwargs)
    return InvoiceLineItem(**defaults)

async def test_save_and_get_line_items(repo):
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job)
    li = make_line_item()
    await repo.save_line_items(job.id, [li])
    fetched = await repo.get(job.id)
    assert len(fetched.extracted_line_items) == 1
    assert fetched.extracted_line_items[0].ten_hang_hoa == "Thép tấm 10mm"
    assert fetched.extracted_line_items[0].so_luong == Decimal("298")

async def test_update_line_items_replaces_all(repo):
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job)
    await repo.save_line_items(job.id, [make_line_item(ten_hang_hoa="A")])
    await repo.update_line_items(job.id, [make_line_item(ten_hang_hoa="B"), make_line_item(ten_hang_hoa="C")])
    fetched = await repo.get(job.id)
    assert len(fetched.extracted_line_items) == 2
    names = {li.ten_hang_hoa for li in fetched.extracted_line_items}
    assert names == {"B", "C"}
