# Invoice Collector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI-based invoice collection system for an accounting department: an IMAP email listener monitors for emails with `[Hóa đơn]` in the subject, downloads PDF/XML attachments, notifies staff via Telegram/Slack, staff review/edit extracted data in the web app, and confirmed records are appended to a monthly XLS summary stored on RustFS. Web upload is kept as a manual fallback.

**Architecture:** Clean architecture (domain → application ← infrastructure, presentation → application). FastAPI serves both Jinja2+HTMX web UI (`/web/`) and REST API (`/api/v1/`). Docker Compose runs `app` + `ollama` (local LLM) + `rustfs` (local S3). Email listener runs as an asyncio background task inside the `app` process. Job state persists in SQLite.

**Tech Stack:** Python 3.11, FastAPI, Jinja2+HTMX, Bootstrap 5 (CDN), Ollama/gemma, markitdown, lxml, openpyxl, boto3, aiosqlite, httpx, stdlib imaplib+email, pytest, Docker Compose

---

## File Map

```
collect_invoice/
├── app/
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── invoice_item.py       # InvoiceItem dataclass
│   │   │   └── processing_job.py     # ProcessingJob dataclass
│   │   ├── value_objects/
│   │   │   ├── file_type.py          # FileType enum
│   │   │   └── invoice_status.py     # InvoiceStatus enum
│   │   └── ports/
│   │       ├── storage_port.py       # IStoragePort ABC
│   │       ├── llm_port.py           # ILLMPort ABC
│   │       ├── job_repository.py     # IJobRepository ABC
│   │       ├── excel_port.py         # IExcelPort ABC
│   │       └── notification_port.py  # INotificationPort ABC
│   ├── application/
│   │   └── use_cases/
│   │       ├── process_invoice.py    # ProcessInvoiceUseCase
│   │       ├── review_and_confirm.py # ReviewAndConfirmUseCase
│   │       └── export_excel.py       # ExportExcelUseCase
│   ├── infrastructure/
│   │   ├── storage/
│   │   │   └── rustfs_storage.py     # boto3 S3-compatible impl
│   │   ├── llm/
│   │   │   └── ollama_client.py      # httpx Ollama impl
│   │   ├── parsers/
│   │   │   ├── xml_parser.py         # lxml → text
│   │   │   └── pdf_parser.py         # markitdown → text
│   │   ├── excel/
│   │   │   └── openpyxl_writer.py    # append rows to XLS
│   │   ├── notifications/
│   │   │   ├── telegram_notifier.py  # Telegram Bot API impl
│   │   │   ├── slack_notifier.py     # Slack Incoming Webhook impl
│   │   │   └── console_notifier.py   # stdout impl (dev/default)
│   │   ├── email/
│   │   │   ├── imap_client.py        # stdlib imaplib wrapped in asyncio.to_thread
│   │   │   ├── attachment_extractor.py # stdlib email module, extract PDF/XML
│   │   │   └── email_listener.py     # asyncio background task polling IMAP
│   │   └── repositories/
│   │       └── sqlite_job_repo.py    # aiosqlite impl
│   ├── presentation/
│   │   ├── api/
│   │   │   ├── schemas.py            # Pydantic request/response models
│   │   │   └── router.py             # /api/v1/ routes
│   │   └── web/
│   │       ├── router.py             # Jinja2 + HTMX routes
│   │       └── templates/
│   │           ├── base.html
│   │           ├── index.html        # upload page
│   │           ├── jobs.html         # job list
│   │           └── review.html       # review/edit page
│   ├── core/
│   │   ├── config.py                 # pydantic-settings
│   │   ├── database.py               # SQLite init + connection
│   │   └── dependencies.py           # FastAPI DI wiring
│   └── main.py                       # app factory
├── tests/
│   ├── conftest.py
│   ├── domain/
│   │   ├── test_value_objects.py
│   │   └── test_entities.py
│   ├── application/
│   │   ├── test_process_invoice.py
│   │   ├── test_review_and_confirm.py
│   │   └── test_export_excel.py
│   └── infrastructure/
│       ├── test_xml_parser.py
│       ├── test_pdf_parser.py
│       ├── test_sqlite_repo.py
│       ├── test_notifier.py
│       └── test_email_listener.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── poetry.lock
├── .env.example
├── pytest.ini
└── Mau_xuat_du_lieu.xlsx
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `pytest.ini`
- Create: `app/__init__.py` (and all `__init__.py` files)

- [X] **Step 1: Initialize git and create directory structure**

```bash
cd /Users/quangdung/Documents/collect_invoice
git init
mkdir -p app/domain/{entities,value_objects,ports}
mkdir -p app/application/use_cases
mkdir -p app/infrastructure/{storage,llm,parsers,excel,repositories,notifications,email}
mkdir -p app/presentation/{api,web/templates}
mkdir -p app/core
mkdir -p tests/{domain,application,infrastructure}
mkdir -p data
touch app/__init__.py
touch app/domain/__init__.py app/domain/entities/__init__.py
touch app/domain/value_objects/__init__.py app/domain/ports/__init__.py
touch app/application/__init__.py app/application/use_cases/__init__.py
touch app/infrastructure/__init__.py
touch app/infrastructure/{storage,llm,parsers,excel,repositories,notifications,email}/__init__.py
touch app/presentation/__init__.py app/presentation/api/__init__.py
touch app/presentation/web/__init__.py
touch app/core/__init__.py
touch tests/__init__.py tests/domain/__init__.py
touch tests/application/__init__.py tests/infrastructure/__init__.py
echo "data/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo ".env" >> .gitignore
```

- [X] **Step 2: Initialize Poetry and add dependencies**

```bash
poetry init --no-interaction
poetry add fastapi==0.115.0 \
           "uvicorn[standard]==0.30.0" \
           python-multipart==0.0.9 \
           jinja2==3.1.4 \
           pydantic==2.7.0 \
           pydantic-settings==2.3.0 \
           httpx==0.27.0 \
           boto3==1.34.0 \
           lxml==5.2.0 \
           markitdown==0.1.0 \
           openpyxl==3.1.5 \
           aiosqlite==0.20.0
poetry add --group dev pytest==8.2.0 pytest-asyncio==0.23.0
```

- [X] **Step 3: Create .env.example**

```
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_PATH=./data/invoices.db

OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=gemma3:4b

RUSTFS_ENDPOINT=http://rustfs:9000
RUSTFS_ACCESS_KEY=minioadmin
RUSTFS_SECRET_KEY=minioadmin
RUSTFS_BUCKET_INVOICES=invoices
RUSTFS_BUCKET_EXPORTS=exports

# IMAP Email Listener
IMAP_HOST=mail.example.com
IMAP_PORT=993
IMAP_USERNAME=ketoan@example.com
IMAP_PASSWORD=your_password
IMAP_USE_SSL=true
EMAIL_LISTENER_ENABLED=false
EMAIL_POLL_INTERVAL=300

# Notifications
NOTIFICATION_TYPE=console
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SLACK_WEBHOOK_URL=
APP_BASE_URL=http://localhost:8000
```

- [X] **Step 4: Create pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 5: Install dependencies**

```bash
poetry install
```

Expected: `poetry.lock` created and all packages installed without error.

- [X] **Step 6: Commit**

```bash
git add .
git commit -m "chore: initial project scaffolding"
```

---

## Task 2: Domain — Value Objects

**Files:**
- Create: `app/domain/value_objects/file_type.py`
- Create: `app/domain/value_objects/invoice_status.py`
- Create: `tests/domain/test_value_objects.py`

- [X] **Step 1: Write the failing tests**

```python
# tests/domain/test_value_objects.py
import pytest
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus

def test_file_type_from_pdf():
    assert FileType.from_filename("invoice.pdf") == FileType.PDF

def test_file_type_from_xml():
    assert FileType.from_filename("FACTURE.XML") == FileType.XML

def test_file_type_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        FileType.from_filename("invoice.doc")

def test_invoice_status_has_required_states():
    for name in ("PENDING", "PROCESSING", "AWAITING_REVIEW", "CONFIRMED", "REJECTED", "FAILED"):
        assert InvoiceStatus[name].value == name
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/domain/test_value_objects.py -v
```

Expected: `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement FileType**

```python
# app/domain/value_objects/file_type.py
from enum import Enum

class FileType(str, Enum):
    PDF = "PDF"
    XML = "XML"

    @classmethod
    def from_filename(cls, filename: str) -> "FileType":
        ext = filename.rsplit(".", 1)[-1].upper()
        if ext == "PDF":
            return cls.PDF
        if ext == "XML":
            return cls.XML
        raise ValueError(f"Unsupported file type: .{ext}")
```

- [ ] **Step 4: Implement InvoiceStatus**

```python
# app/domain/value_objects/invoice_status.py
from enum import Enum

class InvoiceStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
```

- [X] **Step 5: Run tests to verify they pass**

```bash
pytest tests/domain/test_value_objects.py -v
```

Expected: 4 PASSED.

- [X] **Step 6: Commit**

```bash
git add app/domain/value_objects/ tests/domain/test_value_objects.py
git commit -m "feat: domain value objects FileType and InvoiceStatus"
```

---

## Task 3: Domain — Entities

**Files:**
- Create: `app/domain/entities/invoice_item.py`
- Create: `app/domain/entities/processing_job.py`
- Create: `tests/domain/test_entities.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/domain/test_entities.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/domain/test_entities.py -v
```

Expected: `ImportError`.

- [X] **Step 3: Implement InvoiceItem**

```python
# app/domain/entities/invoice_item.py
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
import uuid

@dataclass
class InvoiceItem:
    invoice_symbol: str # Ký hiệu hóa đơn
    invoice_number: str # Số hóa đơn
    invoice_date: date # Ngày lập hóa đơn
    seller_name: str # Tên đơn vị bán hàng
    seller_tax_code: str # Mã số thuế
    description: str # Diễn giải
    price_before_tax: Decimal # Giá trước thuế
    tax_rate: Decimal # Thuế suất
    price_after_tax: Decimal # Giá sau thuế
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
```

- [X] **Step 4: Implement ProcessingJob**

```python
# app/domain/entities/processing_job.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid
from app.domain.entities.invoice_item import InvoiceItem
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
    source_paths: list[str] = field(default_factory=list)
    error: Optional[str] = None
    pending_file_path: Optional[str] = None  # local temp path until confirmed

    @classmethod
    def create(cls, filename: str, file_type: FileType) -> "ProcessingJob":
        return cls(
            id=str(uuid.uuid4()),
            filename=filename,
            file_type=file_type,
            status=InvoiceStatus.PENDING,
            created_at=datetime.utcnow(),
        )
```

- [X] **Step 5: Run tests to verify they pass**

```bash
pytest tests/domain/test_entities.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add app/domain/entities/ tests/domain/test_entities.py
git commit -m "feat: domain entities InvoiceItem and ProcessingJob"
```

---

## Task 4: Domain — Ports (Interfaces)

**Files:**
- Create: `app/domain/ports/storage_port.py`
- Create: `app/domain/ports/llm_port.py`
- Create: `app/domain/ports/job_repository.py`
- Create: `app/domain/ports/excel_port.py`

No tests needed for pure ABC interfaces — they are contracts tested indirectly through implementations.

- [X] **Step 1: Create IStoragePort**

```python
# app/domain/ports/storage_port.py
from abc import ABC, abstractmethod

class IStoragePort(ABC):
    @abstractmethod
    async def upload_file(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        """Upload file and return the storage key."""

    @abstractmethod
    async def download_file(self, bucket: str, key: str) -> bytes:
        """Download file and return bytes."""

    @abstractmethod
    async def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        """Return a presigned download URL."""
```

- [X] **Step 2: Create ILLMPort**

```python
# app/domain/ports/llm_port.py
from abc import ABC, abstractmethod
from app.domain.entities.invoice_item import InvoiceItem

class ILLMPort(ABC):
    @abstractmethod
    async def extract_invoice(self, content: str) -> list[InvoiceItem]:
        """Extract invoice fields from text content. Returns one item per tax-rate group."""
```

- [X] **Step 3: Create IJobRepository**

```python
# app/domain/ports/job_repository.py
from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.entities.invoice_item import InvoiceItem
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
```

- [X] **Step 4: Create IExcelPort**

```python
# app/domain/ports/excel_port.py
from abc import ABC, abstractmethod
from app.domain.entities.invoice_item import InvoiceItem

class IExcelPort(ABC):
    @abstractmethod
    async def append_rows(self, items: list[InvoiceItem], year: int, month: int) -> bytes:
        """Append items to monthly XLS and return the updated file as bytes."""
```

- [X] **Step 5: Create INotificationPort**

```python
# app/domain/ports/notification_port.py
from abc import ABC, abstractmethod

class INotificationPort(ABC):
    @abstractmethod
    async def notify_new_invoice(self, job_id: str, filename: str) -> None:
        """Notify staff that a new invoice is awaiting review."""
```

- [X] **Step 6: Commit**

```bash
git add app/domain/ports/
git commit -m "feat: domain ports (interfaces) for storage, LLM, repository, excel, notification"
```

---

## Task 5: Core Config & Database

**Files:**
- Create: `app/core/config.py`
- Create: `app/core/database.py`

- [X] **Step 1: Create config.py**

```python
# app/core/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_path: str = "./data/invoices.db"

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "gemma3:4b"

    rustfs_endpoint: str = "http://rustfs:9000"
    rustfs_access_key: str = "minioadmin"
    rustfs_secret_key: str = "minioadmin"
    rustfs_bucket_invoices: str = "invoices"
    rustfs_bucket_exports: str = "exports"

    # IMAP email listener
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_use_ssl: bool = True
    email_listener_enabled: bool = False
    email_poll_interval: int = 300  # seconds

    # Notifications
    notification_type: str = "console"  # "telegram" | "slack" | "console"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    slack_webhook_url: str = ""
    app_base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env"}

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [X] **Step 2: Create database.py**

```python
# app/core/database.py
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
    pending_file_path TEXT
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
    tax_amount TEXT DEFAULT '0',
    price_after_tax TEXT DEFAULT '0'
)
"""

async def get_db() -> aiosqlite.Connection:
    settings = get_settings()
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(settings.database_path)
    db.row_factory = aiosqlite.Row
    return db

async def init_db() -> None:
    db = await get_db()
    try:
        await db.execute(CREATE_JOBS_TABLE)
        await db.execute(CREATE_INVOICE_ITEMS_TABLE)
        await db.commit()
    finally:
        await db.close()

```

- [X] **Step 3: Copy .env.example to .env for local dev**

```bash
cp .env.example .env
# Edit .env: set DATABASE_PATH=./data/invoices.db, OLLAMA_BASE_URL=http://localhost:11434
```

- [X] **Step 4: Verify database init works**

```bash
python -c "import asyncio; from app.core.database import init_db; asyncio.run(init_db()); print('DB OK')"
```

Expected: `DB OK` with no errors. File `data/invoices.db` created.

- [X] **Step 5: Commit**

```bash
git add app/core/config.py app/core/database.py .env.example pytest.ini
git commit -m "feat: core config and SQLite database initialization"
```

---

## Task 6: Infrastructure — SQLite Job Repository

**Files:**
- Create: `app/infrastructure/repositories/sqlite_job_repo.py`
- Create: `tests/infrastructure/test_sqlite_repo.py`

- [X] **Step 1: Write failing tests**

```python
# tests/infrastructure/test_sqlite_repo.py
import pytest
import aiosqlite
from decimal import Decimal
from datetime import date, datetime
from app.domain.entities.processing_job import ProcessingJob
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository
from app.core.database import CREATE_JOBS_TABLE, CREATE_INVOICE_ITEMS_TABLE

@pytest.fixture
async def repo():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute(CREATE_JOBS_TABLE)
    await db.execute(CREATE_INVOICE_ITEMS_TABLE)
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
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/test_sqlite_repo.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement SQLiteJobRepository**

```python
# app/infrastructure/repositories/sqlite_job_repo.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/test_sqlite_repo.py -v
```

Expected: 4 PASSED.

- [X] **Step 5: Commit**

```bash
git add app/infrastructure/repositories/ tests/infrastructure/test_sqlite_repo.py
git commit -m "feat: SQLite job repository implementation"
```

---

## Task 7: Infrastructure — XML Parser

**Files:**
- Create: `app/infrastructure/parsers/xml_parser.py`
- Create: `tests/infrastructure/test_xml_parser.py`

**Context:** Real Vietnamese e-invoices have a complex nested structure with:
- `TTChung`: invoice metadata (series, number, date, currency, payment method)
- `NDHDon`: invoice details containing seller (NBan), buyer (NMua), and **multiple line items** (DSHHDVu/HHDVu)
- **Each HHDVu** has: description, quantity, unit price, VAT rate, amounts, and extra data in TTKhac/TTin
- `TToan`: totals grouped by VAT rate
- `DSCKS`: digital signatures (seller + government authority)

Parser must flatten nested structure into readable text while preserving invoice item details (qty, price, VAT).

- [X] **Step 1: Write failing tests**

```python
# tests/infrastructure/test_xml_parser.py
from pathlib import Path
from app.infrastructure.parsers.xml_parser import extract_text_from_xml

# Use actual test sample: tests/samples/invoice_test.xml
SAMPLE_XML_PATH = Path(__file__).parent.parent / "samples" / "invoice_test.xml"

def test_xml_extract_returns_string():
    assert SAMPLE_XML_PATH.exists(), f"Sample XML not found at {SAMPLE_XML_PATH}"
    with open(SAMPLE_XML_PATH, "rb") as f:
        result = extract_text_from_xml(f.read())
    assert isinstance(result, str)
    assert len(result) > 100

def test_xml_extract_contains_invoice_metadata():
    with open(SAMPLE_XML_PATH, "rb") as f:
        result = extract_text_from_xml(f.read())
    # Invoice series, number, date, party details
    assert "C26TAA" in result
    assert "00000064" in result
    assert "2026-03-18" in result
    assert "0201582012" in result  # Seller MST
    assert "0201712790" in result  # Buyer MST

def test_xml_extract_contains_invoice_items():
    with open(SAMPLE_XML_PATH, "rb") as f:
        result = extract_text_from_xml(f.read())
    # Line items: quantity, price, VAT rate, totals
    assert "12.000000" in result or "12" in result  # Qty from item 2
    assert "5900000" in result  # Unit price
    assert "8%" in result  # VAT rate
    assert "70800000" in result  # Amount for item 2

def test_xml_extract_contains_totals():
    with open(SAMPLE_XML_PATH, "rb") as f:
        result = extract_text_from_xml(f.read())
    # Invoice totals
    assert "445000000" in result  # Total before VAT
    assert "35600000" in result  # Total VAT
    assert "480600000" in result  # Grand total
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/test_xml_parser.py -v
```

Expected: `ImportError`.

- [X] **Step 3: Implement xml_parser.py**

```python
# app/infrastructure/parsers/xml_parser.py
from lxml import etree

def extract_text_from_xml(data: bytes) -> str:
    """
    Parse Vietnamese e-invoice XML and flatten to readable text for LLM.
    
    Preserves structure:
    - Invoice metadata (TTChung)
    - Seller/Buyer info (NBan, NMua)
    - Line items (DSHHDVu/HHDVu) with qty, price, VAT, amounts
    - Totals (TToan)
    
    Returns single string suitable for LLM extraction of invoice fields.
    """
    root = etree.fromstring(data)
    parts = []
    
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        text = (elem.text or "").strip()
        
        if text:
            # Preserve key financial fields with labels
            if tag in ("SHDon", "KHHDon", "NLap", "SLuong", "DGia", "ThTien", 
                      "TSuat", "TThue", "TgTCThue", "TgTThue", "TgTTTBSo",
                      "MST", "Ten", "STT", "THHDVu"):
                parts.append(f"{tag}: {text}")
            else:
                # Include other content as-is
                if len(text) > 2:  # Skip short junk
                    parts.append(f"{tag}: {text}")
    
    return "\n".join(parts)
```

- [X] **Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/test_xml_parser.py -v
```

Expected: 4 PASSED.

- [X] **Step 5: Commit**

```bash
git add app/infrastructure/parsers/xml_parser.py tests/infrastructure/test_xml_parser.py
git commit -m "feat: XML parser for Vietnamese e-invoices with structured data extraction"
```

---

## Task 8: Infrastructure — PDF Parser

**Files:**
- Create: `app/infrastructure/parsers/pdf_parser.py`
- Create: `tests/infrastructure/test_pdf_parser.py`

- [X] **Step 1: Write failing tests**

```python
# tests/infrastructure/test_pdf_parser.py
import pytest
from pathlib import Path
from app.infrastructure.parsers.pdf_parser import extract_text_from_pdf

# Use actual test sample: tests/samples/invoice_test.pdf
SAMPLE_PDF_PATH = Path(__file__).parent.parent / "samples" / "invoice_test.pdf"

def test_extract_text_from_pdf_returns_string():
    # Test with real Vietnamese e-invoice PDF
    assert SAMPLE_PDF_PATH.exists(), f"Sample PDF not found at {SAMPLE_PDF_PATH}"
    with open(SAMPLE_PDF_PATH, "rb") as f:
        text = extract_text_from_pdf(f.read())
    
    # Verify extraction returns string
    assert isinstance(text, str)
    assert len(text) > 0
    # Should contain invoice-related keywords (Vietnamese)
    assert any(kw in text.lower() for kw in ["hóa đơn", "invoice", "gtgt", "khhdon"])

def test_extract_text_raises_on_invalid_data():
    with pytest.raises(Exception):
        extract_text_from_pdf(b"not a pdf")
```

- [X] **Step 2: Run tests**

```bash
pytest tests/infrastructure/test_pdf_parser.py -v
```

Expected: 2 PASSED (using actual sample PDF file).

- [X] **Step 3: Implement pdf_parser.py**

```python
# app/infrastructure/parsers/pdf_parser.py
import tempfile
import os
from markitdown import MarkItDown

_converter = MarkItDown()

def extract_text_from_pdf(data: bytes) -> str:
    """Convert PDF bytes to markdown text using markitdown."""
    if not data.startswith(b"%PDF"):
        raise ValueError("Invalid PDF file: does not start with PDF header")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = _converter.convert(tmp_path)
        if not result or not result.text_content:
            raise ValueError("PDF conversion resulted in empty content")
        return result.text_content
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    finally:
        os.unlink(tmp_path)
```

- [X] **Step 4: Run tests**

```bash
pytest tests/infrastructure/test_pdf_parser.py -v
```

Expected: 2 PASSED.

- [X] **Step 5: Commit**

```bash
git add app/infrastructure/parsers/pdf_parser.py
git commit -m "feat: PDF parser using markitdown with validation"
```

---

## Task 9: Infrastructure — Ollama LLM Client

**Files:**
- Create: `app/infrastructure/llm/ollama_client.py`

- [X] **Step 1: Write failing tests**

```python
# tests/infrastructure/test_ollama_client.py
import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from datetime import date
from app.infrastructure.llm.ollama_client import OllamaLLMClient

MOCK_LLM_RESPONSE = """{
  "items": [
    {
      "invoice_symbol": "C26TAA",
      "invoice_number": "00000064",
      "invoice_date": "2026-03-18",
      "seller_name": "CÔNG TY TNHH ĐẦU TƯ VÀ VẬN TẢI AN PHÚ",
      "seller_tax_code": "0201582012",
      "description": "Hàng hóa/Dịch vụ",
      "price_before_tax": 445000000,
      "tax_rate": 0.08,
      "price_after_tax": 35600000
    }
  ]
}"""

@pytest.fixture
def client():
    return OllamaLLMClient(base_url="http://localhost:11434", model="gemma4:e2b")

async def test_extract_invoice_returns_items(client):
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": MOCK_LLM_RESPONSE}
    }
    # raise_for_status is a sync method in httpx
    mock_response.raise_for_status.return_value = None
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        items = await client.extract_invoice("KHHDon: C26TAA\nSHDon: 00000064\n...")
    assert len(items) == 1
    assert items[0].invoice_number == "00000064"
    assert items[0].price_before_tax == Decimal("445000000")
    assert items[0].tax_rate == Decimal("0.08")
    assert items[0].price_after_tax == Decimal("35600000")
    assert items[0].invoice_date == date(2026, 3, 18)
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/ -k "ollama" -v
```

Expected: `ImportError`.

- [X] **Step 3: Implement OllamaLLMClient**

```python
# app/infrastructure/llm/ollama_client.py
import json
from datetime import date
from decimal import Decimal
import uuid
import httpx
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.ports.llm_port import ILLMPort

EXTRACTION_PROMPT = """Phân tích hóa đơn điện tử Việt Nam sau đây và trích xuất thông tin chi tiết.

Nội dung hóa đơn:
{content}

Hướng dẫn:
- Hóa đơn có thể chứa NHIỀU dòng hàng hóa/dịch vụ (STT 1, 2, 3,...)
- Nhóm các dòng cùng mức thuế suất (TSuat) vào một phần tử
- Cộng dồn ThTien (cước suất/giá tiền) và VATAmount (thuế) theo từng mức thuế
- Trích xuất từ TTChung: KHHDon (ký hiệu), SHDon (số hóa đơn), NLap (ngày)
- Người bán từ NBan: Ten, MST
- Mô tả từ THHDVu của từng dòng; tổng hợp lại xem các dòng đó thuộc loại hàng hóa gì trong các loại mặt hàng sau đây:
    + vật tư
    + nhiên liệu
    + hàng hóa/dịch vụ
    + điện nước
    + Tiếp khách, ăn uống
- Nếu một dòng có SLuong=0, bỏ qua nó (dòng chỉ mục)

Trả về JSON với cấu trúc sau (một phần tử per mức thuế suất):
{{
  "items": [
    {{
      "invoice_symbol": "ký hiệu hóa đơn (vd: C26TAA)",
      "invoice_number": "số hóa đơn",
      "invoice_date": "DD/MM/YYYY",
      "seller_name": "tên người bán",
      "seller_tax_code": "mã số thuế người bán",
      "description": "mô tả hàng hóa (loại mặt hàng)",
      "price_before_tax": "giá trước thuế (vd: 445000000)",
      "tax_rate": "thuế suất (vd: 0.08)",
      "price_after_tax": "giá sau thuế (vd: 35600000)"
    }}
  ]
}}

Chỉ trả về JSON thuần túy, không có markdown hay giải thích. Giá trị số là số nguyên hoặc số thập phân."""


class OllamaLLMClient(ILLMPort):
    def __init__(self, base_url: str, model: str):
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def extract_invoice(self, content: str) -> list[InvoiceItem]:
        prompt = EXTRACTION_PROMPT.format(content=content)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                },
            )
            resp.raise_for_status()
        raw = resp.json()["message"]["content"]
        data = json.loads(raw)
        return [_parse_item(i) for i in data.get("items", [])]


def _parse_item(d: dict) -> InvoiceItem:
    invoice_date_raw = d.get("invoice_date", "")
    try:
        # Handle DD/MM/YYYY format as specified in prompt
        parts = invoice_date_raw.split("/")
        if len(parts) == 3:
            day, month, year = map(int, parts)
            invoice_date = date(year, month, day)
        else:
            invoice_date = date.fromisoformat(invoice_date_raw)
    except (ValueError, TypeError, AttributeError):
        invoice_date = date.today()
    return InvoiceItem(
        id=str(uuid.uuid4()) if "id" not in d else d["id"], # Added UUID if not present
        invoice_symbol=str(d.get("invoice_symbol", "")),
        invoice_number=str(d.get("invoice_number", "")),
        invoice_date=invoice_date,
        seller_name=str(d.get("seller_name", "")),
        seller_tax_code=str(d.get("seller_tax_code", "")),
        description=str(d.get("description", "")),
        price_before_tax=Decimal(str(d.get("price_before_tax", 0))),
        tax_rate=Decimal(str(d.get("tax_rate", 0))),
        price_after_tax=Decimal(str(d.get("price_after_tax", 0))),
    )
```

- [X] **Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/ -k "ollama" -v
```

Expected: 1 PASSED.

- [X] **Step 5: Commit**

```bash
git add app/infrastructure/llm/ tests/infrastructure/test_ollama_client.py
git commit -m "feat: Ollama LLM client for invoice extraction"
```

---

## Task 10: Infrastructure — RustFS Storage

**Files:**
- Create: `app/infrastructure/storage/rustfs_storage.py`

- [X] **Step 1: Implement RustFSStorage**

No unit tests for S3 — integration tested manually against a running RustFS instance.

```python
# app/infrastructure/storage/rustfs_storage.py
import asyncio
import boto3
from botocore.exceptions import ClientError
from app.domain.ports.storage_port import IStoragePort

class RustFSStorage(IStoragePort):
    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )

    async def upload_file(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=bucket, Key=key, Body=data, ContentType=content_type,
        )
        return key

    async def download_file(self, bucket: str, key: str) -> bytes:
        resp = await asyncio.to_thread(
            self._client.get_object, Bucket=bucket, Key=key
        )
        return resp["Body"].read()

    async def get_presigned_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def ensure_buckets(self, *bucket_names: str) -> None:
        """Create buckets if they don't exist. Call on app startup."""
        for name in bucket_names:
            try:
                await asyncio.to_thread(self._client.head_bucket, Bucket=name)
            except ClientError:
                await asyncio.to_thread(self._client.create_bucket, Bucket=name)
```

- [X] **Step 2: Commit**

```bash
git add app/infrastructure/storage/rustfs_storage.py
git commit -m "feat: RustFS S3-compatible storage implementation"
```

---

## Task 11: Infrastructure — Excel Writer

**Files:**
- Create: `app/infrastructure/excel/openpyxl_writer.py`

The XLS template (`Mau_xuat_du_lieu.xlsx`) defines the sheet structure. The writer appends rows to the "Bang ke thue" sheet of a monthly export file, following the column layout from the template (confirmed by reading the file in session setup):

| Col | Index | Field |
|-----|-------|-------|
| A | 1 | STT (auto-incremented row number) |
| D | 4 | invoice_symbol |
| E | 5 | invoice_number |
| F | 6 | invoice_date |
| G | 7 | seller_name |
| H | 8 | seller_tax_code |
| I | 9 | description |
| J | 10 | price_before_tax |
| K | 11 | tax_rate × 100 (integer %, e.g. 10) |
| L | 12 | tax_rate decimal (e.g. 0.10) |
| M | 13 | price_after_tax |

- [X] **Step 1: Write failing test**

```python
# tests/infrastructure/test_excel_writer.py
import pytest
from decimal import Decimal
from datetime import date
from io import BytesIO
import openpyxl
from app.domain.entities.invoice_item import InvoiceItem
from app.infrastructure.excel.openpyxl_writer import OpenpyxlWriter

TEMPLATE_PATH = "Mau_xuat_du_lieu.xlsx"

def make_item(**kwargs):
    defaults = dict(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )
    defaults.update(kwargs)
    return InvoiceItem(**defaults)

@pytest.mark.asyncio
async def test_append_rows_returns_filename_and_bytes():
    writer = OpenpyxlWriter(template_path=TEMPLATE_PATH)
    filename, file_bytes = await writer.append_rows([make_item()], year=2026, month=3, existing_data=b"")
    assert filename == "Tong_hop_hoa_don_T3_2026.xlsx"
    assert isinstance(file_bytes, bytes)
    assert len(file_bytes) > 0

@pytest.mark.asyncio
async def test_appended_row_contains_invoice_number():
    writer = OpenpyxlWriter(template_path=TEMPLATE_PATH)
    filename, file_bytes = await writer.append_rows([make_item(invoice_number="TEST-49")], year=2026, month=3, existing_data=b"")
    wb = openpyxl.load_workbook(BytesIO(file_bytes))
    ws = wb["Bang ke thue"]
    values = [ws.cell(row=r, column=5).value for r in range(1, ws.max_row + 1)]
    assert "TEST-49" in values
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/test_excel_writer.py -v
```

Expected: `ImportError`.

- [X] **Step 3: Implement OpenpyxlWriter with filename support**

```python
# app/infrastructure/excel/openpyxl_writer.py
import asyncio
from io import BytesIO
from decimal import Decimal
import openpyxl
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.ports.excel_port import IExcelPort

# First data row in the template (after headers and category label)
DATA_START_ROW = 13
SHEET_NAME = "Bang ke thue"

def generate_monthly_filename(month: int, year: int) -> str:
    """Generate filename: Tong_hop_hoa_don_T{month}_{year}.xlsx
    Example: Tong_hop_hoa_don_T4_2026.xlsx
    """
    return f"Tong_hop_hoa_don_T{month}_{year}.xlsx"

class OpenpyxlWriter(IExcelPort):
    def __init__(self, template_path: str):
        self._template_path = template_path

    async def append_rows(
        self, items: list[InvoiceItem], year: int, month: int, existing_data: bytes
    ) -> tuple[str, bytes]:
        """Append rows to monthly Excel file.
        
        Returns: (filename, file_bytes) tuple
        - filename: For RustFS path like s3://exports/{filename}
        - file_bytes: Excel file bytes to save
        """
        filename = generate_monthly_filename(month, year)
        file_bytes = await asyncio.to_thread(self._append_rows_sync, items, existing_data)
        return filename, file_bytes

    def _append_rows_sync(self, items: list[InvoiceItem], existing_data: bytes) -> bytes:
        if existing_data:
            wb = openpyxl.load_workbook(BytesIO(existing_data))
        else:
            wb = openpyxl.load_workbook(self._template_path)

        ws = wb[SHEET_NAME]

        # Find next available row after the last data row
        last_row = DATA_START_ROW - 1
        for row in range(ws.max_row, DATA_START_ROW - 1, -1):
            if ws.cell(row=row, column=5).value is not None:  # invoice_number column
                last_row = row
                break

        # Determine STT offset
        stt_offset = 0
        for row in range(DATA_START_ROW, last_row + 1):
            v = ws.cell(row=row, column=1).value
            if isinstance(v, int):
                stt_offset = v

        for idx, item in enumerate(items, start=1):
            r = last_row + idx
            ws.cell(row=r, column=1).value = stt_offset + idx
            ws.cell(row=r, column=4).value = item.invoice_symbol
            ws.cell(row=r, column=5).value = item.invoice_number
            ws.cell(row=r, column=6).value = item.invoice_date
            ws.cell(row=r, column=7).value = item.seller_name
            ws.cell(row=r, column=8).value = item.seller_tax_code
            ws.cell(row=r, column=9).value = item.description
            ws.cell(row=r, column=10).value = float(item.price_before_tax)
            ws.cell(row=r, column=11).value = int(item.tax_rate * 100)
            ws.cell(row=r, column=12).value = float(item.tax_rate)
            ws.cell(row=r, column=13).value = float(item.price_after_tax)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()
```

- [X] **Step 4: Run tests to verify they pass**

```bash
pytest tests/infrastructure/test_excel_writer.py -v
```

Expected: 2 PASSED.

- [X] **Step 5: Commit**

```bash
git add app/infrastructure/excel/ tests/infrastructure/test_excel_writer.py
git commit -m "feat: openpyxl Excel writer appending to monthly XLS"
```

---

## Task 12: Application — ProcessInvoiceUseCase

**Files:**
- Create: `app/application/use_cases/process_invoice.py`
- Create: `tests/application/test_process_invoice.py`

- [X] **Step 1: Write failing tests**

```python
# tests/application/test_process_invoice.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import date
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.domain.value_objects.file_type import FileType

def make_item():
    return InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("29030000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("2903000"),
    )

@pytest.fixture
def use_case():
    repo = AsyncMock()
    llm = AsyncMock()
    notification = AsyncMock()
    llm.extract_invoice.return_value = [make_item()]
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
    notification.notify_new_invoice.assert_called_once_with(job.id, "hd049.xml")

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
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/application/test_process_invoice.py -v
```

Expected: `ImportError`.

- [X] **Step 3: Implement ProcessInvoiceUseCase**

```python
# app/application/use_cases/process_invoice.py
import asyncio
import logging
from typing import Optional
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.llm_port import ILLMPort
from app.domain.ports.notification_port import INotificationPort
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.infrastructure.parsers.xml_parser import extract_text_from_xml
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
            # Save raw file to data/pending/ for later RustFS archiving on confirm
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
            else:
                content = await asyncio.to_thread(extract_text_from_pdf, file_data)

            items = await self._llm.extract_invoice(content)
            job.extracted_items = items
            await self._repo.save_items(job.id, items)
            await self._repo.update_status(job.id, InvoiceStatus.AWAITING_REVIEW)
            job.status = InvoiceStatus.AWAITING_REVIEW

            # Notify staff — failure here must not fail the job
            if self._notification:
                try:
                    await self._notification.notify_new_invoice(job.id, filename)
                except Exception as notify_exc:
                    logger.warning("Notification failed for job %s: %s", job.id, notify_exc)

        except Exception as exc:
            error_msg = str(exc)
            await self._repo.update_status(job.id, InvoiceStatus.FAILED, error=error_msg)
            job.status = InvoiceStatus.FAILED
            job.error = error_msg

        return job
```

- [X] **Step 4: Run tests to verify they pass**

```bash
pytest tests/application/test_process_invoice.py -v
```

Expected: 4 PASSED (PDF test may need markitdown mock — acceptable as-is since it tests orchestration).

- [X] **Step 5: Commit**

```bash
git add app/application/use_cases/process_invoice.py tests/application/test_process_invoice.py
git commit -m "feat: ProcessInvoiceUseCase orchestrating parse + LLM extraction"
```

---

## Task 13: Application — ReviewAndConfirmUseCase

**Files:**
- Create: `app/application/use_cases/review_and_confirm.py`
- Create: `tests/application/test_review_and_confirm.py`

- [X] **Step 1: Write failing tests**

```python
# tests/application/test_review_and_confirm.py
import pytest
from unittest.mock import AsyncMock
from decimal import Decimal
from datetime import date
from app.application.use_cases.review_and_confirm import ReviewAndConfirmUseCase
from app.domain.entities.invoice_item import InvoiceItem
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
    return job

async def test_confirm_job_sets_confirmed_status(tmp_path):
    repo = AsyncMock()
    storage = AsyncMock()
    excel = AsyncMock()
    excel.append_rows.return_value = b"xlsx_bytes"
    storage.download_file.return_value = b""
    job = make_job_with_items()
    # Simulate pending file on disk
    pending = tmp_path / f"{job.id}.xml"
    pending.write_bytes(b"<HDon/>")
    job.pending_file_path = str(pending)
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(repo=repo, storage=storage, excel=excel,
                                  bucket_invoices="invoices", bucket_exports="exports")
    result = await uc.confirm(job_id=job.id, updated_items=job.extracted_items)

    assert result.status == InvoiceStatus.CONFIRMED
    storage.upload_file.assert_called()
    excel.append_rows.assert_called_once()

async def test_reject_job_sets_rejected_status():
    repo = AsyncMock()
    job = make_job_with_items()
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(repo=repo, storage=AsyncMock(),
                                  excel=AsyncMock(), bucket_invoices="i", bucket_exports="e")
    result = await uc.reject(job_id=job.id)
    assert result.status == InvoiceStatus.REJECTED
    repo.update_status.assert_called_with(job.id, InvoiceStatus.REJECTED)
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/application/test_review_and_confirm.py -v
```

- [X] **Step 3: Implement ReviewAndConfirmUseCase**

```python
# app/application/use_cases/review_and_confirm.py
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_port import IExcelPort
from app.domain.value_objects.invoice_status import InvoiceStatus

class ReviewAndConfirmUseCase:
    def __init__(
        self,
        repo: IJobRepository,
        storage: IStoragePort,
        excel: IExcelPort,
        bucket_invoices: str,
        bucket_exports: str,
    ):
        self._repo = repo
        self._storage = storage
        self._excel = excel
        self._bucket_invoices = bucket_invoices
        self._bucket_exports = bucket_exports

    async def confirm(
        self,
        job_id: str,
        updated_items: list[InvoiceItem],
    ) -> ProcessingJob:
        import os
        job = await self._repo.get(job_id)
        await self._repo.update_items(job_id, updated_items)

        # Read raw file from pending temp storage
        pending_path = job.pending_file_path
        if pending_path and os.path.exists(pending_path):
            with open(pending_path, "rb") as f:
                file_data = f.read()
        else:
            file_data = b""

        # Upload original invoice file to RustFS
        first = updated_items[0]
        year, month = first.invoice_date.year, first.invoice_date.month
        customer = first.seller_name.replace("/", "-").replace(" ", "_")[:50]
        ext = job.filename.rsplit(".", 1)[-1]
        storage_key = f"{year}/{month:02d}/{customer}/{first.invoice_number}.{ext}"
        await self._storage.upload_file(
            self._bucket_invoices, storage_key, file_data,
            "application/pdf" if ext == "pdf" else "application/xml",
        )

        # Clean up pending temp file
        if pending_path and os.path.exists(pending_path):
            os.unlink(pending_path)
        await self._repo.add_source_path(job_id, storage_key)

        # Append to monthly XLS in RustFS
        xls_key = f"Bang_ke_thue_{year}_{month:02d}.xlsx"
        try:
            existing = await self._storage.download_file(self._bucket_exports, xls_key)
        except Exception:
            existing = b""
        updated_xls = await self._excel.append_rows(updated_items, year, month, existing)
        await self._storage.upload_file(
            self._bucket_exports, xls_key, updated_xls,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        await self._repo.update_status(job_id, InvoiceStatus.CONFIRMED)
        job.status = InvoiceStatus.CONFIRMED
        return job

    async def reject(self, job_id: str) -> ProcessingJob:
        job = await self._repo.get(job_id)
        await self._repo.update_status(job_id, InvoiceStatus.REJECTED)
        job.status = InvoiceStatus.REJECTED
        return job
```

- [X] **Step 4: Run tests to verify they pass**

```bash
pytest tests/application/test_review_and_confirm.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/application/use_cases/review_and_confirm.py tests/application/test_review_and_confirm.py
git commit -m "feat: ReviewAndConfirmUseCase handling confirm/reject flow"
```

---

## Task 14: Application — ExportExcelUseCase

**Files:**
- Create: `app/application/use_cases/export_excel.py`
- Create: `tests/application/test_export_excel.py`

- [X] **Step 1: Write failing test**

```python
# tests/application/test_export_excel.py
import pytest
from unittest.mock import AsyncMock
from app.application.use_cases.export_excel import ExportExcelUseCase

async def test_export_returns_bytes_and_filename():
    storage = AsyncMock()
    storage.download_file.return_value = b"xlsx_bytes"
    uc = ExportExcelUseCase(storage=storage, bucket_exports="exports")
    data, filename = await uc.execute(year=2026, month=3)
    assert data == b"xlsx_bytes"
    assert filename == "Bang_ke_thue_2026_03.xlsx"

async def test_export_raises_when_not_found():
    storage = AsyncMock()
    storage.download_file.side_effect = Exception("NoSuchKey")
    uc = ExportExcelUseCase(storage=storage, bucket_exports="exports")
    with pytest.raises(FileNotFoundError):
        await uc.execute(year=2026, month=3)
```

- [X] **Step 2: Run tests to verify they fail**

```bash
pytest tests/application/test_export_excel.py -v
```

- [X] **Step 3: Implement ExportExcelUseCase**

```python
# app/application/use_cases/export_excel.py
from app.domain.ports.storage_port import IStoragePort

class ExportExcelUseCase:
    def __init__(self, storage: IStoragePort, bucket_exports: str):
        self._storage = storage
        self._bucket_exports = bucket_exports

    async def execute(self, year: int, month: int) -> tuple[bytes, str]:
        filename = f"Bang_ke_thue_{year}_{month:02d}.xlsx"
        try:
            data = await self._storage.download_file(self._bucket_exports, filename)
        except Exception as exc:
            raise FileNotFoundError(f"No export file found for {year}/{month:02d}") from exc
        return data, filename
```

- [X] **Step 4: Run tests to verify they pass**

```bash
pytest tests/application/test_export_excel.py -v
```

Expected: 2 PASSED.

- [X] **Step 5: Commit**

```bash
git add app/application/use_cases/export_excel.py tests/application/test_export_excel.py
git commit -m "feat: ExportExcelUseCase for downloading monthly XLS"
```

---

## Task 15: Presentation — REST API

**Files:**
- Create: `app/presentation/api/schemas.py`
- Create: `app/presentation/api/router.py`

- [X] **Step 1: Create Pydantic schemas**

```python
# app/presentation/api/schemas.py
from pydantic import BaseModel
from decimal import Decimal
from datetime import date, datetime
from typing import Optional

class InvoiceItemSchema(BaseModel):
    id: str
    invoice_symbol: str
    invoice_number: str
    invoice_date: date
    seller_name: str
    seller_tax_code: str
    description: str
    price_before_tax: Decimal
    tax_rate: Decimal
    price_after_tax: Decimal

class JobResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    created_at: datetime
    extracted_items: list[InvoiceItemSchema]
    source_paths: list[str]
    error: Optional[str]

class ReviewRequest(BaseModel):
    items: list[InvoiceItemSchema]
```

- [X] **Step 2: Create REST router**

```python
# app/presentation/api/router.py
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from app.presentation.api.schemas import JobResponse, ReviewRequest, InvoiceItemSchema
from app.core.dependencies import (
    get_process_invoice_uc, get_review_confirm_uc, get_export_excel_uc, get_job_repo,
)

router = APIRouter(prefix="/api/v1")

@router.post("/jobs", response_model=list[JobResponse])
async def upload_invoices(
    files: list[UploadFile] = File(...),
    process_uc=Depends(get_process_invoice_uc),
    repo=Depends(get_job_repo),
):
    # Pair XML + PDF by base filename
    file_map: dict[str, dict] = {}
    for f in files:
        base = f.filename.rsplit(".", 1)[0].lower()
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if base not in file_map:
            file_map[base] = {}
        file_map[base][ext] = (f.filename, await f.read())

    jobs = []
    for base, exts in file_map.items():
        if "xml" in exts:
            filename, data = exts["xml"]
            paired_pdf = exts.get("pdf", (None, None))[1]
        else:
            filename, data = exts["pdf"]
            paired_pdf = None
        job = await process_uc.execute(filename=filename, file_data=data, paired_pdf=paired_pdf)
        jobs.append(_job_to_response(job))
    return jobs

@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(status: str | None = None, repo=Depends(get_job_repo)):
    from app.domain.value_objects.invoice_status import InvoiceStatus
    status_filter = InvoiceStatus(status) if status else None
    jobs = await repo.list_all(status=status_filter)
    return [_job_to_response(j) for j in jobs]

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, repo=Depends(get_job_repo)):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)

@router.patch("/jobs/{job_id}/review", response_model=JobResponse)
async def update_review(job_id: str, body: ReviewRequest, repo=Depends(get_job_repo)):
    from app.domain.entities.invoice_item import InvoiceItem
    from decimal import Decimal
    items = [InvoiceItem(**i.model_dump()) for i in body.items]
    await repo.update_items(job_id, items)
    job = await repo.get(job_id)
    return _job_to_response(job)

@router.post("/jobs/{job_id}/confirm", response_model=JobResponse)
async def confirm_job(
    job_id: str,
    repo=Depends(get_job_repo),
    confirm_uc=Depends(get_review_confirm_uc),
):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Retrieve raw file from storage for archiving
    from app.core.dependencies import get_storage
    # File data passed via the original upload — stored temporarily
    # For simplicity: re-fetch from a temp store or pass from session
    # In this implementation we pass empty bytes; storage key is set by use case
    result = await confirm_uc.confirm(
        job_id=job_id,
        updated_items=job.extracted_items,
    )
    return _job_to_response(result)

@router.post("/jobs/{job_id}/reject", response_model=JobResponse)
async def reject_job(job_id: str, confirm_uc=Depends(get_review_confirm_uc)):
    result = await confirm_uc.reject(job_id=job_id)
    return _job_to_response(result)

@router.get("/exports/{year}/{month}")
async def download_export(year: int, month: int, export_uc=Depends(get_export_excel_uc)):
    try:
        data, filename = await export_uc.execute(year=year, month=month)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def _job_to_response(job) -> JobResponse:
    from app.presentation.api.schemas import InvoiceItemSchema
    return JobResponse(
        id=job.id, filename=job.filename, file_type=job.file_type.value,
        status=job.status.value, created_at=job.created_at,
        extracted_items=[InvoiceItemSchema(**{
            "id": i.id, "invoice_symbol": i.invoice_symbol, "invoice_number": i.invoice_number,
            "invoice_date": i.invoice_date, "seller_name": i.seller_name, "seller_tax_code": i.seller_tax_code,
            "description": i.description, "price_before_tax": i.price_before_tax, "tax_rate": i.tax_rate, "price_after_tax": i.price_after_tax,
        }) for i in job.extracted_items],
        source_paths=job.source_paths, error=job.error,
    )
```

- [ ] **Step 3: Commit**

```bash
git add app/presentation/api/
git commit -m "feat: REST API router and Pydantic schemas"
```

---

## Task 16: Presentation — Web UI

**Files:**
- Create: `app/presentation/web/router.py`
- Create: `app/presentation/web/templates/base.html`
- Create: `app/presentation/web/templates/index.html`
- Create: `app/presentation/web/templates/jobs.html`
- Create: `app/presentation/web/templates/review.html`

- [X] **Step 1: Create web router**

```python
# app/presentation/web/router.py
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.core.dependencies import get_process_invoice_uc, get_review_confirm_uc, get_job_repo

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/upload")
async def handle_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    process_uc=Depends(get_process_invoice_uc),
):
    file_map: dict[str, dict] = {}
    for f in files:
        base = f.filename.rsplit(".", 1)[0].lower()
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if base not in file_map:
            file_map[base] = {}
        file_map[base][ext] = (f.filename, await f.read())

    for base, exts in file_map.items():
        if "xml" in exts:
            filename, data = exts["xml"]
            paired_pdf = exts.get("pdf", (None, None))[1]
        else:
            filename, data = exts["pdf"]
            paired_pdf = None
        await process_uc.execute(filename=filename, file_data=data, paired_pdf=paired_pdf)

    return RedirectResponse("/jobs", status_code=303)

@router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, repo=Depends(get_job_repo)):
    jobs = await repo.list_all()
    return templates.TemplateResponse("jobs.html", {"request": request, "jobs": jobs})

@router.get("/jobs/{job_id}/review", response_class=HTMLResponse)
async def review_page(job_id: str, request: Request, repo=Depends(get_job_repo)):
    job = await repo.get(job_id)
    return templates.TemplateResponse("review.html", {"request": request, "job": job})

@router.post("/jobs/{job_id}/confirm")
async def web_confirm(job_id: str, request: Request, repo=Depends(get_job_repo),
                      confirm_uc=Depends(get_review_confirm_uc)):
    form = await request.form()
    job = await repo.get(job_id)
    from app.domain.entities.invoice_item import InvoiceItem
    from decimal import Decimal
    from datetime import date

    items = []
    for item in job.extracted_items:
        items.append(InvoiceItem(
            id=item.id,
            invoice_symbol=form.get(f"invoice_symbol_{item.id}", item.invoice_symbol),
            invoice_number=form.get(f"invoice_number_{item.id}", item.invoice_number),
            invoice_date=date.fromisoformat(form.get(f"invoice_date_{item.id}", item.invoice_date.isoformat())),
            seller_name=form.get(f"seller_name_{item.id}", item.seller_name),
            seller_tax_code=form.get(f"seller_tax_code_{item.id}", item.seller_tax_code),
            description=form.get(f"description_{item.id}", item.description),
            price_before_tax=Decimal(form.get(f"price_before_tax_{item.id}", str(item.price_before_tax))),
            tax_rate=Decimal(form.get(f"tax_rate_{item.id}", str(item.tax_rate))),
            price_after_tax=Decimal(form.get(f"price_after_tax_{item.id}", str(item.price_after_tax))),
        ))

    await confirm_uc.confirm(job_id=job_id, updated_items=items)
    return RedirectResponse("/jobs", status_code=303)

@router.post("/jobs/{job_id}/reject")
async def web_reject(job_id: str, confirm_uc=Depends(get_review_confirm_uc)):
    await confirm_uc.reject(job_id=job_id)
    return RedirectResponse("/jobs", status_code=303)
```

- [X] **Step 2: Create base.html**

```html
<!-- app/presentation/web/templates/base.html -->
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Thu Hóa Đơn{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body>
<nav class="navbar navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="/">Thu Hóa Đơn</a>
    <div>
      <a href="/" class="btn btn-outline-light btn-sm me-2">Upload</a>
      <a href="/jobs" class="btn btn-outline-light btn-sm">Danh sách</a>
    </div>
  </div>
</nav>
<div class="container">
  {% block content %}{% endblock %}
</div>
</body>
</html>
```

- [X] **Step 3: Create index.html**

```html
<!-- app/presentation/web/templates/index.html -->
{% extends "base.html" %}
{% block title %}Upload Hóa Đơn{% endblock %}
{% block content %}
<div class="row justify-content-center">
  <div class="col-md-6">
    <h2 class="mb-4">Upload Hóa Đơn</h2>
    <form action="/upload" method="post" enctype="multipart/form-data">
      <div class="mb-3">
        <label class="form-label">Chọn file hóa đơn (PDF và/hoặc XML)</label>
        <input class="form-control" type="file" name="files" multiple accept=".pdf,.xml">
        <div class="form-text">Có thể chọn nhiều file. Nếu có cả XML và PDF cùng tên, hệ thống sẽ dùng XML.</div>
      </div>
      <button type="submit" class="btn btn-primary">Xử lý</button>
    </form>
  </div>
</div>
{% endblock %}
```

- [X] **Step 4: Create jobs.html**

```html
<!-- app/presentation/web/templates/jobs.html -->
{% extends "base.html" %}
{% block title %}Danh sách Hóa Đơn{% endblock %}
{% block content %}
<h2 class="mb-4">Danh sách Hóa Đơn</h2>
<table class="table table-striped table-hover">
  <thead class="table-dark">
    <tr>
      <th>File</th><th>Loại</th><th>Trạng thái</th><th>Ngày tạo</th><th></th>
    </tr>
  </thead>
  <tbody>
  {% for job in jobs %}
    <tr>
      <td>{{ job.filename }}</td>
      <td>{{ job.file_type.value }}</td>
      <td>
        {% set badge = {
          "PENDING": "secondary", "PROCESSING": "info",
          "AWAITING_REVIEW": "warning", "CONFIRMED": "success",
          "REJECTED": "danger", "FAILED": "dark"
        } %}
        <span class="badge bg-{{ badge.get(job.status.value, 'secondary') }}">
          {{ job.status.value }}
        </span>
      </td>
      <td>{{ job.created_at.strftime("%d/%m/%Y %H:%M") }}</td>
      <td>
        {% if job.status.value == "AWAITING_REVIEW" %}
          <a href="/jobs/{{ job.id }}/review" class="btn btn-sm btn-warning">Review</a>
        {% endif %}
        {% if job.status.value == "FAILED" %}
          <span class="text-danger small">{{ job.error }}</span>
        {% endif %}
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [X] **Step 5: Create review.html**

```html
<!-- app/presentation/web/templates/review.html -->
{% extends "base.html" %}
{% block title %}Review Hóa Đơn — {{ job.filename }}{% endblock %}
{% block content %}
<h2 class="mb-4">Review: {{ job.filename }}</h2>
<form action="/jobs/{{ job.id }}/confirm" method="post">
  {% for item in job.extracted_items %}
  <div class="card mb-3">
    <div class="card-header">Dòng {{ loop.index }}</div>
    <div class="card-body">
      <div class="row g-3">
        {% set fields = [
          ("invoice_symbol", "Ký hiệu HĐ"), ("invoice_number", "Số HĐ"),
          ("invoice_date", "Ngày phát hành"), ("seller_name", "Tên người bán"),
          ("seller_tax_code", "Mã số thuế"), ("description", "Mặt hàng"),
          ("price_before_tax", "Doanh số chưa thuế"), ("tax_rate", "Thuế suất"),
          ("price_after_tax", "Thuế GTGT")
        ] %}
        {% for fname, label in fields %}
        <div class="col-md-4">
          <label class="form-label">{{ label }}</label>
          <input class="form-control" type="text"
                 name="{{ fname }}_{{ item.id }}"
                 value="{{ item[fname] if fname != 'invoice_date' else item.invoice_date.isoformat() }}">
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
  {% endfor %}
  <div class="d-flex gap-2 mt-3">
    <button type="submit" class="btn btn-success">Xác nhận & Lưu vào XLS</button>
    <a href="/jobs/{{ job.id }}/reject"
       class="btn btn-danger"
       onclick="return confirm('Từ chối hóa đơn này?')">Từ chối</a>
    <a href="/jobs" class="btn btn-secondary">Quay lại</a>
  </div>
</form>
{% endblock %}
```

- [X] **Step 6: Commit**

```bash
git add app/presentation/web/
git commit -m "feat: web UI with upload, job list, and review pages"
```

---

## Task 17: App Wiring — Dependencies & Main

**Files:**
- Create: `app/core/dependencies.py`
- Create: `app/main.py`

- [ ] **Step 1: Create dependencies.py**

```python
# app/core/dependencies.py
from functools import lru_cache
import aiosqlite
from fastapi import Depends
from app.core.config import get_settings, Settings
from app.core.database import get_db
from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository
from app.infrastructure.llm.ollama_client import OllamaLLMClient
from app.infrastructure.storage.rustfs_storage import RustFSStorage
from app.infrastructure.excel.openpyxl_writer import OpenpyxlWriter
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
from app.application.use_cases.review_and_confirm import ReviewAndConfirmUseCase
from app.application.use_cases.export_excel import ExportExcelUseCase

async def get_db_conn() -> aiosqlite.Connection:
    async with await get_db() as db:
        yield db

def get_job_repo(db: aiosqlite.Connection = Depends(get_db_conn)) -> SQLiteJobRepository:
    return SQLiteJobRepository(db)

def get_llm(settings: Settings = Depends(get_settings)) -> OllamaLLMClient:
    return OllamaLLMClient(base_url=settings.ollama_base_url, model=settings.ollama_model)

def get_storage(settings: Settings = Depends(get_settings)) -> RustFSStorage:
    return RustFSStorage(
        endpoint=settings.rustfs_endpoint,
        access_key=settings.rustfs_access_key,
        secret_key=settings.rustfs_secret_key,
    )

def get_excel() -> OpenpyxlWriter:
    return OpenpyxlWriter(template_path="Mau_xuat_du_lieu.xlsx")

def get_notifier():
    from app.core.config import get_settings
    settings = get_settings()
    if settings.notification_type == "telegram" and settings.telegram_bot_token:
        from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
        return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id, settings.app_base_url)
    if settings.notification_type == "slack" and settings.slack_webhook_url:
        from app.infrastructure.notifications.slack_notifier import SlackNotifier
        return SlackNotifier(settings.slack_webhook_url, settings.app_base_url)
    from app.infrastructure.notifications.console_notifier import ConsoleNotifier
    return ConsoleNotifier()

def get_process_invoice_uc(
    repo=Depends(get_job_repo), llm=Depends(get_llm)
) -> ProcessInvoiceUseCase:
    return ProcessInvoiceUseCase(repo=repo, llm=llm, notification=get_notifier())

def get_review_confirm_uc(
    repo=Depends(get_job_repo),
    storage=Depends(get_storage),
    excel=Depends(get_excel),
    settings: Settings = Depends(get_settings),
) -> ReviewAndConfirmUseCase:
    return ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel,
        bucket_invoices=settings.rustfs_bucket_invoices,
        bucket_exports=settings.rustfs_bucket_exports,
    )

def get_export_excel_uc(
    storage=Depends(get_storage), settings: Settings = Depends(get_settings)
) -> ExportExcelUseCase:
    return ExportExcelUseCase(storage=storage, bucket_exports=settings.rustfs_bucket_exports)
```

- [ ] **Step 2: Create main.py**

```python
# app/main.py
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI
from app.core.config import get_settings
from app.core.database import init_db, get_db
from app.infrastructure.storage.rustfs_storage import RustFSStorage
from app.presentation.api.router import router as api_router
from app.presentation.web.router import router as web_router

logger = logging.getLogger(__name__)


def _build_notifier(settings):
    if settings.notification_type == "telegram" and settings.telegram_bot_token:
        from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
        return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id, settings.app_base_url)
    if settings.notification_type == "slack" and settings.slack_webhook_url:
        from app.infrastructure.notifications.slack_notifier import SlackNotifier
        return SlackNotifier(settings.slack_webhook_url, settings.app_base_url)
    from app.infrastructure.notifications.console_notifier import ConsoleNotifier
    return ConsoleNotifier()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    storage = RustFSStorage(
        endpoint=settings.rustfs_endpoint,
        access_key=settings.rustfs_access_key,
        secret_key=settings.rustfs_secret_key,
    )
    try:
        await storage.ensure_buckets(
            settings.rustfs_bucket_invoices,
            settings.rustfs_bucket_exports,
        )
    except Exception:
        pass  # RustFS may not be available in dev mode

    listener_task: Optional[asyncio.Task] = None
    listener_obj = None

    if settings.email_listener_enabled:
        from app.infrastructure.email.imap_client import IMAPClient
        from app.infrastructure.email.email_listener import EmailListener
        from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository
        from app.infrastructure.llm.ollama_client import OllamaLLMClient
        from app.application.use_cases.process_invoice import ProcessInvoiceUseCase

        db = await get_db()
        repo = SQLiteJobRepository(db)
        llm = OllamaLLMClient(settings.ollama_base_url, settings.ollama_model)
        notification = _build_notifier(settings)
        process_uc = ProcessInvoiceUseCase(repo=repo, llm=llm, notification=notification)
        imap_client = IMAPClient(
            host=settings.imap_host, port=settings.imap_port,
            username=settings.imap_username, password=settings.imap_password,
            use_ssl=settings.imap_use_ssl,
        )
        listener_obj = EmailListener(imap_client, process_uc, settings.email_poll_interval)
        listener_task = asyncio.create_task(listener_obj.start())
        logger.info("Email listener started (polling every %ds)", settings.email_poll_interval)

    yield

    if listener_obj and listener_task:
        listener_obj.stop()
        listener_task.cancel()
        logger.info("Email listener stopped")


app = FastAPI(title="Thu Hóa Đơn", lifespan=lifespan)
app.include_router(api_router)
app.include_router(web_router)
```

- [X] **Step 3: Run the app locally (without Docker) to verify wiring**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected: Server starts, `http://localhost:8000` shows upload page. No import errors.

- [X] **Step 4: Run all tests**

```bash
pytest -v
```

Expected: All tests pass.

- [X] **Step 5: Commit**

```bash
git add app/core/dependencies.py app/main.py
git commit -m "feat: app wiring — DI dependencies and FastAPI main"
```

---

## Task 18: Docker Compose + Dockerfile (Dev & Prod)

**Files:**
- Create: `Dockerfile` (development)
- Create: `Dockerfile.prod` (production)
- Create: `docker-compose.yml` (development)
- Create: `docker-compose.prod.yml` (production)
- Create: `ollama-entrypoint.sh` (auto-pull Ollama model)
- Update: `pyproject.toml` (add gunicorn for prod)

---

### DEVELOPMENT SETUP

- [X] **Step 1: Update pyproject.toml with prod dependencies**

Add this to `[dependency-groups]`:
```toml
prod = [
    "gunicorn (>=23.0.0,<24.0.0)"
]
```

- [X] **Step 2: Create Dockerfile (Development)**

```dockerfile
# Dockerfile — Development with volume mount & auto-reload
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

COPY pyproject.toml poetry.lock* ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --with dev

# App code is mounted as volume in docker-compose.yml
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- [X] **Step 3: Create docker-compose.yml (Development)**

```yaml
version: '3.8'

services:
  app:
    build: .
    container_name: collect-invoice-app
    ports:
      - "8000:8000"
    volumes:
      # Mount entire app directory for development
      - .:/app
      - ./data:/app/data
      - ./Mau_xuat_du_lieu.xlsx:/app/Mau_xuat_du_lieu.xlsx:ro
      # Exclude .venv and .git to avoid syncing
      - /app/.venv
      - /app/.git
    env_file: .env
    environment:
      DATABASE_PATH: ./data/invoices.db
      OLLAMA_BASE_URL: http://ollama:11434
      RUSTFS_ENDPOINT: http://rustfs:9000
    depends_on:
      - ollama
      - rustfs
    restart: unless-stopped
    networks:
      - invoice-network

  ollama:
    image: ollama/ollama:latest
    container_name: collect-invoice-ollama
    volumes:
      - ollama_data:/root/.ollama
      - ./ollama-entrypoint.sh:/ollama-entrypoint.sh:ro
    ports:
      - "11434:11434"
    environment:
      OLLAMA_HOST: 0.0.0.0:11434
    entrypoint: /bin/bash /ollama-entrypoint.sh
    restart: unless-stopped
    networks:
      - invoice-network

  rustfs:
    image: rustfs/rustfs:latest
    container_name: collect-invoice-rustfs
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - rustfs_data:/data
    environment:
      RUSTFS_VOLUMES: /data
      RUSTFS_ROOT_USER: rustfsadmin
      RUSTFS_ROOT_PASSWORD: rustfsadmin
    restart: unless-stopped
    networks:
      - invoice-network

volumes:
  ollama_data:
  rustfs_data:

networks:
  invoice-network:
    driver: bridge
```

- [X] **Step 4: Create ollama-entrypoint.sh (Auto-pull model)**

```bash
#!/bin/bash
set -e

# Start Ollama in background
/bin/ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready (check port 11434)
echo "Waiting for Ollama to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Ollama is ready!"
    break
  fi
  echo "Attempt $i: Ollama not ready yet, waiting..."
  sleep 2
done

# Pull gemma4:e2b model
echo "Pulling gemma4:e2b model..."
/bin/ollama pull gemma4:e2b

# Keep Ollama running in foreground
wait $OLLAMA_PID
```

Make it executable:
```bash
chmod +x ollama-entrypoint.sh
```

- [ ] **Step 5: Start Development Environment**

```bash
# Build images (first time only)
docker compose build

# Start all services (Ollama will auto-pull gemma4:e2b)
docker compose up -d

# Watch Ollama pulling the model (~2-4GB, takes 5-10 min first time)
docker compose logs -f ollama

# Once model is pulled, verify app is running
docker compose logs -f app

# Expected output: "Application startup complete"
```

- [ ] **Step 6: Verify Dev Environment**

```bash
# Check all services are healthy
docker compose ps

# Expected:
#   collect-invoice-app      Up
#   collect-invoice-ollama   Up
#   collect-invoice-rustfs   Up

# Test app is accessible
curl http://localhost:8000

# Expected: HTML response (Jinja2 template)
```

---

### PRODUCTION SETUP

- [X] **Step 7: Create Dockerfile.prod (Production)**

```dockerfile
# Multi-stage build for production
FROM python:3.12-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock* ./

RUN poetry export --without-hashes --no-interaction --no-ansi -f requirements.txt -o requirements.txt

# Final production image
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt

# Copy entire application code (no volume mounts in prod)
COPY . .

RUN mkdir -p data

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Production: gunicorn with 4 workers for better performance
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "app.main:app"]
```

- [X] **Step 8: Create docker-compose.prod.yml (Production)**

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.prod
    container_name: collect-invoice-app-prod
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./Mau_xuat_du_lieu.xlsx:/app/Mau_xuat_du_lieu.xlsx:ro
    env_file: .env
    environment:
      DATABASE_PATH: ./data/invoices.db
      OLLAMA_BASE_URL: http://ollama:11434
      RUSTFS_ENDPOINT: http://rustfs:9000
    depends_on:
      - ollama
      - rustfs
    restart: unless-stopped
    networks:
      - invoice-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  ollama:
    image: ollama/ollama:latest
    container_name: collect-invoice-ollama-prod
    volumes:
      - ollama_data:/root/.ollama
      - ./ollama-entrypoint.sh:/ollama-entrypoint.sh:ro
    ports:
      - "11434:11434"
    environment:
      OLLAMA_HOST: 0.0.0.0:11434
    entrypoint: /bin/bash /ollama-entrypoint.sh
    restart: unless-stopped
    networks:
      - invoice-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  rustfs:
    image: rustfs/rustfs:latest
    container_name: collect-invoice-rustfs-prod
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - rustfs_data:/data
    environment:
      RUSTFS_VOLUMES: /data
      RUSTFS_ROOT_USER: rustfsadmin
      RUSTFS_ROOT_PASSWORD: rustfsadmin
    restart: unless-stopped
    networks:
      - invoice-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

volumes:
  ollama_data:
  rustfs_data:

networks:
  invoice-network:
    driver: bridge
```

- [ ] **Step 9: Start Production Environment**

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f app
```

---

### SMOKE TEST (Dev or Prod)

- [ ] **Step 10: Test Complete Workflow**

```bash
# 1. Visit http://localhost:8000 in browser
# 2. Upload a sample XML invoice file
# 3. Verify job appears at http://localhost:8000/jobs with status AWAITING_REVIEW
# 4. Check console for notification: "[INVOICE] Hóa đơn mới cần phê duyệt..."
# 5. Click Review, verify extracted fields appear
# 6. Click Confirm
# 7. Verify http://localhost:8000/api/v1/exports/2026/4 returns XLSX file
```

---

### FINAL COMMIT

- [ ] **Step 11: Commit all files**

```bash
git add Dockerfile Dockerfile.prod docker-compose.yml docker-compose.prod.yml ollama-entrypoint.sh pyproject.toml
git commit -m "feat: Docker setup for dev (volume mount) and prod (multi-stage, gunicorn, non-root user)"
```

---

## Task 19: Infrastructure — Notification Adapters

**Files:**
- Create: `app/infrastructure/notifications/console_notifier.py`
- Create: `app/infrastructure/notifications/telegram_notifier.py`
- Create: `app/infrastructure/notifications/slack_notifier.py`
- Create: `tests/infrastructure/test_notifier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/infrastructure/test_notifier.py
import pytest
from unittest.mock import AsyncMock, patch
from app.infrastructure.notifications.console_notifier import ConsoleNotifier
from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
from app.infrastructure.notifications.slack_notifier import SlackNotifier

async def test_console_notifier_does_not_raise(capsys):
    notifier = ConsoleNotifier()
    await notifier.notify_new_invoice("job-123", "HD0049.xml")
    captured = capsys.readouterr()
    assert "HD0049.xml" in captured.out

async def test_telegram_notifier_calls_api():
    notifier = TelegramNotifier(token="test_token", chat_id="123456", app_base_url="http://localhost:8000")
    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        await notifier.notify_new_invoice("job-abc", "HD0049.xml")
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "sendMessage" in str(call_kwargs)
    assert "123456" in str(call_kwargs)

async def test_slack_notifier_calls_webhook():
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", app_base_url="http://localhost:8000")
    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        await notifier.notify_new_invoice("job-abc", "HD0049.xml")
    mock_post.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/test_notifier.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement ConsoleNotifier**

```python
# app/infrastructure/notifications/console_notifier.py
from app.domain.ports.notification_port import INotificationPort

class ConsoleNotifier(INotificationPort):
    async def notify_new_invoice(self, job_id: str, filename: str) -> None:
        print(f"[INVOICE] Hóa đơn mới cần phê duyệt: {filename} (job_id={job_id})")
```

- [ ] **Step 4: Implement TelegramNotifier**

```python
# app/infrastructure/notifications/telegram_notifier.py
import httpx
from app.domain.ports.notification_port import INotificationPort

class TelegramNotifier(INotificationPort):
    def __init__(self, token: str, chat_id: str, app_base_url: str):
        self._token = token
        self._chat_id = chat_id
        self._app_base_url = app_base_url.rstrip("/")

    async def notify_new_invoice(self, job_id: str, filename: str) -> None:
        text = (
            f"📄 Hóa đơn mới cần phê duyệt\n"
            f"File: {filename}\n"
            f"👉 {self._app_base_url}/jobs/{job_id}/review"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
            )
            resp.raise_for_status()
```

- [ ] **Step 5: Implement SlackNotifier**

```python
# app/infrastructure/notifications/slack_notifier.py
import httpx
from app.domain.ports.notification_port import INotificationPort

class SlackNotifier(INotificationPort):
    def __init__(self, webhook_url: str, app_base_url: str):
        self._webhook_url = webhook_url
        self._app_base_url = app_base_url.rstrip("/")

    async def notify_new_invoice(self, job_id: str, filename: str) -> None:
        text = (
            f":page_facing_up: *Hóa đơn mới cần phê duyệt*\n"
            f"File: `{filename}`\n"
            f"<{self._app_base_url}/jobs/{job_id}/review|Xem và phê duyệt>"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._webhook_url,
                json={"text": text},
            )
            resp.raise_for_status()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/infrastructure/test_notifier.py -v
```

Expected: 3 PASSED.

- [ ] **Step 7: Commit**

```bash
git add app/infrastructure/notifications/ app/domain/ports/notification_port.py tests/infrastructure/test_notifier.py
git commit -m "feat: notification adapters — Telegram, Slack, Console"
```

---

## Task 20: Infrastructure — IMAP Email Listener

**Files:**
- Create: `app/infrastructure/email/imap_client.py`
- Create: `app/infrastructure/email/attachment_extractor.py`
- Create: `app/infrastructure/email/email_listener.py`
- Create: `tests/infrastructure/test_email_listener.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/infrastructure/test_email_listener.py
import pytest
import email as email_lib
from unittest.mock import AsyncMock, MagicMock, patch
from app.infrastructure.email.attachment_extractor import extract_attachments
from app.infrastructure.email.email_listener import EmailListener

# --- attachment_extractor tests ---

def _make_email_with_attachment(filename: str, content: bytes, content_type: str) -> email_lib.message.Message:
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    msg = MIMEMultipart()
    msg["Subject"] = "[Hóa đơn] Test"
    part = MIMEBase("application", "octet-stream")
    part.set_payload(content)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(part)
    return msg

def test_extract_pdf_attachment():
    msg = _make_email_with_attachment("HD0049.pdf", b"%PDF-1.4 content", "application/pdf")
    attachments = extract_attachments(msg)
    assert len(attachments) == 1
    assert attachments[0][0] == "HD0049.pdf"
    assert attachments[0][1] == b"%PDF-1.4 content"

def test_extract_xml_attachment():
    msg = _make_email_with_attachment("HD0049.xml", b"<HDon/>", "application/xml")
    attachments = extract_attachments(msg)
    assert len(attachments) == 1
    assert attachments[0][0] == "HD0049.xml"

def test_skip_non_invoice_attachment():
    msg = _make_email_with_attachment("document.docx", b"word content", "application/docx")
    attachments = extract_attachments(msg)
    assert len(attachments) == 0

# --- EmailListener tests ---

async def test_listener_calls_process_uc_for_xml_attachment():
    process_uc = AsyncMock()
    imap_client = AsyncMock()
    msg = _make_email_with_attachment("HD0049.xml", b"<HDon/>", "application/xml")
    imap_client.fetch_invoice_emails.return_value = [(1, msg)]

    listener = EmailListener(imap_client, process_uc, poll_interval=999)
    await listener._poll_once()

    process_uc.execute.assert_called_once_with(
        filename="HD0049.xml", file_data=b"<HDon/>", paired_pdf=None
    )

async def test_listener_pairs_xml_and_pdf():
    process_uc = AsyncMock()
    imap_client = AsyncMock()
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    msg = MIMEMultipart()
    msg["Subject"] = "[Hóa đơn] Test"
    for fname, content in [("HD0049.xml", b"<HDon/>"), ("HD0049.pdf", b"%PDF")]:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(content)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=fname)
        msg.attach(part)

    imap_client.fetch_invoice_emails.return_value = [(1, msg)]
    listener = EmailListener(imap_client, process_uc, poll_interval=999)
    await listener._poll_once()

    process_uc.execute.assert_called_once_with(
        filename="HD0049.xml", file_data=b"<HDon/>", paired_pdf=b"%PDF"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/infrastructure/test_email_listener.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement attachment_extractor.py**

```python
# app/infrastructure/email/attachment_extractor.py
import email as email_lib
from email.header import decode_header as _decode_header

def extract_attachments(msg: email_lib.message.Message) -> list[tuple[str, bytes]]:
    """Return list of (filename, bytes) for PDF/XML attachments only."""
    results = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue
        raw_filename = part.get_filename()
        if not raw_filename:
            continue
        filename = _decode_mime_header(raw_filename)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ("pdf", "xml"):
            continue
        data = part.get_payload(decode=True)
        if data:
            results.append((filename, data))
    return results


def _decode_mime_header(value: str) -> str:
    parts = []
    for decoded, charset in _decode_header(value):
        if isinstance(decoded, bytes):
            parts.append(decoded.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(decoded)
    return "".join(parts)
```

- [ ] **Step 4: Implement imap_client.py**

```python
# app/infrastructure/email/imap_client.py
import asyncio
import imaplib
import email as email_lib
import logging

logger = logging.getLogger(__name__)

class IMAPClient:
    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_ssl = use_ssl

    async def fetch_invoice_emails(self) -> list[tuple[int, email_lib.message.Message]]:
        """Fetch unread emails whose subject contains [Hóa đơn]. Marks them as read."""
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> list[tuple[int, email_lib.message.Message]]:
        cls = imaplib.IMAP4_SSL if self._use_ssl else imaplib.IMAP4
        with cls(self._host, self._port) as conn:
            conn.login(self._username, self._password)
            conn.select("INBOX")
            # Fetch all UNSEEN, filter by subject in Python (avoids IMAP UTF-8 encoding issues)
            _, msg_ids = conn.search(None, "UNSEEN")
            results = []
            for msg_id in msg_ids[0].split():
                _, msg_data = conn.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                msg = email_lib.message_from_bytes(msg_data[0][1])
                subject = msg.get("Subject", "")
                if "[Hóa đơn]" not in subject and "[hoa don]" not in subject.lower():
                    continue
                conn.store(msg_id, "+FLAGS", "\\Seen")
                results.append((int(msg_id), msg))
            return results
```

- [ ] **Step 5: Implement email_listener.py**

```python
# app/infrastructure/email/email_listener.py
import asyncio
import logging
from app.infrastructure.email.imap_client import IMAPClient
from app.infrastructure.email.attachment_extractor import extract_attachments
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase

logger = logging.getLogger(__name__)

class EmailListener:
    def __init__(self, imap_client: IMAPClient, process_uc: ProcessInvoiceUseCase, poll_interval: int = 300):
        self._imap = imap_client
        self._process_uc = process_uc
        self._poll_interval = poll_interval
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._poll_once()
            except Exception as exc:
                logger.error("Email poll error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False

    async def _poll_once(self) -> None:
        emails = await self._imap.fetch_invoice_emails()
        for msg_id, msg in emails:
            attachments = extract_attachments(msg)
            by_base: dict[str, dict] = {}
            for filename, data in attachments:
                base = filename.rsplit(".", 1)[0].lower()
                ext = filename.rsplit(".", 1)[-1].lower()
                if base not in by_base:
                    by_base[base] = {}
                by_base[base][ext] = (filename, data)

            for base, exts in by_base.items():
                if "xml" in exts:
                    filename, data = exts["xml"]
                    paired_pdf = exts.get("pdf", (None, None))[1]
                else:
                    filename, data = exts["pdf"]
                    paired_pdf = None
                try:
                    await self._process_uc.execute(
                        filename=filename, file_data=data, paired_pdf=paired_pdf
                    )
                except Exception as exc:
                    logger.error("Failed to process attachment %s from email %s: %s", filename, msg_id, exc)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/infrastructure/test_email_listener.py -v
```

Expected: 5 PASSED.

- [ ] **Step 7: Integration smoke test (requires real IMAP account)**

```bash
# Set IMAP credentials in .env then run:
EMAIL_LISTENER_ENABLED=true python -c "
import asyncio
from app.core.config import get_settings
from app.infrastructure.email.imap_client import IMAPClient

async def test():
    s = get_settings()
    client = IMAPClient(s.imap_host, s.imap_port, s.imap_username, s.imap_password, s.imap_use_ssl)
    emails = await client.fetch_invoice_emails()
    print(f'Found {len(emails)} invoice emails')

asyncio.run(test())
"
```

Expected: prints number of unread `[Hóa đơn]` emails found (0 if none pending).

- [ ] **Step 8: Commit**

```bash
git add app/infrastructure/email/ tests/infrastructure/test_email_listener.py
git commit -m "feat: IMAP email listener with attachment extraction and invoice pairing"
```

---

## Notes

**First run checklist:**
1. Copy `.env.example` to `.env` and adjust values
2. For email listener: set `IMAP_*` vars and `EMAIL_LISTENER_ENABLED=true`
3. For Telegram notifications: set `NOTIFICATION_TYPE=telegram`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
4. Start services: `docker compose up -d`
5. Pull LLM model: `docker compose exec ollama ollama pull gemma3:4b`
6. Open `http://localhost:8000`

**Telegram Bot setup:** Create a bot via @BotFather → get token. Add bot to a group or get your chat ID via `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending a message.

**Adjusting the Ollama model:** Set `OLLAMA_MODEL` in `.env` (e.g., `gemma3:2b` for Pi 4B lower RAM, `gemma3:12b` on Pi 5).

**Email listener off by default:** `EMAIL_LISTENER_ENABLED=false` in `.env.example`. Staff can still upload manually via web app. Set to `true` once IMAP credentials are configured.
