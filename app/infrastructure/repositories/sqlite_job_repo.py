import json
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
import aiosqlite
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus

class SQLiteJobRepository(IJobRepository):
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def save(self, job: ProcessingJob) -> None:
        await self._db.execute(
            "INSERT INTO jobs (id, filename, file_type, status, created_at, source_paths) VALUES (?,?,?,?,?,?)",
            (job.id, job.filename, job.file_type.value, job.status.value,
             job.created_at.isoformat(), json.dumps(job.source_paths)),
        )
        await self._db.commit()

    async def get(self, job_id: str) -> Optional[ProcessingJob]:
        async with self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        job = ProcessingJob(
            id=row["id"], filename=row["filename"],
            file_type=FileType(row["file_type"]),
            status=InvoiceStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            source_paths=json.loads(row["source_paths"] or "[]"),
            error=row["error"],
            pending_file_path=row["pending_file_path"],
        )
        async with self._db.execute(
            "SELECT * FROM invoice_items WHERE job_id = ?", (job_id,)
        ) as cur:
            job.extracted_items = [_row_to_item(r) for r in await cur.fetchall()]
        return job

    async def list_all(self, status: Optional[InvoiceStatus] = None) -> list[ProcessingJob]:
        if status:
            async with self._db.execute(
                "SELECT id FROM jobs WHERE status = ? ORDER BY created_at DESC", (status.value,)
            ) as cur:
                ids = [r["id"] for r in await cur.fetchall()]
        else:
            async with self._db.execute("SELECT id FROM jobs ORDER BY created_at DESC") as cur:
                ids = [r["id"] for r in await cur.fetchall()]
        return [j for j_id in ids if (j := await self.get(j_id)) is not None]

    async def update_status(self, job_id: str, status: InvoiceStatus, error: Optional[str] = None) -> None:
        await self._db.execute(
            "UPDATE jobs SET status = ?, error = ? WHERE id = ?",
            (status.value, error, job_id),
        )
        await self._db.commit()

    async def save_items(self, job_id: str, items: list[InvoiceItem]) -> None:
        await self._db.executemany(
            """INSERT INTO invoice_items
               (id, job_id, invoice_symbol, invoice_number, invoice_date, seller_name, seller_tax_code, description, price_before_tax, tax_rate, price_after_tax)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [_item_to_row(job_id, i) for i in items],
        )
        await self._db.commit()

    async def update_items(self, job_id: str, items: list[InvoiceItem]) -> None:
        await self._db.execute("DELETE FROM invoice_items WHERE job_id = ?", (job_id,))
        await self._db.commit()
        await self.save_items(job_id, items)

    async def add_source_path(self, job_id: str, path: str) -> None:
        async with self._db.execute("SELECT source_paths FROM jobs WHERE id = ?", (job_id,)) as cur:
            row = await cur.fetchone()
        paths = json.loads(row["source_paths"] or "[]")
        paths.append(path)
        await self._db.execute("UPDATE jobs SET source_paths = ? WHERE id = ?", (json.dumps(paths), job_id))
        await self._db.commit()

    async def update_pending_file_path(self, job_id: str, path: str) -> None:
        await self._db.execute("UPDATE jobs SET pending_file_path = ? WHERE id = ?", (path, job_id))
        await self._db.commit()


def _item_to_row(job_id: str, item: InvoiceItem) -> tuple:
    return (
        item.id, job_id, item.invoice_symbol, item.invoice_number,
        item.invoice_date.isoformat(), item.seller_name, item.seller_tax_code, item.description,
        str(item.price_before_tax), str(item.tax_rate), str(item.price_after_tax),
    )

def _row_to_item(row) -> InvoiceItem:
    return InvoiceItem(
        id=row["id"], invoice_symbol=row["invoice_symbol"], invoice_number=row["invoice_number"],
        invoice_date=date.fromisoformat(row["invoice_date"]),
        seller_name=row["seller_name"], seller_tax_code=row["seller_tax_code"], description=row["description"],
        price_before_tax=Decimal(row["price_before_tax"]), tax_rate=Decimal(row["tax_rate"]), price_after_tax=Decimal(row["price_after_tax"]),
    )