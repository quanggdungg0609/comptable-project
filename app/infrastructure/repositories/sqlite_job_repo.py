import json
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
import aiosqlite
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus

class SQLiteJobRepository(IJobRepository):
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def save(self, job: ProcessingJob) -> None:
        await self._db.execute(
            "INSERT INTO jobs (id, filename, file_type, status, created_at, source_paths, pending_pdf_path, duplicate_of, retry_count) VALUES (?,?,?,?,?,?,?,?,?)",
            (job.id, job.filename, job.file_type.value, job.status.value,
             job.created_at.isoformat(), json.dumps(job.source_paths), job.pending_pdf_path, job.duplicate_of, 0),
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
            pending_pdf_path=row["pending_pdf_path"],
            duplicate_of=row["duplicate_of"],
            retry_count=row["retry_count"] if "retry_count" in row.keys() else 0,
        )
        async with self._db.execute(
            "SELECT * FROM invoice_items WHERE job_id = ?", (job_id,)
        ) as cur:
            job.extracted_items = [_row_to_item(r) for r in await cur.fetchall()]
        async with self._db.execute(
            "SELECT * FROM invoice_line_items WHERE job_id = ?", (job_id,)
        ) as cur:
            job.extracted_line_items = [_row_to_line_item(r) for r in await cur.fetchall()]
        return job

    async def list_all(self, status: Optional[InvoiceStatus] = None) -> list[ProcessingJob]:
        # 3 queries total (jobs + items + line_items), no N+1.
        if status:
            jobs_sql = "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC"
            params: tuple = (status.value,)
        else:
            jobs_sql = "SELECT * FROM jobs ORDER BY created_at DESC"
            params = ()

        async with self._db.execute(jobs_sql, params) as cur:
            job_rows = await cur.fetchall()
        if not job_rows:
            return []

        ids = [r["id"] for r in job_rows]
        placeholders = ",".join("?" * len(ids))

        items_by_job: dict[str, list[InvoiceItem]] = {i: [] for i in ids}
        async with self._db.execute(
            f"SELECT * FROM invoice_items WHERE job_id IN ({placeholders})", ids
        ) as cur:
            async for r in cur:
                items_by_job[r["job_id"]].append(_row_to_item(r))

        lines_by_job: dict[str, list[InvoiceLineItem]] = {i: [] for i in ids}
        async with self._db.execute(
            f"SELECT * FROM invoice_line_items WHERE job_id IN ({placeholders})", ids
        ) as cur:
            async for r in cur:
                lines_by_job[r["job_id"]].append(_row_to_line_item(r))

        jobs: list[ProcessingJob] = []
        for row in job_rows:
            job = ProcessingJob(
                id=row["id"], filename=row["filename"],
                file_type=FileType(row["file_type"]),
                status=InvoiceStatus(row["status"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                source_paths=json.loads(row["source_paths"] or "[]"),
                error=row["error"],
                pending_file_path=row["pending_file_path"],
                pending_pdf_path=row["pending_pdf_path"],
                duplicate_of=row["duplicate_of"],
                retry_count=row["retry_count"] if "retry_count" in row.keys() else 0,
            )
            job.extracted_items = items_by_job.get(row["id"], [])
            job.extracted_line_items = lines_by_job.get(row["id"], [])
            jobs.append(job)
        return jobs

    async def update_status(self, job_id: str, status: InvoiceStatus, error: Optional[str] = None) -> None:
        await self._db.execute(
            "UPDATE jobs SET status = ?, error = ? WHERE id = ?",
            (status.value, error, job_id),
        )
        await self._db.commit()

    async def save_items(self, job_id: str, items: list[InvoiceItem]) -> None:
        await self._db.executemany(
            """INSERT INTO invoice_items
               (id, job_id, invoice_symbol, invoice_number, invoice_date, seller_name, seller_address, seller_tax_code, description, price_before_tax, tax_rate, price_after_tax)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
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

    async def update_pending_pdf_path(self, job_id: str, path: str) -> None:
        await self._db.execute("UPDATE jobs SET pending_pdf_path = ? WHERE id = ?", (path, job_id))
        await self._db.commit()

    async def save_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None:
        await self._db.executemany(
            """INSERT INTO invoice_line_items
               (id, job_id, invoice_symbol, invoice_number, invoice_date,
                seller_name, seller_address, seller_tax_code, ten_hang_hoa, don_vi_tinh,
                so_luong, don_gia, thanh_tien, tax_rate, tax_amount)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [_line_item_to_row(job_id, li) for li in items],
        )
        await self._db.commit()

    async def update_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None:
        await self._db.execute("DELETE FROM invoice_line_items WHERE job_id = ?", (job_id,))
        await self._db.commit()
        await self.save_line_items(job_id, items)

    async def get_items_by_month(self, year: int, month: int) -> list[InvoiceItem]:
        prefix = f"{year}-{month:02d}"
        async with self._db.execute(
            """SELECT ii.* FROM invoice_items ii
               JOIN jobs j ON ii.job_id = j.id
               WHERE j.status = 'CONFIRMED'
               AND ii.invoice_date LIKE ?
               ORDER BY ii.invoice_date""",
            (f"{prefix}%",),
        ) as cur:
            return [_row_to_item(r) for r in await cur.fetchall()]

    async def get_line_items_by_month(self, year: int, month: int) -> list[InvoiceLineItem]:
        prefix = f"{year}-{month:02d}"
        async with self._db.execute(
            """SELECT li.* FROM invoice_line_items li
               JOIN jobs j ON li.job_id = j.id
               WHERE j.status = 'CONFIRMED'
               AND li.invoice_date LIKE ?
               ORDER BY li.invoice_date""",
            (f"{prefix}%",),
        ) as cur:
            return [_row_to_line_item(r) for r in await cur.fetchall()]

    async def find_duplicate(
        self,
        invoice_symbol: str,
        invoice_number: str,
        seller_tax_code: str,
        exclude_job_id: Optional[str] = None,
    ) -> Optional[ProcessingJob]:
        query = """SELECT j.id FROM jobs j
               JOIN invoice_items ii ON ii.job_id = j.id
               WHERE ii.invoice_symbol = ?
                 AND ii.invoice_number = ?
                 AND ii.seller_tax_code = ?
                 AND j.status IN ('CONFIRMED', 'AWAITING_REVIEW')"""
        params: list = [invoice_symbol, invoice_number, seller_tax_code]
        if exclude_job_id is not None:
            query += " AND j.id != ?"
            params.append(exclude_job_id)
        query += " LIMIT 1"
        async with self._db.execute(query, params) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return await self.get(row["id"])

    async def list_retryable(self, max_retry_count: int = 3) -> list[ProcessingJob]:
        async with self._db.execute(
            "SELECT * FROM jobs WHERE status = 'FAILED' AND retry_count < ? AND pending_file_path IS NOT NULL ORDER BY created_at ASC",
            (max_retry_count,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            ProcessingJob(
                id=r["id"], filename=r["filename"],
                file_type=FileType(r["file_type"]),
                status=InvoiceStatus(r["status"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                source_paths=json.loads(r["source_paths"] or "[]"),
                error=r["error"],
                pending_file_path=r["pending_file_path"],
                pending_pdf_path=r["pending_pdf_path"],
                duplicate_of=r["duplicate_of"],
                retry_count=r["retry_count"] if "retry_count" in r.keys() else 0,
            )
            for r in rows
        ]

    async def increment_retry_count(self, job_id: str) -> None:
        await self._db.execute(
            "UPDATE jobs SET retry_count = retry_count + 1 WHERE id = ?",
            (job_id,),
        )
        await self._db.commit()

    async def update_duplicate_of(self, job_id: str, duplicate_of_id: str) -> None:
        await self._db.execute(
            "UPDATE jobs SET duplicate_of = ? WHERE id = ?",
            (duplicate_of_id, job_id),
        )
        await self._db.commit()


def _item_to_row(job_id: str, item: InvoiceItem) -> tuple:
    return (
        item.id, job_id, item.invoice_symbol, item.invoice_number,
        item.invoice_date.isoformat(), item.seller_name, item.seller_address, item.seller_tax_code, item.description,
        str(item.price_before_tax), str(item.tax_rate), str(item.price_after_tax),
    )

def _row_to_item(row) -> InvoiceItem:
    return InvoiceItem(
        id=row["id"], invoice_symbol=row["invoice_symbol"], invoice_number=row["invoice_number"],
        invoice_date=date.fromisoformat(row["invoice_date"]),
        seller_name=row["seller_name"], seller_address=row["seller_address"] or "", seller_tax_code=row["seller_tax_code"], description=row["description"],
        price_before_tax=Decimal(row["price_before_tax"]), tax_rate=Decimal(row["tax_rate"]), price_after_tax=Decimal(row["price_after_tax"]),
    )

def _line_item_to_row(job_id: str, li: InvoiceLineItem) -> tuple:
    return (
        li.id, job_id, li.invoice_symbol, li.invoice_number,
        li.invoice_date.isoformat(), li.seller_name, li.seller_address, li.seller_tax_code,
        li.ten_hang_hoa, li.don_vi_tinh,
        str(li.so_luong), str(li.don_gia), str(li.thanh_tien),
        str(li.tax_rate), str(li.tax_amount),
    )

def _row_to_line_item(row) -> InvoiceLineItem:
    return InvoiceLineItem(
        id=row["id"],
        invoice_symbol=row["invoice_symbol"],
        invoice_number=row["invoice_number"],
        invoice_date=date.fromisoformat(row["invoice_date"]),
        seller_name=row["seller_name"],
        seller_address=row["seller_address"] or "",
        seller_tax_code=row["seller_tax_code"],
        ten_hang_hoa=row["ten_hang_hoa"],
        don_vi_tinh=row["don_vi_tinh"],
        so_luong=Decimal(row["so_luong"]),
        don_gia=Decimal(row["don_gia"]),
        thanh_tien=Decimal(row["thanh_tien"]),
        tax_rate=Decimal(row["tax_rate"]),
        tax_amount=Decimal(row["tax_amount"]),
    )