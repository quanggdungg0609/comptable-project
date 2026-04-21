# Invoice Line Items (Chi Tiết Hàng Hóa) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trích xuất từng dòng hàng hóa/dịch vụ từ hóa đơn, lưu vào bảng riêng, hiển thị chỉnh sửa được trên trang review, và xuất file Excel chi tiết khi confirm.

**Architecture:** XML invoices → parse line items trực tiếp từ XML (không cần LLM). PDF invoices → cập nhật LLM prompt để trả về cả `items` (gộp theo thuế suất) lẫn `line_items` (từng dòng) trong một lần gọi. Line items được lưu vào bảng `invoice_line_items` riêng và export ra file Excel `Chi_tiet_hoa_don_T{M}_{Y}.xlsx` khi confirm.

**Tech Stack:** Python 3.12, aiosqlite, openpyxl, FastAPI/Jinja2, lxml

---

## File Map

**Tạo mới:**
- `app/domain/entities/invoice_line_item.py` — dataclass `InvoiceLineItem`
- `app/domain/ports/excel_detail_port.py` — abstract `IExcelDetailPort`
- `app/infrastructure/excel/openpyxl_detail_writer.py` — `OpenpyxlDetailWriter`
- `tests/domain/test_invoice_line_item.py`
- `tests/infrastructure/test_sqlite_repo_line_items.py`
- `tests/infrastructure/test_xml_line_items.py`
- `tests/infrastructure/test_excel_detail_writer.py`
- `tests/application/test_process_invoice_line_items.py`
- `tests/application/test_review_confirm_line_items.py`

**Sửa đổi:**
- `app/domain/entities/processing_job.py` — thêm `extracted_line_items`
- `app/domain/ports/job_repository.py` — thêm `save_line_items`, `update_line_items`
- `app/domain/ports/llm_port.py` — đổi return type `extract_invoice`
- `app/core/database.py` — thêm `CREATE_INVOICE_LINE_ITEMS_TABLE`, gọi trong `init_db`
- `app/infrastructure/repositories/sqlite_job_repo.py` — implement 2 method mới, load line items trong `get()`
- `app/infrastructure/parsers/xml_parser.py` — thêm `extract_line_items_from_xml()`
- `app/infrastructure/llm/ollama_client.py` — cập nhật prompt + parse line_items
- `app/infrastructure/llm/gemini_client.py` — cập nhật maxOutputTokens + parse line_items
- `app/infrastructure/llm/fallback_client.py` — cập nhật return type
- `app/application/use_cases/process_invoice.py` — lưu line items
- `app/application/use_cases/review_and_confirm.py` — nhận line_items, export detail Excel
- `app/core/dependencies.py` — thêm `get_excel_detail()`, cập nhật `get_review_confirm_uc`
- `app/presentation/api/schemas.py` — thêm `InvoiceLineItemSchema`, cập nhật `JobResponse`
- `app/presentation/web/router.py` — parse line items từ form confirm
- `app/presentation/web/templates/review.html` — thêm bảng chi tiết chỉnh sửa được

---

## Task 1: InvoiceLineItem entity + DB table

**Files:**
- Create: `app/domain/entities/invoice_line_item.py`
- Create: `tests/domain/test_invoice_line_item.py`
- Modify: `app/domain/entities/processing_job.py`
- Modify: `app/core/database.py`

- [ ] **Step 1: Viết failing test cho entity**

```python
# tests/domain/test_invoice_line_item.py
from decimal import Decimal
from datetime import date
from app.domain.entities.invoice_line_item import InvoiceLineItem

def test_invoice_line_item_defaults():
    item = InvoiceLineItem(
        invoice_symbol="1C26TAA",
        invoice_number="49",
        invoice_date=date(2026, 3, 12),
        seller_name="Cty XYZ",
        seller_tax_code="0901212659",
        ten_hang_hoa="Thép tấm 10mm",
        don_vi_tinh="Kg",
        so_luong=Decimal("298"),
        don_gia=Decimal("28000"),
        thanh_tien=Decimal("8344000"),
        tax_rate=Decimal("0.10"),
        tax_amount=Decimal("834400"),
    )
    assert item.ten_hang_hoa == "Thép tấm 10mm"
    assert item.so_luong == Decimal("298")
    assert isinstance(item.id, str) and len(item.id) == 36  # UUID
```

- [ ] **Step 2: Chạy test để xác nhận fail**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/domain/test_invoice_line_item.py -v
```
Expected: `ImportError: cannot import name 'InvoiceLineItem'`

- [ ] **Step 3: Tạo entity**

```python
# app/domain/entities/invoice_line_item.py
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
import uuid

@dataclass
class InvoiceLineItem:
    invoice_symbol: str
    invoice_number: str
    invoice_date: date
    seller_name: str
    seller_tax_code: str
    ten_hang_hoa: str
    don_vi_tinh: str
    so_luong: Decimal
    don_gia: Decimal
    thanh_tien: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
```

- [ ] **Step 4: Chạy test để xác nhận pass**

```bash
python -m pytest tests/domain/test_invoice_line_item.py -v
```
Expected: PASS

- [ ] **Step 5: Thêm `extracted_line_items` vào `ProcessingJob`**

Mở `app/domain/entities/processing_job.py`, thêm import và field:

```python
# Thêm import sau dòng "from app.domain.entities.invoice_item import InvoiceItem"
from app.domain.entities.invoice_line_item import InvoiceLineItem

# Thêm field này vào dataclass ProcessingJob (sau extracted_items):
extracted_line_items: list[InvoiceLineItem] = field(default_factory=list)
```

- [ ] **Step 6: Thêm bảng DB và init**

Mở `app/core/database.py`, thêm sau `CREATE_INVOICE_ITEMS_TABLE`:

```python
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
```

Trong hàm `init_db()`, thêm dòng sau `await db.execute(CREATE_INVOICE_ITEMS_TABLE)`:

```python
await db.execute(CREATE_INVOICE_LINE_ITEMS_TABLE)
```

- [ ] **Step 7: Commit**

```bash
git add app/domain/entities/invoice_line_item.py \
        app/domain/entities/processing_job.py \
        app/core/database.py \
        tests/domain/test_invoice_line_item.py
git commit -m "feat: add InvoiceLineItem entity and invoice_line_items DB table"
```

---

## Task 2: Repository — save/load line items

**Files:**
- Modify: `app/domain/ports/job_repository.py`
- Modify: `app/infrastructure/repositories/sqlite_job_repo.py`
- Create: `tests/infrastructure/test_sqlite_repo_line_items.py`

- [ ] **Step 1: Viết failing tests**

```python
# tests/infrastructure/test_sqlite_repo_line_items.py
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
```

- [ ] **Step 2: Chạy test để xác nhận fail**

```bash
python -m pytest tests/infrastructure/test_sqlite_repo_line_items.py -v
```
Expected: `AttributeError: 'SQLiteJobRepository' object has no attribute 'save_line_items'`

- [ ] **Step 3: Thêm abstract methods vào port**

Mở `app/domain/ports/job_repository.py`, thêm import và 2 method:

```python
# Thêm import sau dòng "from app.domain.entities.invoice_item import InvoiceItem"
from app.domain.entities.invoice_line_item import InvoiceLineItem

# Thêm 2 method abstract vào IJobRepository:
@abstractmethod
async def save_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None: ...

@abstractmethod
async def update_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None: ...
```

- [ ] **Step 4: Implement trong SQLiteJobRepository**

Mở `app/infrastructure/repositories/sqlite_job_repo.py`.

Thêm import sau dòng `from app.domain.entities.invoice_item import InvoiceItem`:
```python
from app.domain.entities.invoice_line_item import InvoiceLineItem
```

Trong method `get()`, thêm sau block load `invoice_items` (sau dòng `job.extracted_items = ...`):
```python
async with self._db.execute(
    "SELECT * FROM invoice_line_items WHERE job_id = ?", (job_id,)
) as cur:
    job.extracted_line_items = [_row_to_line_item(r) for r in await cur.fetchall()]
```

Thêm 2 method mới vào class `SQLiteJobRepository`:
```python
async def save_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None:
    await self._db.executemany(
        """INSERT INTO invoice_line_items
           (id, job_id, invoice_symbol, invoice_number, invoice_date,
            seller_name, seller_tax_code, ten_hang_hoa, don_vi_tinh,
            so_luong, don_gia, thanh_tien, tax_rate, tax_amount)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [_line_item_to_row(job_id, li) for li in items],
    )
    await self._db.commit()

async def update_line_items(self, job_id: str, items: list[InvoiceLineItem]) -> None:
    await self._db.execute("DELETE FROM invoice_line_items WHERE job_id = ?", (job_id,))
    await self._db.commit()
    await self.save_line_items(job_id, items)
```

Thêm 2 helper function ở cuối file:
```python
def _line_item_to_row(job_id: str, li: InvoiceLineItem) -> tuple:
    return (
        li.id, job_id, li.invoice_symbol, li.invoice_number,
        li.invoice_date.isoformat(), li.seller_name, li.seller_tax_code,
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
        seller_tax_code=row["seller_tax_code"],
        ten_hang_hoa=row["ten_hang_hoa"],
        don_vi_tinh=row["don_vi_tinh"],
        so_luong=Decimal(row["so_luong"]),
        don_gia=Decimal(row["don_gia"]),
        thanh_tien=Decimal(row["thanh_tien"]),
        tax_rate=Decimal(row["tax_rate"]),
        tax_amount=Decimal(row["tax_amount"]),
    )
```

- [ ] **Step 5: Chạy test để xác nhận pass**

```bash
python -m pytest tests/infrastructure/test_sqlite_repo_line_items.py -v
```
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add app/domain/ports/job_repository.py \
        app/infrastructure/repositories/sqlite_job_repo.py \
        tests/infrastructure/test_sqlite_repo_line_items.py
git commit -m "feat: add save/load line items to repository"
```

---

## Task 3: XML parser — extract_line_items_from_xml()

**Files:**
- Modify: `app/infrastructure/parsers/xml_parser.py`
- Create: `tests/infrastructure/test_xml_line_items.py`

- [ ] **Step 1: Viết failing test**

```python
# tests/infrastructure/test_xml_line_items.py
from decimal import Decimal
from datetime import date
from app.infrastructure.parsers.xml_parser import extract_line_items_from_xml

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
  <DLHDon>
    <TTChung>
      <KHHDon>1C26TAA</KHHDon>
      <SHDon>49</SHDon>
      <NLap>2026-03-12</NLap>
    </TTChung>
    <NDHDon>
      <NBan>
        <Ten>Cty TNHH ĐT và TM Linh Chi Nguyễn</Ten>
        <MST>0901212659</MST>
      </NBan>
      <DSHHDVu>
        <HHDVu>
          <STT>1</STT>
          <THHDVu>Thép tấm 10mm</THHDVu>
          <DVTinh>Kg</DVTinh>
          <SLuong>298</SLuong>
          <DGia>28000</DGia>
          <ThTien>8344000</ThTien>
          <TSuat>10%</TSuat>
        </HHDVu>
        <HHDVu>
          <STT>2</STT>
          <THHDVu>Thép tấm 4mm</THHDVu>
          <DVTinh>Kg</DVTinh>
          <SLuong>42</SLuong>
          <DGia>28000</DGia>
          <ThTien>1176000</ThTien>
          <TSuat>10%</TSuat>
        </HHDVu>
        <HHDVu>
          <STT>3</STT>
          <THHDVu>Dịch vụ bỏ qua</THHDVu>
          <SLuong>0</SLuong>
          <DGia>0</DGia>
          <ThTien>0</ThTien>
        </HHDVu>
      </DSHHDVu>
    </NDHDon>
  </DLHDon>
</HDon>""".encode("utf-8")

def test_extract_returns_correct_count():
    items = extract_line_items_from_xml(SAMPLE_XML)
    assert len(items) == 2  # dòng SLuong=0 bị bỏ qua

def test_extract_fields_correct():
    items = extract_line_items_from_xml(SAMPLE_XML)
    first = items[0]
    assert first.ten_hang_hoa == "Thép tấm 10mm"
    assert first.don_vi_tinh == "Kg"
    assert first.so_luong == Decimal("298")
    assert first.don_gia == Decimal("28000")
    assert first.thanh_tien == Decimal("8344000")
    assert first.tax_rate == Decimal("0.10")
    assert first.invoice_symbol == "1C26TAA"
    assert first.invoice_number == "49"
    assert first.invoice_date == date(2026, 3, 12)
    assert first.seller_name == "Cty TNHH ĐT và TM Linh Chi Nguyễn"
    assert first.seller_tax_code == "0901212659"

def test_tax_amount_computed():
    items = extract_line_items_from_xml(SAMPLE_XML)
    first = items[0]
    # tax_amount = thanh_tien * tax_rate = 8344000 * 0.10 = 834400
    assert first.tax_amount == Decimal("834400.0")
```

- [ ] **Step 2: Chạy test để xác nhận fail**

```bash
python -m pytest tests/infrastructure/test_xml_line_items.py -v
```
Expected: `ImportError: cannot import name 'extract_line_items_from_xml'`

- [ ] **Step 3: Implement hàm trong xml_parser.py**

Thêm import ở đầu `app/infrastructure/parsers/xml_parser.py`:
```python
from decimal import Decimal
from datetime import date
from app.domain.entities.invoice_line_item import InvoiceLineItem
```

Thêm hàm mới ở cuối file:
```python
def _parse_tsuat(tsuat_str: str) -> Decimal:
    """Convert '10%' or '0.10' to Decimal 0.10."""
    s = tsuat_str.strip()
    if s.endswith("%"):
        return Decimal(s[:-1]) / Decimal("100")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")

def _parse_date(date_str: str) -> date:
    try:
        return date.fromisoformat(date_str)
    except Exception:
        return date.today()

def extract_line_items_from_xml(data: bytes) -> list[InvoiceLineItem]:
    root = etree.fromstring(data)

    invoice_symbol = _first_text(root, "KHHDon")
    invoice_number = _first_text(root, "SHDon")
    invoice_date = _parse_date(_first_text(root, "NLap"))

    nban = _find_elem(root, "NBan")
    seller_name = _first_text(nban, "Ten") if nban is not None else ""
    seller_tax_code = _first_text(nban, "MST") if nban is not None else ""

    items = []
    for el in root.iter():
        if _local(el) != "HHDVu":
            continue
        sluong_str = _first_text(el, "SLuong")
        try:
            sluong = Decimal(sluong_str)
        except Exception:
            sluong = Decimal("0")
        if sluong == 0:
            continue

        don_gia_str = _first_text(el, "DGia") or "0"
        thanh_tien_str = _first_text(el, "ThTien") or "0"
        tsuat_str = _first_text(el, "TSuat") or "0"

        try:
            don_gia = Decimal(don_gia_str)
        except Exception:
            don_gia = Decimal("0")
        try:
            thanh_tien = Decimal(thanh_tien_str)
        except Exception:
            thanh_tien = Decimal("0")

        tax_rate = _parse_tsuat(tsuat_str)
        tax_amount = (thanh_tien * tax_rate).quantize(Decimal("0.1"))

        items.append(InvoiceLineItem(
            invoice_symbol=invoice_symbol,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            seller_name=seller_name,
            seller_tax_code=seller_tax_code,
            ten_hang_hoa=_first_text(el, "THHDVu"),
            don_vi_tinh=_first_text(el, "DVTinh"),
            so_luong=sluong,
            don_gia=don_gia,
            thanh_tien=thanh_tien,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
        ))
    return items
```

- [ ] **Step 4: Chạy test để xác nhận pass**

```bash
python -m pytest tests/infrastructure/test_xml_line_items.py -v
```
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/parsers/xml_parser.py \
        tests/infrastructure/test_xml_line_items.py
git commit -m "feat: extract line items directly from XML HHDVu elements"
```

---

## Task 4: LLM — cập nhật prompt và return type

**Files:**
- Modify: `app/domain/ports/llm_port.py`
- Modify: `app/infrastructure/llm/ollama_client.py`
- Modify: `app/infrastructure/llm/gemini_client.py`
- Modify: `app/infrastructure/llm/fallback_client.py`

- [ ] **Step 1: Cập nhật ILLMPort**

Mở `app/domain/ports/llm_port.py`. Nội dung hiện tại:
```python
from abc import ABC, abstractmethod
from app.domain.entities.invoice_item import InvoiceItem

class ILLMPort(ABC):
    @abstractmethod
    async def extract_invoice(self, content: str) -> list[InvoiceItem]: ...
```

Thay thành:
```python
from abc import ABC, abstractmethod
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem

class ILLMPort(ABC):
    @abstractmethod
    async def extract_invoice(self, content: str) -> tuple[list[InvoiceItem], list[InvoiceLineItem]]: ...
```

- [ ] **Step 2: Cập nhật EXTRACTION_PROMPT và parse trong ollama_client.py**

Mở `app/infrastructure/llm/ollama_client.py`. Thay toàn bộ `EXTRACTION_PROMPT`:

```python
EXTRACTION_PROMPT = """Trích xuất hóa đơn điện tử Việt Nam.

Dữ liệu:
{content}

Phân loại mô tả thành một trong: vật tư | nhiên liệu | hàng hóa/dịch vụ | điện nước | tiếp khách ăn uống

Trả về JSON với 2 phần:
1. "items": gộp các dòng theo thuế suất (một item per mức thuế, cộng dồn ThTien và TThue)
2. "line_items": từng dòng hàng hóa/dịch vụ riêng lẻ

{{
  "items": [
    {{"invoice_symbol":"KHHDon","invoice_number":"SHDon","invoice_date":"DD/MM/YYYY",
      "seller_name":"NBan.Ten","seller_tax_code":"NBan.MST","description":"loại mặt hàng",
      "price_before_tax":0,"tax_rate":0.08,"price_after_tax":0}}
  ],
  "line_items": [
    {{"ten_hang_hoa":"tên mặt hàng","don_vi_tinh":"đơn vị","so_luong":1,
      "don_gia":0,"thanh_tien":0,"tax_rate":0.08,"tax_amount":0}}
  ]
}}"""
```

Thêm import ở đầu file sau `from app.domain.entities.invoice_item import InvoiceItem`:
```python
from app.domain.entities.invoice_line_item import InvoiceLineItem
```

Thay method `extract_invoice` trong `OllamaLLMClient`:
```python
async def extract_invoice(self, content: str) -> tuple[list[InvoiceItem], list[InvoiceLineItem]]:
    prompt = EXTRACTION_PROMPT.format(content=content)
    async with httpx.AsyncClient(timeout=600.0) as client:
        resp = await client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "think": False,
                "options": {"num_ctx": 4096, "num_predict": 2048},
            },
        )
        resp.raise_for_status()
    raw = resp.json()["message"]["content"]
    data = json.loads(raw)
    items = [_parse_item(i) for i in data.get("items", [])]
    line_items = [_parse_line_item(li, items) for li in data.get("line_items", [])]
    return items, line_items
```

Thêm hàm `_parse_line_item` vào cuối file:
```python
def _parse_line_item(d: dict, items: list[InvoiceItem]) -> InvoiceLineItem:
    # Kế thừa header từ items[0] nếu có
    header = items[0] if items else None
    return InvoiceLineItem(
        invoice_symbol=header.invoice_symbol if header else "",
        invoice_number=header.invoice_number if header else "",
        invoice_date=header.invoice_date if header else date.today(),
        seller_name=header.seller_name if header else "",
        seller_tax_code=header.seller_tax_code if header else "",
        ten_hang_hoa=str(d.get("ten_hang_hoa", "")),
        don_vi_tinh=str(d.get("don_vi_tinh", "")),
        so_luong=Decimal(str(d.get("so_luong", 0))),
        don_gia=Decimal(str(d.get("don_gia", 0))),
        thanh_tien=Decimal(str(d.get("thanh_tien", 0))),
        tax_rate=Decimal(str(d.get("tax_rate", 0))),
        tax_amount=Decimal(str(d.get("tax_amount", 0))),
    )
```

Thêm import ở đầu file:
```python
from app.domain.entities.invoice_line_item import InvoiceLineItem
```

- [ ] **Step 3: Cập nhật gemini_client.py**

Mở `app/infrastructure/llm/gemini_client.py`.

Thêm import:
```python
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.infrastructure.llm.ollama_client import EXTRACTION_PROMPT, _parse_item, _parse_line_item
```

Sửa `maxOutputTokens` từ `512` thành `2048`.

Thay method `extract_invoice`:
```python
async def extract_invoice(self, content: str) -> tuple[list[InvoiceItem], list[InvoiceLineItem]]:
    prompt = EXTRACTION_PROMPT.format(content=content)
    url = GEMINI_API_URL.format(model=self._model)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 2048,
        },
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = None
        for attempt in range(_MAX_RETRIES + 1):
            resp = await client.post(
                url,
                headers={"x-goog-api-key": self._api_key},
                json=payload,
            )
            if resp.status_code not in _RETRYABLE_STATUS:
                break
            if attempt == _MAX_RETRIES:
                break
            retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                wait = int(retry_after)
            else:
                wait = min(30 * (2 ** attempt), 120)
            logger.warning(
                "Gemini %d — attempt %d/%d, waiting %ds. Body: %s",
                resp.status_code, attempt + 1, _MAX_RETRIES, wait,
                resp.text[:200],
            )
            await asyncio.sleep(wait)

        resp.raise_for_status()

    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(raw)
    items = [_parse_item(i) for i in data.get("items", [])]
    line_items = [_parse_line_item(li, items) for li in data.get("line_items", [])]
    return items, line_items
```

- [ ] **Step 4: Cập nhật fallback_client.py**

Thay toàn bộ nội dung `app/infrastructure/llm/fallback_client.py`:

```python
import logging
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.ports.llm_port import ILLMPort

logger = logging.getLogger(__name__)


class FallbackLLMClient(ILLMPort):
    """Try primary LLM first; on any error, fall back to secondary."""

    def __init__(self, primary: ILLMPort, secondary: ILLMPort):
        self._primary = primary
        self._secondary = secondary

    async def extract_invoice(self, content: str) -> tuple[list[InvoiceItem], list[InvoiceLineItem]]:
        try:
            return await self._primary.extract_invoice(content)
        except Exception as exc:
            logger.warning("Primary LLM failed (%s), falling back to secondary", exc)
            return await self._secondary.extract_invoice(content)
```

- [ ] **Step 5: Commit**

```bash
git add app/domain/ports/llm_port.py \
        app/infrastructure/llm/ollama_client.py \
        app/infrastructure/llm/gemini_client.py \
        app/infrastructure/llm/fallback_client.py
git commit -m "feat: update LLM to extract line_items alongside aggregated items"
```

---

## Task 5: ProcessInvoiceUseCase — lưu line items

**Files:**
- Modify: `app/application/use_cases/process_invoice.py`
- Create: `tests/application/test_process_invoice_line_items.py`

- [ ] **Step 1: Viết failing test**

```python
# tests/application/test_process_invoice_line_items.py
import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from datetime import date
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
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
        seller_tax_code="0901212659", ten_hang_hoa="Thép tấm 10mm",
        don_vi_tinh="Kg", so_luong=Decimal("298"), don_gia=Decimal("28000"),
        thanh_tien=Decimal("8344000"), tax_rate=Decimal("0.10"),
        tax_amount=Decimal("834400"),
    )

@pytest.fixture
def use_case():
    repo = AsyncMock()
    llm = AsyncMock()
    llm.extract_invoice.return_value = ([make_item()], [make_line_item()])
    return ProcessInvoiceUseCase(repo=repo, llm=llm), repo, llm

async def test_xml_saves_line_items_from_xml_parser(use_case):
    uc, repo, llm = use_case
    fake_line_items = [make_line_item()]
    with patch(
        "app.application.use_cases.process_invoice.extract_line_items_from_xml",
        return_value=fake_line_items,
    ):
        job = await uc.execute(
            filename="hd049.xml",
            file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        )
    assert job.status == InvoiceStatus.AWAITING_REVIEW
    repo.save_line_items.assert_called_once_with(job.id, fake_line_items)

async def test_pdf_saves_line_items_from_llm(use_case):
    uc, repo, llm = use_case
    job = await uc.execute(
        filename="hd049.pdf",
        file_data=b"%PDF-1.4",
    )
    assert job.status == InvoiceStatus.AWAITING_REVIEW
    repo.save_line_items.assert_called_once()
    saved_items = repo.save_line_items.call_args[0][1]
    assert len(saved_items) == 1
    assert saved_items[0].ten_hang_hoa == "Thép tấm 10mm"
```

- [ ] **Step 2: Chạy test để xác nhận fail**

```bash
python -m pytest tests/application/test_process_invoice_line_items.py -v
```
Expected: FAIL (`save_line_items not called`)

- [ ] **Step 3: Cập nhật ProcessInvoiceUseCase**

Mở `app/application/use_cases/process_invoice.py`.

Thêm import:
```python
from app.infrastructure.parsers.xml_parser import extract_line_items_from_xml
```

Thay đoạn xử lý trong `execute()` từ dòng `if file_type == FileType.XML:` đến `await self._repo.save_items(...)`:

```python
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
await self._repo.save_line_items(job.id, line_items)
```

- [ ] **Step 4: Chạy test để xác nhận pass**

```bash
python -m pytest tests/application/test_process_invoice_line_items.py -v
```
Expected: 2 PASS

- [ ] **Step 5: Chạy toàn bộ test để kiểm tra regression**

```bash
python -m pytest tests/ -v --ignore=tests/infrastructure/test_ollama_client.py
```
Expected: tất cả PASS (test ollama_client bỏ qua vì cần server thật)

- [ ] **Step 6: Commit**

```bash
git add app/application/use_cases/process_invoice.py \
        tests/application/test_process_invoice_line_items.py
git commit -m "feat: save line items during invoice processing"
```

---

## Task 6: IExcelDetailPort + OpenpyxlDetailWriter

**Files:**
- Create: `app/domain/ports/excel_detail_port.py`
- Create: `app/infrastructure/excel/openpyxl_detail_writer.py`
- Create: `tests/infrastructure/test_excel_detail_writer.py`

- [ ] **Step 1: Viết failing test**

```python
# tests/infrastructure/test_excel_detail_writer.py
import pytest
from decimal import Decimal
from datetime import date
from io import BytesIO
import openpyxl
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.infrastructure.excel.openpyxl_detail_writer import OpenpyxlDetailWriter

TEMPLATE_PATH = "Mau_xuat_du_lieu_chi_tiet.xlsx"

def make_line_item(**kwargs):
    defaults = dict(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12),
        seller_name="Cty TNHH ĐT và TM Linh Chi Nguyễn",
        seller_tax_code="0901212659",
        ten_hang_hoa="Thép tấm 10mm", don_vi_tinh="Kg",
        so_luong=Decimal("298"), don_gia=Decimal("28000"),
        thanh_tien=Decimal("8344000"), tax_rate=Decimal("0.10"),
        tax_amount=Decimal("834400"),
    )
    defaults.update(kwargs)
    return InvoiceLineItem(**defaults)

@pytest.mark.asyncio
async def test_append_returns_filename_and_bytes():
    writer = OpenpyxlDetailWriter(template_path=TEMPLATE_PATH)
    filename, file_bytes = await writer.append_rows(
        [make_line_item()], year=2026, month=3, existing_data=b""
    )
    assert filename == "Chi_tiet_hoa_don_T3_2026.xlsx"
    assert isinstance(file_bytes, bytes) and len(file_bytes) > 0

@pytest.mark.asyncio
async def test_appended_row_contains_product_name():
    writer = OpenpyxlDetailWriter(template_path=TEMPLATE_PATH)
    _, file_bytes = await writer.append_rows(
        [make_line_item(ten_hang_hoa="TEST-PRODUCT")], year=2026, month=3, existing_data=b""
    )
    wb = openpyxl.load_workbook(BytesIO(file_bytes))
    ws = wb.active
    all_values = [ws.cell(row=r, column=c).value for r in range(1, ws.max_row + 1) for c in range(1, 15)]
    assert "TEST-PRODUCT" in all_values

@pytest.mark.asyncio
async def test_two_appends_accumulate_rows():
    writer = OpenpyxlDetailWriter(template_path=TEMPLATE_PATH)
    _, first_bytes = await writer.append_rows(
        [make_line_item(ten_hang_hoa="Hàng A")], year=2026, month=3, existing_data=b""
    )
    _, second_bytes = await writer.append_rows(
        [make_line_item(ten_hang_hoa="Hàng B")], year=2026, month=3, existing_data=first_bytes
    )
    wb = openpyxl.load_workbook(BytesIO(second_bytes))
    ws = wb.active
    all_values = [ws.cell(row=r, column=c).value for r in range(1, ws.max_row + 1) for c in range(1, 15)]
    assert "Hàng A" in all_values
    assert "Hàng B" in all_values
```

- [ ] **Step 2: Chạy test để xác nhận fail**

```bash
python -m pytest tests/infrastructure/test_excel_detail_writer.py -v
```
Expected: `ImportError: cannot import name 'OpenpyxlDetailWriter'`

- [ ] **Step 3: Tạo port**

```python
# app/domain/ports/excel_detail_port.py
from abc import ABC, abstractmethod
from app.domain.entities.invoice_line_item import InvoiceLineItem

class IExcelDetailPort(ABC):
    @abstractmethod
    async def append_rows(
        self,
        items: list[InvoiceLineItem],
        year: int,
        month: int,
        existing_data: bytes,
    ) -> tuple[str, bytes]: ...
```

- [ ] **Step 4: Implement OpenpyxlDetailWriter**

Cần xác định hàng data bắt đầu trong template. Chạy script nhỏ để kiểm tra:
```bash
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('Mau_xuat_du_lieu_chi_tiet.xlsx')
ws = wb.active
for r in range(1, 10):
    print(r, [ws.cell(row=r, column=c).value for c in range(1,15)])
"
```
Xác định hàng data đầu tiên (sau header rows) — gọi là `DATA_START_ROW`.

Từ output trên (dựa theo Excel mẫu đã đọc — hàng 1-2 là merged header, hàng 3 là tiêu đề cột, data từ hàng 6):

```python
# app/infrastructure/excel/openpyxl_detail_writer.py
import asyncio
from io import BytesIO
from decimal import Decimal
import openpyxl
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.ports.excel_detail_port import IExcelDetailPort

DATA_START_ROW = 6  # Hàng data đầu tiên trong template (sau headers)

def generate_detail_filename(month: int, year: int) -> str:
    return f"Chi_tiet_hoa_don_T{month}_{year}.xlsx"

class OpenpyxlDetailWriter(IExcelDetailPort):
    def __init__(self, template_path: str):
        self._template_path = template_path

    async def append_rows(
        self,
        items: list[InvoiceLineItem],
        year: int,
        month: int,
        existing_data: bytes,
    ) -> tuple[str, bytes]:
        filename = generate_detail_filename(month, year)
        file_bytes = await asyncio.to_thread(self._append_rows_sync, items, existing_data)
        return filename, file_bytes

    def _append_rows_sync(self, items: list[InvoiceLineItem], existing_data: bytes) -> bytes:
        if existing_data:
            wb = openpyxl.load_workbook(BytesIO(existing_data))
        else:
            wb = openpyxl.load_workbook(self._template_path)

        ws = wb.active

        # Tìm hàng cuối có dữ liệu (cột H = ten_hang_hoa)
        last_row = DATA_START_ROW - 1
        for row in range(ws.max_row, DATA_START_ROW - 1, -1):
            if ws.cell(row=row, column=8).value is not None:
                last_row = row
                break

        # STT offset
        stt_offset = 0
        for row in range(DATA_START_ROW, last_row + 1):
            v = ws.cell(row=row, column=1).value
            if isinstance(v, int):
                stt_offset = v

        for idx, li in enumerate(items, start=1):
            r = last_row + idx
            ws.cell(row=r, column=1).value = stt_offset + idx   # STT
            ws.cell(row=r, column=2).value = ""                  # Ký hiệu mẫu HĐ (trống)
            ws.cell(row=r, column=3).value = li.invoice_symbol   # Ký hiệu HĐ
            ws.cell(row=r, column=4).value = li.invoice_number   # Số HĐ
            ws.cell(row=r, column=5).value = li.invoice_date     # Ngày phát hành
            ws.cell(row=r, column=6).value = li.seller_name      # Tên nhà cung cấp
            ws.cell(row=r, column=7).value = li.seller_tax_code  # MST
            ws.cell(row=r, column=8).value = li.ten_hang_hoa     # Mặt hàng
            ws.cell(row=r, column=9).value = li.don_vi_tinh      # Đơn vị tính
            ws.cell(row=r, column=10).value = float(li.so_luong) # Số lượng
            ws.cell(row=r, column=11).value = float(li.don_gia)  # Đơn giá
            ws.cell(row=r, column=12).value = float(li.thanh_tien)  # Thành tiền
            ws.cell(row=r, column=13).value = int(li.tax_rate * 100)  # Thuế suất %
            ws.cell(row=r, column=14).value = float(li.tax_amount)    # Thuế GTGT

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()
```

- [ ] **Step 5: Chạy test để xác nhận pass**

```bash
python -m pytest tests/infrastructure/test_excel_detail_writer.py -v
```
Expected: 3 PASS. Nếu `DATA_START_ROW` sai, điều chỉnh dựa trên output của script kiểm tra ở Step 4.

- [ ] **Step 6: Commit**

```bash
git add app/domain/ports/excel_detail_port.py \
        app/infrastructure/excel/openpyxl_detail_writer.py \
        tests/infrastructure/test_excel_detail_writer.py
git commit -m "feat: add OpenpyxlDetailWriter for chi tiet Excel export"
```

---

## Task 7: ReviewAndConfirmUseCase + dependencies — wire detail export

**Files:**
- Modify: `app/application/use_cases/review_and_confirm.py`
- Modify: `app/core/dependencies.py`
- Create: `tests/application/test_review_confirm_line_items.py`

- [ ] **Step 1: Viết failing test**

```python
# tests/application/test_review_confirm_line_items.py
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

async def test_confirm_calls_detail_writer(use_case):
    uc, repo, storage, excel, excel_detail = use_case
    line_items = [make_line_item()]
    await uc.confirm(job_id="job-1", updated_items=[make_item()], updated_line_items=line_items)
    excel_detail.append_rows.assert_called_once()
    call_args = excel_detail.append_rows.call_args[0]
    assert call_args[0] == line_items  # items passed correctly

async def test_confirm_uploads_detail_excel(use_case):
    uc, repo, storage, excel, excel_detail = use_case
    await uc.confirm(job_id="job-1", updated_items=[make_item()], updated_line_items=[make_line_item()])
    upload_calls = storage.upload_file.call_args_list
    uploaded_keys = [c[0][1] for c in upload_calls]
    assert any("Chi_tiet" in k for k in uploaded_keys)
```

- [ ] **Step 2: Chạy test để xác nhận fail**

```bash
python -m pytest tests/application/test_review_confirm_line_items.py -v
```
Expected: FAIL (`ReviewAndConfirmUseCase.__init__() got unexpected keyword argument 'excel_detail'`)

- [ ] **Step 3: Cập nhật ReviewAndConfirmUseCase**

Thay toàn bộ nội dung `app/application/use_cases/review_and_confirm.py`:

```python
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.entities.processing_job import ProcessingJob
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_port import IExcelPort
from app.domain.ports.excel_detail_port import IExcelDetailPort
from app.domain.value_objects.invoice_status import InvoiceStatus

class ReviewAndConfirmUseCase:
    def __init__(
        self,
        repo: IJobRepository,
        storage: IStoragePort,
        excel: IExcelPort,
        excel_detail: IExcelDetailPort,
        bucket_invoices: str,
        bucket_exports: str,
    ):
        self._repo = repo
        self._storage = storage
        self._excel = excel
        self._excel_detail = excel_detail
        self._bucket_invoices = bucket_invoices
        self._bucket_exports = bucket_exports

    async def confirm(
        self,
        job_id: str,
        updated_items: list[InvoiceItem],
        updated_line_items: list[InvoiceLineItem],
    ) -> ProcessingJob:
        import os
        job = await self._repo.get(job_id)
        await self._repo.update_items(job_id, updated_items)
        await self._repo.update_line_items(job_id, updated_line_items)

        pending_path = job.pending_file_path
        if pending_path and os.path.exists(pending_path):
            with open(pending_path, "rb") as f:
                file_data = f.read()
        else:
            file_data = b""

        first = updated_items[0]
        year, month = first.invoice_date.year, first.invoice_date.month
        customer = first.seller_name.replace("/", "-").replace(" ", "_")[:50]
        ext = job.filename.rsplit(".", 1)[-1]
        storage_key = f"{year}/{month:02d}/{customer}/{first.invoice_number}.{ext}"
        await self._storage.upload_file(
            self._bucket_invoices, storage_key, file_data,
            "application/pdf" if ext == "pdf" else "application/xml",
        )

        if pending_path and os.path.exists(pending_path):
            os.unlink(pending_path)
        await self._repo.add_source_path(job_id, storage_key)

        # Export Excel tổng hợp
        xls_key = f"Bang_ke_thue_{year}_{month:02d}.xlsx"
        try:
            existing_xls = await self._storage.download_file(self._bucket_exports, xls_key)
        except Exception:
            existing_xls = b""
        _, xls_bytes = await self._excel.append_rows(updated_items, year, month, existing_xls)
        await self._storage.upload_file(
            self._bucket_exports, xls_key, xls_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Export Excel chi tiết
        detail_key = f"Chi_tiet_hoa_don_T{month}_{year}.xlsx"
        try:
            existing_detail = await self._storage.download_file(self._bucket_exports, detail_key)
        except Exception:
            existing_detail = b""
        _, detail_bytes = await self._excel_detail.append_rows(
            updated_line_items, year, month, existing_detail
        )
        await self._storage.upload_file(
            self._bucket_exports, detail_key, detail_bytes,
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

- [ ] **Step 4: Cập nhật dependencies.py**

Mở `app/core/dependencies.py`.

Thêm import:
```python
from app.infrastructure.excel.openpyxl_detail_writer import OpenpyxlDetailWriter
from app.domain.ports.excel_detail_port import IExcelDetailPort
```

Thêm factory function (sau `get_excel()`):
```python
def get_excel_detail() -> OpenpyxlDetailWriter:
    return OpenpyxlDetailWriter(template_path="Mau_xuat_du_lieu_chi_tiet.xlsx")
```

Cập nhật `get_review_confirm_uc()`:
```python
def get_review_confirm_uc(
    repo=Depends(get_job_repo),
    storage=Depends(get_storage),
    excel=Depends(get_excel),
    excel_detail=Depends(get_excel_detail),
    settings: Settings = Depends(get_settings),
) -> ReviewAndConfirmUseCase:
    return ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices=settings.rustfs_bucket_invoices,
        bucket_exports=settings.rustfs_bucket_exports,
    )
```

- [ ] **Step 5: Chạy test để xác nhận pass**

```bash
python -m pytest tests/application/test_review_confirm_line_items.py -v
```
Expected: 2 PASS

- [ ] **Step 6: Fix existing test_review_and_confirm.py**

Test cũ sẽ bị break vì `ReviewAndConfirmUseCase` thay đổi constructor và `confirm()` signature. Thay toàn bộ nội dung `tests/application/test_review_and_confirm.py`:

```python
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

async def test_confirm_job_sets_confirmed_status(tmp_path):
    repo = AsyncMock()
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

async def test_reject_job_sets_rejected_status():
    repo = AsyncMock()
    job = make_job_with_items()
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(
        repo=repo, storage=AsyncMock(), excel=AsyncMock(), excel_detail=AsyncMock(),
        bucket_invoices="i", bucket_exports="e",
    )
    result = await uc.reject(job_id=job.id)
    assert result.status == InvoiceStatus.REJECTED
    repo.update_status.assert_called_with(job.id, InvoiceStatus.REJECTED)
```

- [ ] **Step 7: Chạy toàn bộ test**

```bash
python -m pytest tests/ -v --ignore=tests/infrastructure/test_ollama_client.py
```
Expected: tất cả PASS

- [ ] **Step 8: Commit**

```bash
git add app/application/use_cases/review_and_confirm.py \
        app/core/dependencies.py \
        tests/application/test_review_confirm_line_items.py
git commit -m "feat: wire detail Excel export into confirm use case"
```

---

## Task 8: API Schemas — thêm InvoiceLineItemSchema

**Files:**
- Modify: `app/presentation/api/schemas.py`

- [ ] **Step 1: Cập nhật schemas.py**

Mở `app/presentation/api/schemas.py`. Thêm class mới và cập nhật `JobResponse`:

```python
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

class InvoiceLineItemSchema(BaseModel):
    id: str
    invoice_symbol: str
    invoice_number: str
    invoice_date: date
    seller_name: str
    seller_tax_code: str
    ten_hang_hoa: str
    don_vi_tinh: str
    so_luong: Decimal
    don_gia: Decimal
    thanh_tien: Decimal
    tax_rate: Decimal
    tax_amount: Decimal

class JobResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    status: str
    created_at: datetime
    extracted_items: list[InvoiceItemSchema]
    extracted_line_items: list[InvoiceLineItemSchema]
    source_paths: list[str]
    error: Optional[str]

class ReviewRequest(BaseModel):
    items: list[InvoiceItemSchema]
```

- [ ] **Step 2: Commit**

```bash
git add app/presentation/api/schemas.py
git commit -m "feat: add InvoiceLineItemSchema to API schemas"
```

---

## Task 9: Web Router — parse line items từ form confirm

**Files:**
- Modify: `app/presentation/web/router.py`

- [ ] **Step 1: Cập nhật confirm handler**

Mở `app/presentation/web/router.py`. Thay toàn bộ handler `web_confirm`:

```python
@router.post("/jobs/{job_id}/confirm")
async def web_confirm(job_id: str, request: Request, repo=Depends(get_job_repo),
                      confirm_uc=Depends(get_review_confirm_uc)):
    form = await request.form()
    job = await repo.get(job_id)
    from app.domain.entities.invoice_item import InvoiceItem
    from app.domain.entities.invoice_line_item import InvoiceLineItem
    from decimal import Decimal
    from datetime import date

    # Parse invoice items (giữ nguyên như cũ)
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

    # Parse line items từ form
    line_items = []
    for li in job.extracted_line_items:
        line_items.append(InvoiceLineItem(
            id=li.id,
            invoice_symbol=li.invoice_symbol,
            invoice_number=li.invoice_number,
            invoice_date=li.invoice_date,
            seller_name=li.seller_name,
            seller_tax_code=li.seller_tax_code,
            ten_hang_hoa=form.get(f"li_ten_hang_hoa_{li.id}", li.ten_hang_hoa),
            don_vi_tinh=form.get(f"li_don_vi_tinh_{li.id}", li.don_vi_tinh),
            so_luong=Decimal(form.get(f"li_so_luong_{li.id}", str(li.so_luong))),
            don_gia=Decimal(form.get(f"li_don_gia_{li.id}", str(li.don_gia))),
            thanh_tien=Decimal(form.get(f"li_thanh_tien_{li.id}", str(li.thanh_tien))),
            tax_rate=Decimal(form.get(f"li_tax_rate_{li.id}", str(li.tax_rate))),
            tax_amount=Decimal(form.get(f"li_tax_amount_{li.id}", str(li.tax_amount))),
        ))

    await confirm_uc.confirm(job_id=job_id, updated_items=items, updated_line_items=line_items)
    return RedirectResponse("/jobs", status_code=303)
```

- [ ] **Step 2: Commit**

```bash
git add app/presentation/web/router.py
git commit -m "feat: parse line items from confirm form"
```

---

## Task 10: Review page — bảng chi tiết chỉnh sửa được

**Files:**
- Modify: `app/presentation/web/templates/review.html`

- [ ] **Step 1: Thêm CSS cho bảng chi tiết**

Trong `review.html`, thêm vào block `<style>` (trước thẻ đóng `</style>`):

```css
.line-items-section {
  margin-top: 20px;
  padding: 0 0 24px;
}
.line-items-header {
  font-size: 12px;
  font-weight: 700;
  color: #495057;
  text-transform: uppercase;
  letter-spacing: .5px;
  padding: 10px 14px;
  background: #e9ecef;
  border-radius: 6px 6px 0 0;
  border: 1px solid #dee2e6;
  display: flex;
  align-items: center;
  gap: 8px;
}
.line-items-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  border: 1px solid #dee2e6;
  border-top: none;
  border-radius: 0 0 6px 6px;
  overflow: hidden;
}
.line-items-table th {
  background: #f8f9fa;
  padding: 6px 8px;
  text-align: left;
  font-size: 10px;
  font-weight: 700;
  color: #6c757d;
  text-transform: uppercase;
  letter-spacing: .3px;
  border-bottom: 1px solid #dee2e6;
  white-space: nowrap;
}
.line-items-table td {
  padding: 4px 5px;
  border-bottom: 1px solid #f0f0f0;
  vertical-align: middle;
}
.line-items-table tr:last-child td { border-bottom: none; }
.li-input {
  width: 100%;
  font-size: 12px;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  padding: 3px 6px;
  background: #fff;
  min-width: 60px;
}
.li-input:focus {
  outline: none;
  border-color: #0d6efd;
  box-shadow: 0 0 0 2px rgba(13,110,253,.1);
}
.li-input.num { font-family: monospace; text-align: right; }
.li-name { min-width: 140px; }
.badge-count {
  font-size: 10px;
  background: #0d6efd;
  color: #fff;
  padding: 2px 7px;
  border-radius: 10px;
  font-weight: 700;
}
```

- [ ] **Step 2: Thêm bảng chi tiết vào cột phải của form**

Trong `review.html`, thêm đoạn HTML này ngay **trước** `<div class="action-bar">`:

```html
{% if job.extracted_line_items %}
<div class="p-3">
  <div class="line-items-section">
    <div class="line-items-header">
      Chi tiết hàng hóa / Dịch vụ
      <span class="badge-count">{{ job.extracted_line_items | length }} dòng</span>
    </div>
    <div style="overflow-x: auto;">
      <table class="line-items-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Tên hàng hóa / Dịch vụ</th>
            <th>ĐVT</th>
            <th>SL</th>
            <th>Đơn giá</th>
            <th>Thành tiền</th>
            <th>TS%</th>
            <th>Thuế GTGT</th>
          </tr>
        </thead>
        <tbody>
          {% for li in job.extracted_line_items %}
          <tr>
            <td style="color:#aaa; font-size:11px;">{{ loop.index }}</td>
            <td>
              <input class="li-input li-name" type="text"
                     name="li_ten_hang_hoa_{{ li.id }}" value="{{ li.ten_hang_hoa }}">
            </td>
            <td>
              <input class="li-input" type="text" style="min-width:50px;"
                     name="li_don_vi_tinh_{{ li.id }}" value="{{ li.don_vi_tinh }}">
            </td>
            <td>
              <input class="li-input num" type="text" style="min-width:55px;"
                     name="li_so_luong_{{ li.id }}" value="{{ li.so_luong }}"
                     data-row="{{ li.id }}" oninput="recalc('{{ li.id }}')">
            </td>
            <td>
              <input class="li-input num" type="text" style="min-width:80px;"
                     name="li_don_gia_{{ li.id }}" value="{{ li.don_gia }}"
                     data-row="{{ li.id }}" oninput="recalc('{{ li.id }}')">
            </td>
            <td>
              <input class="li-input num" type="text" style="min-width:90px;"
                     name="li_thanh_tien_{{ li.id }}" id="li_thanh_tien_{{ li.id }}"
                     value="{{ li.thanh_tien }}" readonly style="background:#f8f9fa;">
            </td>
            <td>
              <input class="li-input num" type="text" style="min-width:45px;"
                     name="li_tax_rate_{{ li.id }}" value="{{ li.tax_rate }}">
            </td>
            <td>
              <input class="li-input num" type="text" style="min-width:85px;"
                     name="li_tax_amount_{{ li.id }}" id="li_tax_amount_{{ li.id }}"
                     value="{{ li.tax_amount }}">
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endif %}
```

- [ ] **Step 3: Thêm JavaScript auto-calc**

Thêm đoạn script này vào cuối `review.html`, trước `{% endblock %}`:

```html
<script>
function recalc(rowId) {
  var sl = parseFloat(document.querySelector('[name="li_so_luong_' + rowId + '"]').value) || 0;
  var dg = parseFloat(document.querySelector('[name="li_don_gia_' + rowId + '"]').value) || 0;
  var tt = sl * dg;
  var ttEl = document.getElementById('li_thanh_tien_' + rowId);
  if (ttEl) ttEl.value = tt.toFixed(0);
}
</script>
```

- [ ] **Step 4: Commit**

```bash
git add app/presentation/web/templates/review.html
git commit -m "feat: add editable line items table to review page"
```

---

## Task 11: Chạy toàn bộ test suite và smoke test

- [ ] **Step 1: Chạy tất cả tests**

```bash
python -m pytest tests/ -v --ignore=tests/infrastructure/test_ollama_client.py
```
Expected: tất cả PASS

- [ ] **Step 2: Kiểm tra app khởi động được**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -c "from app.main import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Kiểm tra DB migration chạy đúng**

```bash
python -c "
import asyncio
from app.core.database import init_db, get_db, close_db

async def check():
    await init_db()
    db = await get_db()
    async with db.execute(\"SELECT name FROM sqlite_master WHERE type='table'\") as cur:
        tables = [r[0] for r in await cur.fetchall()]
    print('Tables:', tables)
    await close_db()

asyncio.run(check())
"
```
Expected: output bao gồm `jobs`, `invoice_items`, `invoice_line_items`

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: invoice line items — full feature complete" --allow-empty
```
