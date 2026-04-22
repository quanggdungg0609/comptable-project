# Duplicate Invoice Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Tự động phát hiện và đánh dấu hóa đơn trùng lặp sau khi extract, ngăn chặn confirm trùng lặp vào dữ liệu export.

**Architecture:** Sau khi `ProcessInvoiceUseCase` extract và lưu `invoice_items`, query DB tìm job khác có cùng `(invoice_symbol, invoice_number, seller_tax_code)` với status `CONFIRMED` hoặc `AWAITING_REVIEW`. Nếu tìm thấy, job mới được đánh dấu `DUPLICATE` và lưu `duplicate_of`. Trang review hiển thị cảnh báo và chặn confirm.

**Tech Stack:** Python, aiosqlite, FastAPI, Jinja2, pytest-asyncio

---

## File Map

| File | Thay đổi |
|------|---------|
| `app/domain/value_objects/invoice_status.py` | Thêm `DUPLICATE` vào enum |
| `app/domain/entities/processing_job.py` | Thêm field `duplicate_of: Optional[str]` |
| `app/domain/ports/job_repository.py` | Thêm 2 abstract method mới |
| `app/core/database.py` | Thêm cột `duplicate_of` vào DDL + migration |
| `app/infrastructure/repositories/sqlite_job_repo.py` | Implement `find_duplicate`, `update_duplicate_of`, cập nhật `save`/`get` |
| `app/application/use_cases/process_invoice.py` | Thêm duplicate check sau `save_items` |
| `app/presentation/web/templates/jobs.html` | Thêm badge "Trùng lặp" màu cam |
| `app/presentation/web/templates/review.html` | Banner cảnh báo + ẩn nút Confirm |
| `app/presentation/web/router.py` | Guard 400 ở `/confirm` endpoint |
| `tests/infrastructure/test_sqlite_repo.py` | Tests cho `find_duplicate` |
| `tests/application/test_process_invoice.py` | Tests duplicate detection trong use case |
| `tests/presentation/test_web_router.py` | Test guard confirm |

---

## Task 1: Domain — Thêm `DUPLICATE` status và `duplicate_of` field

**Files:**
- Modify: `app/domain/value_objects/invoice_status.py`
- Modify: `app/domain/entities/processing_job.py`

- [x] **Step 1: Thêm DUPLICATE vào InvoiceStatus**

Mở `app/domain/value_objects/invoice_status.py`, thêm dòng sau `FAILED`:

```python
from enum import Enum

class InvoiceStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    CONFIRMED = "CONFIRMED"
    CONFIRMING = "CONFIRMING"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
```

- [x] **Step 2: Thêm `duplicate_of` vào ProcessingJob**

Mở `app/domain/entities/processing_job.py`, thêm field `duplicate_of`:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus


@dataclass
class ProcessingJob:
    id: str
    filename: str
    file_type: FileType
    status: InvoiceStatus
    created_at: datetime
    extracted_items: list[InvoiceItem] = field(default_factory=list)
    extracted_line_items: list[InvoiceLineItem] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    error: Optional[str] = None
    pending_file_path: Optional[str] = None
    duplicate_of: Optional[str] = None

    @classmethod
    def create(cls, filename: str, file_type: FileType) -> "ProcessingJob":
        return cls(
            id=str(uuid.uuid4()),
            filename=filename,
            file_type=file_type,
            status=InvoiceStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
```

- [x] **Step 3: Commit**

```bash
git add app/domain/value_objects/invoice_status.py app/domain/entities/processing_job.py
git commit -m "feat: add DUPLICATE status and duplicate_of field to domain"
```

---

## Task 2: Domain Port — Thêm 2 abstract method vào `IJobRepository`

**Files:**
- Modify: `app/domain/ports/job_repository.py`

- [x] **Step 1: Thêm `find_duplicate` và `update_duplicate_of`**

Mở `app/domain/ports/job_repository.py`, thêm 2 method ở cuối class:

```python
from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.value_objects.invoice_status import InvoiceStatus

class IJobRepository(ABC):
    @abstractmethod
    async def save(self, job: ProcessingJob) -> None: ...

    @abstractmethod
    async def get(self, job_id: str) -> Optional[ProcessingJob]: ...

    @abstractmethod
    async def list_all(self, status: Optional[InvoiceStatus] = None) -> list[ProcessingJob]: ...

    @abstractmethod
    async def update_status(self, job_id: str, status: InvoiceStatus, error: Optional[str] = None) -> None: ...

    @abstractmethod
    async def save_items(self, job_id: str, items: list[InvoiceItem]) -> None: ...

    @abstractmethod
    async def update_items(self, job_id: str, items: list[InvoiceItem]) -> None: ...

    @abstractmethod
    async def add_source_path(self, job_id: str, path: str) -> None: ...

    @abstractmethod
    async def update_pending_file_path(self, job_id: str, path: str) -> None: ...

    @abstractmethod
    async def save_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None: ...

    @abstractmethod
    async def update_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None: ...

    @abstractmethod
    async def get_items_by_month(self, year: int, month: int) -> list[InvoiceItem]: ...

    @abstractmethod
    async def get_line_items_by_month(self, year: int, month: int) -> list[InvoiceLineItem]: ...

    @abstractmethod
    async def find_duplicate(
        self,
        invoice_symbol: str,
        invoice_number: str,
        seller_tax_code: str,
    ) -> Optional[ProcessingJob]: ...

    @abstractmethod
    async def update_duplicate_of(self, job_id: str, duplicate_of_id: str) -> None: ...
```

- [x] **Step 2: Commit**

```bash
git add app/domain/ports/job_repository.py
git commit -m "feat: add find_duplicate and update_duplicate_of to IJobRepository"
```

---

## Task 3: Database — Thêm cột `duplicate_of` vào schema

**Files:**
- Modify: `app/core/database.py`

- [x] **Step 1: Thêm cột vào DDL và thêm migration**

Mở `app/core/database.py`, cập nhật `CREATE_JOBS_TABLE` để thêm cột `duplicate_of`, và thêm migration statement trong `init_db`:

```python
import aiosqlite
from pathlib import Path
from app.core.config import get_settings

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    error TEXT,
    source_paths TEXT DEFAULT '[]',
    pending_file_path TEXT,
    duplicate_of TEXT
)
"""

CREATE_INVOICE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    invoice_symbol TEXT DEFAULT '',
    invoice_number TEXT DEFAULT '',
    invoice_date TEXT DEFAULT '',
    seller_name TEXT DEFAULT '',
    seller_tax_code TEXT DEFAULT '',
    description TEXT DEFAULT '',
    price_before_tax TEXT DEFAULT '0',
    tax_rate TEXT DEFAULT '0',
    price_after_tax TEXT DEFAULT '0'
)
"""

CREATE_INVOICE_LINE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_line_items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    invoice_symbol TEXT DEFAULT '',
    invoice_number TEXT DEFAULT '',
    invoice_date TEXT DEFAULT '',
    seller_name TEXT DEFAULT '',
    seller_tax_code TEXT DEFAULT '',
    ten_hang_hoa TEXT DEFAULT '',
    don_vi_tinh TEXT DEFAULT '',
    so_luong TEXT DEFAULT '0',
    don_gia TEXT DEFAULT '0',
    thanh_tien TEXT DEFAULT '0',
    tax_rate TEXT DEFAULT '0',
    tax_amount TEXT DEFAULT '0'
)
"""

_db_connection: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db_connection
    if _db_connection is None:
        settings = get_settings()
        Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
        _db_connection = await aiosqlite.connect(settings.database_path)
        _db_connection.row_factory = aiosqlite.Row
    return _db_connection

async def close_db() -> None:
    global _db_connection
    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None

async def init_db() -> None:
    db = await get_db()
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute(CREATE_JOBS_TABLE)
    await db.execute(CREATE_INVOICE_ITEMS_TABLE)
    await db.execute(CREATE_INVOICE_LINE_ITEMS_TABLE)
    # Migration: add duplicate_of column if it doesn't exist yet
    await db.execute(
        "ALTER TABLE jobs ADD COLUMN duplicate_of TEXT"
    )
    await db.commit()
```

> **Lưu ý:** `ALTER TABLE ... ADD COLUMN` trên SQLite sẽ raise error nếu cột đã tồn tại. Bước tiếp theo sẽ bọc trong try/except để xử lý.

- [x] **Step 2: Bọc migration trong try/except**

Sửa lại phần migration trong `init_db`:

```python
async def init_db() -> None:
    db = await get_db()
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute(CREATE_JOBS_TABLE)
    await db.execute(CREATE_INVOICE_ITEMS_TABLE)
    await db.execute(CREATE_INVOICE_LINE_ITEMS_TABLE)
    try:
        await db.execute("ALTER TABLE jobs ADD COLUMN duplicate_of TEXT")
    except Exception:
        pass  # column already exists
    await db.commit()
```

- [x] **Step 3: Commit**

```bash
git add app/core/database.py
git commit -m "feat: add duplicate_of column to jobs table with migration"
```

---

## Task 4: Infrastructure — Implement `find_duplicate` và `update_duplicate_of` trong SQLiteJobRepository

**Files:**
- Modify: `app/infrastructure/repositories/sqlite_job_repo.py`
- Test: `tests/infrastructure/test_sqlite_repo.py`

- [x] **Step 1: Viết failing tests**

Mở `tests/infrastructure/test_sqlite_repo.py`, thêm vào cuối file:

```python
async def test_find_duplicate_returns_confirmed_match(repo):
    # Job gốc đã CONFIRMED
    job1 = ProcessingJob.create("hd001.xml", FileType.XML)
    await repo.save(job1)
    item1 = InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
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
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )
    await repo.save_items(job1.id, [item1])
    await repo.update_status(job1.id, InvoiceStatus.AWAITING_REVIEW)

    result = await repo.find_duplicate("1C26TAA", "49", "0901212659")
    assert result is not None
    assert result.id == job1.id


async def test_find_duplicate_ignores_failed_and_rejected(repo):
    for status in [InvoiceStatus.FAILED, InvoiceStatus.REJECTED]:
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
```

- [x] **Step 2: Chạy test để xác nhận FAIL**

```bash
cd /Users/quangdung/Documents/collect_invoice
pytest tests/infrastructure/test_sqlite_repo.py::test_find_duplicate_returns_confirmed_match -v
```

Expected: `FAILED` với `AttributeError: 'SQLiteJobRepository' object has no attribute 'find_duplicate'`

- [x] **Step 3: Implement trong SQLiteJobRepository**

Mở `app/infrastructure/repositories/sqlite_job_repo.py`.

Cập nhật method `save` để thêm `duplicate_of`:

```python
async def save(self, job: ProcessingJob) -> None:
    await self._db.execute(
        "INSERT INTO jobs (id, filename, file_type, status, created_at, source_paths, duplicate_of) VALUES (?,?,?,?,?,?,?)",
        (job.id, job.filename, job.file_type.value, job.status.value,
         job.created_at.isoformat(), json.dumps(job.source_paths), job.duplicate_of),
    )
    await self._db.commit()
```

Cập nhật method `get` để đọc `duplicate_of`:

```python
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
        duplicate_of=row["duplicate_of"],
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
```

Thêm 2 method mới vào cuối class (trước các helper functions):

```python
async def find_duplicate(
    self,
    invoice_symbol: str,
    invoice_number: str,
    seller_tax_code: str,
) -> Optional[ProcessingJob]:
    async with self._db.execute(
        """SELECT DISTINCT j.id FROM jobs j
           JOIN invoice_items ii ON ii.job_id = j.id
           WHERE ii.invoice_symbol = ?
             AND ii.invoice_number = ?
             AND ii.seller_tax_code = ?
             AND j.status IN ('CONFIRMED', 'AWAITING_REVIEW')
           LIMIT 1""",
        (invoice_symbol, invoice_number, seller_tax_code),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return await self.get(row["id"])

async def update_duplicate_of(self, job_id: str, duplicate_of_id: str) -> None:
    await self._db.execute(
        "UPDATE jobs SET duplicate_of = ? WHERE id = ?",
        (duplicate_of_id, job_id),
    )
    await self._db.commit()
```

- [x] **Step 4: Chạy tất cả tests infrastructure**

```bash
pytest tests/infrastructure/test_sqlite_repo.py -v
```

Expected: tất cả PASS bao gồm 5 tests mới.

- [x] **Step 5: Commit**

```bash
git add app/infrastructure/repositories/sqlite_job_repo.py tests/infrastructure/test_sqlite_repo.py
git commit -m "feat: implement find_duplicate and update_duplicate_of in SQLiteJobRepository"
```

---

## Task 5: Application — Thêm duplicate check vào `ProcessInvoiceUseCase`

**Files:**
- Modify: `app/application/use_cases/process_invoice.py`
- Test: `tests/application/test_process_invoice.py`

- [x] **Step 1: Cập nhật fixture và viết failing tests**

Mở `tests/application/test_process_invoice.py`.

**1a.** Cập nhật fixture `use_case` để `find_duplicate` trả về `None` mặc định — không làm vậy thì `AsyncMock()` tự trả về mock truthy khiến mọi test cũ đều trigger duplicate path:

```python
@pytest.fixture
def use_case():
    repo = AsyncMock()
    llm = AsyncMock()
    notification = AsyncMock()
    llm.extract_invoice.return_value = ([make_item()], [])
    repo.find_duplicate = AsyncMock(return_value=None)
    return ProcessInvoiceUseCase(repo=repo, llm=llm, notification=notification), repo, llm, notification
```

**1b.** Thêm 4 test mới vào cuối file:

```python
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
```

Thêm import cần thiết ở đầu file test (sau các import hiện tại):

```python
from app.domain.entities.processing_job import ProcessingJob
from app.domain.value_objects.file_type import FileType
```

- [x] **Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/application/test_process_invoice.py::test_duplicate_job_sets_duplicate_status -v
```

Expected: `FAILED` vì `find_duplicate` chưa được gọi.

- [x] **Step 3: Implement duplicate check trong ProcessInvoiceUseCase**

Mở `app/application/use_cases/process_invoice.py`. Thêm logic duplicate check sau `await self._repo.save_items(job.id, items)` và trước `await self._repo.save_line_items(...)`:

```python
import asyncio
import logging
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.llm_port import ILLMPort
from app.domain.ports.notification_port import INotificationPort
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.infrastructure.parsers.xml_parser import extract_text_from_xml, extract_line_items_from_xml
from app.infrastructure.parsers.pdf_parser import extract_text_from_pdf

logger = logging.getLogger(__name__)

class ProcessInvoiceUseCase:
    def __init__(
        self,
        repo: IJobRepository,
        llm: ILLMPort,
        notification: Optional[INotificationPort] = None,
    ):
        self._repo = repo
        self._llm = llm
        self._notification = notification

    async def execute(
        self,
        filename: str,
        file_data: bytes,
        paired_pdf: bytes | None = None,
    ) -> ProcessingJob:
        file_type = FileType.from_filename(filename)
        job = ProcessingJob.create(filename=filename, file_type=file_type)
        await self._repo.save(job)
        await self._repo.update_status(job.id, InvoiceStatus.PROCESSING)

        try:
            import os
            pending_dir = "data/pending"
            os.makedirs(pending_dir, exist_ok=True)
            ext = filename.rsplit(".", 1)[-1].lower()
            pending_path = f"{pending_dir}/{job.id}.{ext}"
            with open(pending_path, "wb") as f:
                f.write(file_data)
            await self._repo.update_pending_file_path(job.id, pending_path)
            job.pending_file_path = pending_path

            if file_type == FileType.XML:
                content = extract_text_from_xml(file_data)
                line_items = extract_line_items_from_xml(file_data)
            else:
                content = await asyncio.to_thread(extract_text_from_pdf, file_data)
                line_items = []

            items, llm_line_items = await self._llm.extract_invoice(content)

            if file_type != FileType.XML:
                line_items = llm_line_items

            job.extracted_items = items
            job.extracted_line_items = line_items
            await self._repo.save_items(job.id, items)

            # Duplicate check — soft fail: DB error must not block the job
            if items:
                try:
                    item = items[0]
                    dup = await self._repo.find_duplicate(
                        item.invoice_symbol, item.invoice_number, item.seller_tax_code
                    )
                    if dup:
                        await self._repo.update_duplicate_of(job.id, dup.id)
                        await self._repo.update_status(job.id, InvoiceStatus.DUPLICATE)
                        job.status = InvoiceStatus.DUPLICATE
                        job.duplicate_of = dup.id
                        return job
                except Exception as dup_exc:
                    logger.warning("Duplicate check failed for job %s: %s", job.id, dup_exc)

            await self._repo.save_line_items(job.id, line_items)
            await self._repo.update_status(job.id, InvoiceStatus.AWAITING_REVIEW)
            job.status = InvoiceStatus.AWAITING_REVIEW

            if self._notification:
                try:
                    await self._notification.notify_new_invoice(job.id, filename)
                except Exception as notify_exc:
                    logger.warning("Notification failed for job %s: %s", job.id, notify_exc)

        except Exception as exc:
            import traceback
            error_msg = str(exc) or repr(exc)
            logger.error("Job %s failed: %s\n%s", job.id, error_msg, traceback.format_exc())
            await self._repo.update_status(job.id, InvoiceStatus.FAILED, error=error_msg)
            job.status = InvoiceStatus.FAILED
            job.error = error_msg

        return job
```

- [x] **Step 4: Chạy tất cả tests application**

```bash
pytest tests/application/test_process_invoice.py -v
```

Expected: tất cả PASS bao gồm 4 tests mới.

- [x] **Step 5: Commit**

```bash
git add app/application/use_cases/process_invoice.py tests/application/test_process_invoice.py
git commit -m "feat: detect duplicate invoices in ProcessInvoiceUseCase"
```

---

## Task 6: Presentation — Guard confirm endpoint + test

**Files:**
- Modify: `app/presentation/web/router.py`
- Test: `tests/presentation/test_web_router.py`

- [x] **Step 1: Viết failing test**

Mở `tests/presentation/test_web_router.py`. Tìm phần test liên quan đến confirm và thêm:

```python
async def test_confirm_duplicate_job_returns_400(client, repo):
    from app.domain.entities.processing_job import ProcessingJob
    from app.domain.value_objects.file_type import FileType
    from app.domain.value_objects.invoice_status import InvoiceStatus

    job = ProcessingJob.create("hd001.xml", FileType.XML)
    job.status = InvoiceStatus.DUPLICATE
    job.duplicate_of = "some-other-job-id"
    await repo.save(job)
    await repo.update_status(job.id, InvoiceStatus.DUPLICATE)

    response = await client.post(f"/jobs/{job.id}/confirm")
    assert response.status_code == 400
```

- [x] **Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/presentation/test_web_router.py::test_confirm_duplicate_job_returns_400 -v
```

Expected: `FAILED` — hiện tại confirm không check status DUPLICATE.

- [x] **Step 3: Thêm guard vào `/confirm` handler**

Mở `app/presentation/web/router.py`. Trong `web_confirm`, thêm guard ngay sau khi `job = await repo.get(job_id)`:

```python
@router.post("/jobs/{job_id}/confirm")
async def web_confirm(job_id: str, request: Request, background_tasks: BackgroundTasks,
                      repo=Depends(get_job_repo),
                      confirm_uc=Depends(get_review_confirm_uc)):
    from starlette.requests import ClientDisconnect
    try:
        form = await request.form()
    except ClientDisconnect:
        return RedirectResponse("/jobs", status_code=303)
    job = await repo.get(job_id)

    from app.domain.value_objects.invoice_status import InvoiceStatus
    if job is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    if job.status == InvoiceStatus.DUPLICATE:
        raise HTTPException(status_code=400, detail="Hóa đơn trùng lặp, không thể xác nhận")

    # ... phần còn lại của handler giữ nguyên
```

- [x] **Step 4: Chạy tất cả tests presentation**

```bash
pytest tests/presentation/test_web_router.py -v
```

Expected: tất cả PASS.

- [x] **Step 5: Commit**

```bash
git add app/presentation/web/router.py tests/presentation/test_web_router.py
git commit -m "feat: block confirm for DUPLICATE jobs with 400 guard"
```

---

## Task 7: UI — Badge "Trùng lặp" trong jobs.html

**Files:**
- Modify: `app/presentation/web/templates/jobs.html`

- [x] **Step 1: Thêm DUPLICATE vào badge map và thêm nút Review**

Mở `app/presentation/web/templates/jobs.html`. Tìm đoạn `{% set badge = {...} %}` và cập nhật:

```html
{% set badge = {
"PENDING": "secondary", "PROCESSING": "info",
"AWAITING_REVIEW": "warning", "CONFIRMING": "primary",
"CONFIRMED": "success", "REJECTED": "danger", "FAILED": "dark",
"DUPLICATE": "warning"
} %}
<span class="badge bg-{{ badge.get(job.status.value, 'secondary') }}" 
      {% if job.status.value == "DUPLICATE" %}style="background-color: #fd7e14 !important;"{% endif %}>
    {% if job.status.value == "CONFIRMING" %}Đang lưu Excel...
    {% elif job.status.value == "DUPLICATE" %}Trùng lặp
    {% else %}{{ job.status.value }}{% endif %}
</span>
```

Trong phần `<td>` hiển thị action buttons, thêm điều kiện cho DUPLICATE:

```html
{% if job.status.value == "AWAITING_REVIEW" %}
<a href="/jobs/{{ job.id }}/review" class="btn btn-sm btn-warning">Review</a>
{% endif %}
{% if job.status.value == "DUPLICATE" %}
<a href="/jobs/{{ job.id }}/review" class="btn btn-sm btn-outline-warning">Xem chi tiết</a>
{% endif %}
{% if job.status.value == "FAILED" %}
<span class="text-danger small">{{ job.error }}</span>
{% endif %}
```

- [x] **Step 2: Commit**

```bash
git add app/presentation/web/templates/jobs.html
git commit -m "feat: add Trung lap badge for DUPLICATE jobs in jobs list"
```

---

## Task 8: UI — Banner cảnh báo và ẩn Confirm trong review.html

**Files:**
- Modify: `app/presentation/web/templates/review.html`

- [x] **Step 1: Thêm banner cảnh báo và điều chỉnh action buttons**

Mở `app/presentation/web/templates/review.html`.

**1a.** Tìm dòng `<form id="confirmForm"` (dòng ~438). Thêm banner cảnh báo ngay TRƯỚC form đó:

```html
{% if job.status.value == "DUPLICATE" %}
<div class="alert alert-danger d-flex align-items-center gap-2 mb-3" role="alert">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" class="bi bi-exclamation-triangle-fill flex-shrink-0" viewBox="0 0 16 16">
    <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5m.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2"/>
  </svg>
  <div>
    <strong>Hóa đơn trùng lặp!</strong> Hóa đơn này đã tồn tại trong hệ thống.
    {% if job.duplicate_of %}
    <a href="/jobs/{{ job.duplicate_of }}/review" class="alert-link ms-1">Xem hóa đơn gốc →</a>
    {% endif %}
  </div>
</div>
{% endif %}
```

**1b.** Tìm đoạn action buttons (dòng ~570):

```html
<button type="button" id="confirmBtn" class="btn btn-success btn-sm px-4" onclick="submitConfirm()">✓ Xác nhận & Lưu XLS</button>
<a href="/jobs/{{ job.id }}/reject" class="btn btn-outline-danger btn-sm"
   onclick="return confirm('Từ chối hóa đơn này?')">✗ Từ chối</a>
<a href="/jobs" class="btn btn-outline-secondary btn-sm ms-auto">← Quay lại</a>
```

Thay bằng:

```html
{% if job.status.value != "DUPLICATE" %}
<button type="button" id="confirmBtn" class="btn btn-success btn-sm px-4" onclick="submitConfirm()">✓ Xác nhận & Lưu XLS</button>
{% endif %}
<a href="/jobs/{{ job.id }}/reject" class="btn btn-outline-danger btn-sm"
   onclick="return confirm('Từ chối hóa đơn này?')">✗ Từ chối</a>
<a href="/jobs" class="btn btn-outline-secondary btn-sm ms-auto">← Quay lại</a>
```

- [x] **Step 2: Commit**

```bash
git add app/presentation/web/templates/review.html
git commit -m "feat: show duplicate warning banner and hide Confirm button for DUPLICATE jobs"
```

---

## Task 9: Full test suite + smoke check

- [x] **Step 1: Chạy toàn bộ test suite**

```bash
cd /Users/quangdung/Documents/collect_invoice
pytest -v
```

Expected: tất cả tests PASS.

- [x] **Step 2: Kiểm tra DB migration trên file thực**

```bash
python -c "
import asyncio
from app.core.database import init_db, get_db

async def check():
    await init_db()
    db = await get_db()
    async with db.execute(\"PRAGMA table_info(jobs)\") as cur:
        cols = await cur.fetchall()
    print([c[1] for c in cols])

asyncio.run(check())
"
```

Expected: output chứa `'duplicate_of'` trong danh sách columns.

- [x] **Step 3: Commit cuối nếu có thay đổi còn sót**

```bash
git status
# Nếu có file chưa commit:
git add -p
git commit -m "chore: finalize duplicate invoice detection feature"
```
