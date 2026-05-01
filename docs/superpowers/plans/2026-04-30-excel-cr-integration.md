# Excel-CR Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Excel-CR (expense aggregation → Chỉ tiêu mapping → Excel output) as a self-contained module inside the running `collect_invoice` FastAPI backend.

**Architecture:** New feature module under `/excel-cr/*` routes sharing RustFS storage, SQLite DB, and Gemini/Ollama LLM client. No existing code modified except `main.py`, `database.py`, `dependencies.py`, `config.py`, and `pyproject.toml`.

**Tech Stack:** FastAPI, pandas, pdfplumber, openpyxl, aiosqlite, boto3 (RustFS), Gemini/Ollama via existing LLM client.

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `app/domain/entities/excel_cr_session.py` | Session dataclass |
| `app/domain/ports/excel_cr_rule_port.py` | Abstract rules R/W interface |
| `app/application/use_cases/excel_cr/__init__.py` | Package marker |
| `app/application/use_cases/excel_cr/upload_source.py` | Parse + store source file in RustFS, create session |
| `app/application/use_cases/excel_cr/aggregate_and_match.py` | pandas groupby + 3-tier rule matching |
| `app/application/use_cases/excel_cr/llm_classify.py` | LLM classify unmatched rows |
| `app/application/use_cases/excel_cr/confirm_mappings.py` | Save decisions, update rules.json |
| `app/application/use_cases/excel_cr/download_result.py` | Write Excel output to RustFS, return bytes |
| `app/infrastructure/parsers/excel_cr_source_parser.py` | Read CSV/XLS with pandas, PDF with pdfplumber → DataFrame |
| `app/infrastructure/excel/excel_cr_writer.py` | openpyxl: fill template cells from aggregated data |
| `app/infrastructure/rules/rustfs_rules_manager.py` | rules.json R/W via RustFS |
| `app/infrastructure/llm/excel_cr_classifier.py` | Gemini/Ollama prompt for expense classification |
| `app/infrastructure/repositories/sqlite_excel_cr_repo.py` | Session CRUD |
| `app/presentation/api/excel_cr_router.py` | FastAPI router: `/excel-cr/*` endpoints |
| `app/presentation/web/excel_cr_web.py` | Serve `index.html` at `/excel-cr/` |
| `app/static/excel_cr/index.html` | Frontend: 3-state SPA |
| `tests/test_excel_cr_parser.py` | Parser unit tests |
| `tests/test_excel_cr_rules.py` | Rule matching unit tests |
| `tests/test_excel_cr_classifier.py` | Classifier prompt unit tests |
| `tests/test_excel_cr_writer.py` | Writer unit tests |

### Modified files
| File | Change |
|---|---|
| `pyproject.toml` | Add `pdfplumber` dependency |
| `app/core/config.py` | Add `excel_cr_bucket: str` setting |
| `app/core/database.py` | Add `excel_cr_sessions` table + migration |
| `app/core/dependencies.py` | Add Excel-CR singletons + dependency getters |
| `app/main.py` | Mount `excel_cr_router`, init `excel-cr` bucket |

---

## Task 1: Add pdfplumber dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pdfplumber to pyproject.toml**

Open `pyproject.toml` and add `pdfplumber = ">=0.11"` to `[tool.poetry.dependencies]` (same section as `openpyxl`).

- [ ] **Step 2: Install**

```bash
cd /Users/quangdung/Documents/collect_invoice
poetry add pdfplumber
```

Expected: `pdfplumber` added to `poetry.lock`.

- [ ] **Step 3: Verify import**

```bash
poetry run python -c "import pdfplumber; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "chore: add pdfplumber dependency for Excel-CR PDF parsing"
```

---

## Task 2: SQLite schema — excel_cr_sessions table

**Files:**
- Modify: `app/core/database.py`
- Test: `tests/test_excel_cr_db.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_excel_cr_db.py`:

```python
import asyncio
import pytest
import aiosqlite
from app.core.database import init_db, get_db, close_db

@pytest.mark.asyncio
async def test_excel_cr_sessions_table_exists(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)

    # Reset singleton
    import app.core.database as db_module
    db_module._db_connection = None

    await init_db()
    db = await get_db()
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='excel_cr_sessions'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None, "excel_cr_sessions table must exist"
    await close_db()
    db_module._db_connection = None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_excel_cr_db.py -v
```

Expected: FAIL — `excel_cr_sessions` table does not exist yet.

- [ ] **Step 3: Add table DDL and migration to database.py**

Add after `CREATE_INVOICE_LINE_ITEMS_TABLE` constant:

```python
CREATE_EXCEL_CR_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS excel_cr_sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    source_file_key TEXT,
    template_key TEXT,
    aggregated_data TEXT,
    match_results TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
```

In `init_db()`, after the existing `await db.execute(CREATE_INVOICE_LINE_ITEMS_TABLE)` line, add:

```python
    await db.execute(CREATE_EXCEL_CR_SESSIONS_TABLE)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
poetry run pytest tests/test_excel_cr_db.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/database.py tests/test_excel_cr_db.py
git commit -m "feat: add excel_cr_sessions table to SQLite schema"
```

---

## Task 3: Domain entity + port

**Files:**
- Create: `app/domain/entities/excel_cr_session.py`
- Create: `app/domain/ports/excel_cr_rule_port.py`

- [ ] **Step 1: Create ExcelCrSession entity**

```python
# app/domain/entities/excel_cr_session.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid

@dataclass
class ExcelCrSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"          # pending|aggregated|reviewed|done
    source_file_key: str | None = None
    template_key: str | None = None
    aggregated_data: list[dict[str, Any]] | None = None
    match_results: list[dict[str, Any]] | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

- [ ] **Step 2: Create IExcelCrRulePort**

```python
# app/domain/ports/excel_cr_rule_port.py
from abc import ABC, abstractmethod
from typing import Any

class IExcelCrRulePort(ABC):
    @abstractmethod
    async def load(self) -> dict[str, Any]: ...

    @abstractmethod
    async def save(self, rules: dict[str, Any]) -> None: ...
```

- [ ] **Step 3: Commit**

```bash
git add app/domain/entities/excel_cr_session.py app/domain/ports/excel_cr_rule_port.py
git commit -m "feat: add ExcelCrSession entity and IExcelCrRulePort"
```

---

## Task 4: Source parser (CSV / XLS / PDF)

**Files:**
- Create: `app/infrastructure/parsers/excel_cr_source_parser.py`
- Test: `tests/test_excel_cr_parser.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_excel_cr_parser.py`:

```python
import io
import pytest
import pandas as pd
from app.infrastructure.parsers.excel_cr_source_parser import parse_source_file

def _make_csv_bytes(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue()

SAMPLE_ROWS = [
    {"Tháng": 1, "Ngày": "2025-01-02", "Diễn giải": "Thưởng sáng kiến", "TK": 111,
     "Số tiền": 58_900_000, "Khoản mục": "cpk", "TK cp": ""},
    {"Tháng": 1, "Ngày": "2025-01-15", "Diễn giải": "Trợ cấp TNLĐ", "TK": 111,
     "Số tiền": 9_336_600, "Khoản mục": "cpk", "TK cp": ""},
    {"Tháng": 2, "Ngày": "2025-02-05", "Diễn giải": "Thưởng sáng kiến", "TK": 111,
     "Số tiền": 12_000_000, "Khoản mục": "cpk", "TK cp": ""},
]

def test_parse_csv_returns_dataframe():
    data = _make_csv_bytes(SAMPLE_ROWS)
    df = parse_source_file(data, "chi_phi.csv")
    assert list(df.columns) == ["thang", "dien_giai", "so_tien", "khoan_muc"]

def test_parse_csv_row_count():
    data = _make_csv_bytes(SAMPLE_ROWS)
    df = parse_source_file(data, "chi_phi.csv")
    assert len(df) == 3

def test_parse_csv_so_tien_numeric():
    data = _make_csv_bytes(SAMPLE_ROWS)
    df = parse_source_file(data, "chi_phi.csv")
    assert df["so_tien"].dtype.kind in ("f", "i")

def test_parse_csv_strips_numeric_khoan_muc():
    rows = SAMPLE_ROWS + [
        {"Tháng": 1, "Ngày": "2025-01-03", "Diễn giải": "Header row",
         "TK": 111, "Số tiền": 0, "Khoản mục": "123", "TK cp": ""}
    ]
    data = _make_csv_bytes(rows)
    df = parse_source_file(data, "chi_phi.csv")
    # row with numeric Khoản mục is dropped
    assert len(df) == 3

def test_parse_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        parse_source_file(b"data", "file.txt")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_excel_cr_parser.py -v
```

Expected: FAIL — `parse_source_file` not defined.

- [ ] **Step 3: Implement parser**

```python
# app/infrastructure/parsers/excel_cr_source_parser.py
import io
import logging
import pandas as pd

logger = logging.getLogger(__name__)

_COLUMN_MAP = {
    "tháng": "thang",
    "diễn giải": "dien_giai",
    "số tiền": "so_tien",
    "khoản mục": "khoan_muc",
}


def parse_source_file(data: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV/XLS/XLSX/PDF source file → normalized DataFrame.

    Returns columns: thang (int), dien_giai (str), so_tien (float), khoan_muc (str).
    Drops rows with purely numeric khoan_muc (totals/headers).
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        df = _read_csv(data)
    elif ext in ("xls", "xlsx"):
        df = _read_excel(data, ext)
    elif ext == "pdf":
        df = _read_pdf(data)
    else:
        raise ValueError(f"Unsupported file extension: .{ext}")

    df = _normalize(df)
    return df


def _read_csv(data: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode CSV — unsupported encoding")


def _read_excel(data: bytes, ext: str) -> pd.DataFrame:
    engine = "xlrd" if ext == "xls" else "openpyxl"
    return pd.read_excel(io.BytesIO(data), engine=engine)


def _read_pdf(data: bytes) -> pd.DataFrame:
    import pdfplumber
    frames = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                header, *rows = table
                frames.append(pd.DataFrame(rows, columns=header))
    if not frames:
        raise ValueError("No tables found in PDF — scan-only PDF not supported")
    return pd.concat(frames, ignore_index=True)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().lower() for c in df.columns]
    rename = {}
    for col in df.columns:
        for pattern, target in _COLUMN_MAP.items():
            if pattern in col:
                rename[col] = target
                break
    df = df.rename(columns=rename)

    required = {"thang", "dien_giai", "so_tien", "khoan_muc"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[list(required)].copy()

    # Drop rows where khoan_muc is purely numeric (totals/headers)
    df = df[~df["khoan_muc"].astype(str).str.strip().str.match(r"^\d+$")]

    df["so_tien"] = pd.to_numeric(
        df["so_tien"].astype(str).str.replace(",", "").str.replace(" ", ""),
        errors="coerce",
    ).fillna(0.0)

    df["thang"] = pd.to_numeric(df["thang"], errors="coerce").fillna(0).astype(int)
    df["dien_giai"] = df["dien_giai"].astype(str).str.strip()
    df["khoan_muc"] = df["khoan_muc"].astype(str).str.strip().str.lower()

    return df.reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_excel_cr_parser.py -v
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/parsers/excel_cr_source_parser.py tests/test_excel_cr_parser.py
git commit -m "feat: add Excel-CR source file parser (CSV/XLS/PDF)"
```

---

## Task 5: RustFS rules manager

**Files:**
- Create: `app/infrastructure/rules/rustfs_rules_manager.py`
- Create: `app/infrastructure/rules/__init__.py`
- Test: `tests/test_excel_cr_rules.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_excel_cr_rules.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.infrastructure.rules.rustfs_rules_manager import RustfsRulesManager

BUCKET = "excel-cr"
RULES_KEY = "config/rules.json"

DEFAULT_RULES = {"llm_confirmed": [], "keyword": [], "direct": []}

@pytest.mark.asyncio
async def test_load_returns_default_when_not_found():
    storage = MagicMock()
    storage.download_file = AsyncMock(side_effect=Exception("NoSuchKey"))
    mgr = RustfsRulesManager(storage, BUCKET)
    rules = await mgr.load()
    assert rules == DEFAULT_RULES

@pytest.mark.asyncio
async def test_load_returns_stored_rules():
    stored = {"llm_confirmed": [{"dien_giai": "foo", "chi_tieu": "bar"}], "keyword": [], "direct": []}
    storage = MagicMock()
    storage.download_file = AsyncMock(return_value=json.dumps(stored).encode())
    mgr = RustfsRulesManager(storage, BUCKET)
    rules = await mgr.load()
    assert rules["llm_confirmed"][0]["dien_giai"] == "foo"

@pytest.mark.asyncio
async def test_save_uploads_json():
    storage = MagicMock()
    storage.upload_file = AsyncMock(return_value=RULES_KEY)
    mgr = RustfsRulesManager(storage, BUCKET)
    rules = {"llm_confirmed": [], "keyword": [], "direct": []}
    await mgr.save(rules)
    storage.upload_file.assert_called_once()
    call_args = storage.upload_file.call_args
    assert call_args[0][0] == BUCKET
    assert call_args[0][1] == RULES_KEY
    saved = json.loads(call_args[0][2])
    assert saved == rules
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_excel_cr_rules.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create `__init__.py`**

```python
# app/infrastructure/rules/__init__.py
```

- [ ] **Step 4: Implement RustfsRulesManager**

```python
# app/infrastructure/rules/rustfs_rules_manager.py
import json
import logging
from typing import Any
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.domain.ports.storage_port import IStoragePort

logger = logging.getLogger(__name__)

_DEFAULT_RULES: dict[str, Any] = {
    "llm_confirmed": [],
    "keyword": [],
    "direct": [],
}
_RULES_KEY = "config/rules.json"


class RustfsRulesManager(IExcelCrRulePort):
    def __init__(self, storage: IStoragePort, bucket: str):
        self._storage = storage
        self._bucket = bucket

    async def load(self) -> dict[str, Any]:
        try:
            data = await self._storage.download_file(self._bucket, _RULES_KEY)
            return json.loads(data)
        except Exception:
            logger.info("rules.json not found in RustFS — returning defaults")
            return dict(_DEFAULT_RULES)

    async def save(self, rules: dict[str, Any]) -> None:
        data = json.dumps(rules, ensure_ascii=False, indent=2).encode("utf-8")
        await self._storage.upload_file(self._bucket, _RULES_KEY, data, "application/json")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_excel_cr_rules.py -v
```

Expected: All 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/infrastructure/rules/ tests/test_excel_cr_rules.py
git commit -m "feat: add RustfsRulesManager for Excel-CR rules.json"
```

---

## Task 6: SQLite session repository

**Files:**
- Create: `app/infrastructure/repositories/sqlite_excel_cr_repo.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_excel_cr_db.py`:

```python
import json
from datetime import datetime
from app.domain.entities.excel_cr_session import ExcelCrSession
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository

@pytest.mark.asyncio
async def test_session_save_and_get(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test2.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    import app.core.database as db_module
    db_module._db_connection = None

    await init_db()
    db = await get_db()
    repo = SQLiteExcelCrRepository(db)

    session = ExcelCrSession()
    session.source_file_key = "excel-cr/uploads/abc/source.csv"
    await repo.save(session)

    loaded = await repo.get(session.id)
    assert loaded is not None
    assert loaded.source_file_key == "excel-cr/uploads/abc/source.csv"
    assert loaded.status == "pending"

    await close_db()
    db_module._db_connection = None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_excel_cr_db.py::test_session_save_and_get -v
```

Expected: FAIL.

- [ ] **Step 3: Implement repository**

```python
# app/infrastructure/repositories/sqlite_excel_cr_repo.py
import json
from datetime import datetime
from typing import Optional
import aiosqlite
from app.domain.entities.excel_cr_session import ExcelCrSession


class SQLiteExcelCrRepository:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def save(self, session: ExcelCrSession) -> None:
        await self._db.execute(
            """INSERT INTO excel_cr_sessions
               (id, status, source_file_key, template_key,
                aggregated_data, match_results, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                session.id,
                session.status,
                session.source_file_key,
                session.template_key,
                json.dumps(session.aggregated_data) if session.aggregated_data is not None else None,
                json.dumps(session.match_results) if session.match_results is not None else None,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get(self, session_id: str) -> Optional[ExcelCrSession]:
        async with self._db.execute(
            "SELECT * FROM excel_cr_sessions WHERE id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return ExcelCrSession(
            id=row["id"],
            status=row["status"],
            source_file_key=row["source_file_key"],
            template_key=row["template_key"],
            aggregated_data=json.loads(row["aggregated_data"]) if row["aggregated_data"] else None,
            match_results=json.loads(row["match_results"]) if row["match_results"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def update(self, session: ExcelCrSession) -> None:
        session.updated_at = datetime.utcnow()
        await self._db.execute(
            """UPDATE excel_cr_sessions
               SET status=?, source_file_key=?, template_key=?,
                   aggregated_data=?, match_results=?, updated_at=?
               WHERE id=?""",
            (
                session.status,
                session.source_file_key,
                session.template_key,
                json.dumps(session.aggregated_data) if session.aggregated_data is not None else None,
                json.dumps(session.match_results) if session.match_results is not None else None,
                session.updated_at.isoformat(),
                session.id,
            ),
        )
        await self._db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_excel_cr_db.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/repositories/sqlite_excel_cr_repo.py tests/test_excel_cr_db.py
git commit -m "feat: add SQLiteExcelCrRepository for session persistence"
```

---

## Task 7: Aggregate and match use case

**Files:**
- Create: `app/application/use_cases/excel_cr/__init__.py`
- Create: `app/application/use_cases/excel_cr/aggregate_and_match.py`

The `match_rules()` function applies 3-tier matching:
1. `llm_confirmed`: exact `dien_giai` match
2. `keyword`: `khoan_muc` match AND any keyword in `dien_giai`
3. `direct`: `khoan_muc` match only

- [ ] **Step 1: Write failing tests**

Create `tests/test_excel_cr_aggregate.py`:

```python
import pytest
from app.application.use_cases.excel_cr.aggregate_and_match import (
    aggregate_rows, match_rules, AggregatedRow
)

SAMPLE_ROWS = [
    {"thang": 1, "dien_giai": "Thưởng sáng kiến", "so_tien": 58_900_000.0, "khoan_muc": "cpk"},
    {"thang": 1, "dien_giai": "Trợ cấp TNLĐ",     "so_tien":  9_336_600.0, "khoan_muc": "cpk"},
    {"thang": 1, "dien_giai": "Thưởng sáng kiến", "so_tien": 12_000_000.0, "khoan_muc": "cpk"},
    {"thang": 2, "dien_giai": "Thưởng sáng kiến", "so_tien":  5_000_000.0, "khoan_muc": "cpk"},
]

RULES = {
    "llm_confirmed": [{"dien_giai": "Thưởng sáng kiến", "chi_tieu": "Chi khác"}],
    "keyword": [{"khoan_muc": "cpk", "keywords": ["trợ cấp"], "chi_tieu": "Chi phí lao động"}],
    "direct": [],
}

def test_aggregate_sums_same_thang_dien_giai():
    rows = aggregate_rows(SAMPLE_ROWS)
    t1_thuong = [r for r in rows if r.thang == 1 and r.dien_giai == "Thưởng sáng kiến"]
    assert len(t1_thuong) == 1
    assert t1_thuong[0].so_tien == pytest.approx(70_900_000.0)

def test_aggregate_keeps_separate_thang():
    rows = aggregate_rows(SAMPLE_ROWS)
    months = {r.thang for r in rows}
    assert months == {1, 2}

def test_match_llm_confirmed():
    rows = aggregate_rows(SAMPLE_ROWS)
    matched, unmatched = match_rules(rows, RULES)
    thuong = [r for r in matched if r.dien_giai == "Thưởng sáng kiến"]
    assert all(r.chi_tieu == "Chi khác" for r in thuong)

def test_match_keyword():
    rows = aggregate_rows(SAMPLE_ROWS)
    matched, unmatched = match_rules(rows, RULES)
    trocap = [r for r in matched if "Trợ cấp" in r.dien_giai]
    assert len(trocap) == 1
    assert trocap[0].chi_tieu == "Chi phí lao động"

def test_unmatched_rows_have_no_chi_tieu():
    rules_empty = {"llm_confirmed": [], "keyword": [], "direct": []}
    rows = aggregate_rows(SAMPLE_ROWS)
    _, unmatched = match_rules(rows, rules_empty)
    assert len(unmatched) == len(rows)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_excel_cr_aggregate.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create package `__init__.py`**

```python
# app/application/use_cases/excel_cr/__init__.py
```

- [ ] **Step 4: Implement aggregate_and_match**

```python
# app/application/use_cases/excel_cr/aggregate_and_match.py
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AggregatedRow:
    thang: int
    dien_giai: str
    khoan_muc: str
    so_tien: float
    chi_tieu: str | None = None
    match_tier: str | None = None  # llm_confirmed|keyword|direct|None


def aggregate_rows(rows: list[dict[str, Any]]) -> list[AggregatedRow]:
    """Group by (thang, dien_giai, khoan_muc), sum so_tien."""
    totals: dict[tuple, float] = {}
    for r in rows:
        key = (int(r["thang"]), str(r["dien_giai"]).strip(), str(r["khoan_muc"]).strip().lower())
        totals[key] = totals.get(key, 0.0) + float(r["so_tien"])
    return [
        AggregatedRow(thang=k[0], dien_giai=k[1], khoan_muc=k[2], so_tien=v)
        for k, v in totals.items()
    ]


def match_rules(
    rows: list[AggregatedRow], rules: dict[str, Any]
) -> tuple[list[AggregatedRow], list[AggregatedRow]]:
    """Apply 3-tier rule matching. Returns (matched, unmatched)."""
    confirmed_map = {r["dien_giai"].lower(): r["chi_tieu"] for r in rules.get("llm_confirmed", [])}
    keyword_rules = rules.get("keyword", [])
    direct_map = {r["khoan_muc"].lower(): r["chi_tieu"] for r in rules.get("direct", [])}

    matched, unmatched = [], []
    for row in rows:
        dien_giai_lower = row.dien_giai.lower()

        # Tier 1: exact dien_giai match
        if dien_giai_lower in confirmed_map:
            row.chi_tieu = confirmed_map[dien_giai_lower]
            row.match_tier = "llm_confirmed"
            matched.append(row)
            continue

        # Tier 2: khoan_muc + keyword
        kw_match = None
        for rule in keyword_rules:
            if rule["khoan_muc"].lower() == row.khoan_muc:
                if any(kw.lower() in dien_giai_lower for kw in rule.get("keywords", [])):
                    kw_match = rule["chi_tieu"]
                    break
        if kw_match:
            row.chi_tieu = kw_match
            row.match_tier = "keyword"
            matched.append(row)
            continue

        # Tier 3: direct khoan_muc match
        if row.khoan_muc in direct_map:
            row.chi_tieu = direct_map[row.khoan_muc]
            row.match_tier = "direct"
            matched.append(row)
            continue

        unmatched.append(row)

    return matched, unmatched
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_excel_cr_aggregate.py -v
```

Expected: All 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/application/use_cases/excel_cr/ tests/test_excel_cr_aggregate.py
git commit -m "feat: add Excel-CR aggregate_rows and match_rules"
```

---

## Task 8: LLM classifier

**Files:**
- Create: `app/infrastructure/llm/excel_cr_classifier.py`
- Test: `tests/test_excel_cr_classifier.py`

The classifier wraps `GeminiLLMClient` (or Ollama fallback). It sends `khoan_muc` + `dien_giai` patterns (no `so_tien`) and receives `{suggested, confidence, reason, alternates}`. Threshold ≥ 0.85 → auto-apply.

- [ ] **Step 1: Write failing tests**

Create `tests/test_excel_cr_classifier.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.infrastructure.llm.excel_cr_classifier import ExcelCrClassifier, ClassificationResult

@pytest.mark.asyncio
async def test_classify_returns_result_above_threshold():
    classifier = ExcelCrClassifier.__new__(ExcelCrClassifier)

    mock_response = {
        "suggestions": [
            {
                "dien_giai": "Thù lao HĐTV quý I",
                "suggested": "Chi khác",
                "confidence": 0.92,
                "reason": "Thù lao HĐTV là chi phí quản lý",
                "alternates": ["Chi phí QL"],
            }
        ]
    }

    with patch.object(classifier, "_call_llm", new=AsyncMock(return_value=mock_response)):
        results = await classifier.classify(
            khoan_muc="cpk",
            dien_giai_list=["Thù lao HĐTV quý I"],
            chi_tieu_list=["Chi khác", "Chi phí QL"],
        )

    assert len(results) == 1
    assert results[0].suggested == "Chi khác"
    assert results[0].confidence == pytest.approx(0.92)
    assert results[0].auto_apply is True

@pytest.mark.asyncio
async def test_classify_below_threshold_not_auto_applied():
    classifier = ExcelCrClassifier.__new__(ExcelCrClassifier)

    mock_response = {
        "suggestions": [
            {
                "dien_giai": "Phí thuê xe",
                "suggested": "Chi phí SXKD",
                "confidence": 0.70,
                "reason": "Không chắc",
                "alternates": [],
            }
        ]
    }

    with patch.object(classifier, "_call_llm", new=AsyncMock(return_value=mock_response)):
        results = await classifier.classify(
            khoan_muc="cpk",
            dien_giai_list=["Phí thuê xe"],
            chi_tieu_list=["Chi phí SXKD", "Chi khác"],
        )

    assert results[0].auto_apply is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_excel_cr_classifier.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement classifier**

```python
# app/infrastructure/llm/excel_cr_classifier.py
import json
import logging
from dataclasses import dataclass
from typing import Any
import httpx

logger = logging.getLogger(__name__)

_AUTO_APPLY_THRESHOLD = 0.85

_SYSTEM_PROMPT = """Bạn là chuyên gia phân loại chi phí kế toán Việt Nam.
Phân loại các khoản chi phí vào đúng Chỉ tiêu báo cáo.
Chỉ dựa vào Khoản mục và Diễn giải — KHÔNG có thông tin về số tiền hay tên công ty.
Trả lời JSON theo schema được yêu cầu."""

_USER_TEMPLATE = """Khoản mục: {khoan_muc}

Danh sách Diễn giải cần phân loại:
{dien_giai_json}

Danh sách Chỉ tiêu hợp lệ:
{chi_tieu_json}

Trả về JSON:
{{
  "suggestions": [
    {{
      "dien_giai": "<Diễn giải gốc>",
      "suggested": "<Chỉ tiêu phù hợp nhất>",
      "confidence": <0.0-1.0>,
      "reason": "<lý do ngắn gọn>",
      "alternates": ["<Chỉ tiêu thay thế nếu có>"]
    }}
  ]
}}"""

_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass
class ClassificationResult:
    dien_giai: str
    suggested: str
    confidence: float
    reason: str
    alternates: list[str]
    auto_apply: bool


class ExcelCrClassifier:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model

    async def classify(
        self,
        khoan_muc: str,
        dien_giai_list: list[str],
        chi_tieu_list: list[str],
    ) -> list[ClassificationResult]:
        if not dien_giai_list:
            return []

        prompt = _USER_TEMPLATE.format(
            khoan_muc=khoan_muc,
            dien_giai_json=json.dumps(dien_giai_list, ensure_ascii=False),
            chi_tieu_json=json.dumps(chi_tieu_list, ensure_ascii=False),
        )

        data = await self._call_llm(prompt)
        results = []
        for s in data.get("suggestions", []):
            confidence = float(s.get("confidence", 0.0))
            results.append(ClassificationResult(
                dien_giai=s.get("dien_giai", ""),
                suggested=s.get("suggested", ""),
                confidence=confidence,
                reason=s.get("reason", ""),
                alternates=s.get("alternates", []),
                auto_apply=confidence >= _AUTO_APPLY_THRESHOLD,
            ))
        return results

    async def _call_llm(self, prompt: str) -> dict[str, Any]:
        url = _GEMINI_API_URL.format(model=self._model)
        payload = {
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 4096,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url, headers={"x-goog-api-key": self._api_key}, json=payload
            )
            resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_excel_cr_classifier.py -v
```

Expected: All 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/llm/excel_cr_classifier.py tests/test_excel_cr_classifier.py
git commit -m "feat: add ExcelCrClassifier for expense row classification"
```

---

## Task 9: Excel writer

**Files:**
- Create: `app/infrastructure/excel/excel_cr_writer.py`
- Test: `tests/test_excel_cr_writer.py`

The writer fills a template Excel file. It finds cells matching `Chỉ tiêu` label, then writes `Số tiền` into the correct month column.

- [ ] **Step 1: Write failing tests**

Create `tests/test_excel_cr_writer.py`:

```python
import io
import pytest
import openpyxl
from app.infrastructure.excel.excel_cr_writer import ExcelCrWriter
from app.application.use_cases.excel_cr.aggregate_and_match import AggregatedRow

def _make_template() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Chỉ tiêu"
    ws["B1"] = "Tháng 1"
    ws["C1"] = "Tháng 2"
    ws["A2"] = "Chi khác"
    ws["A3"] = "Chi phí lao động"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def test_writer_fills_chi_tieu_cell():
    template_bytes = _make_template()
    rows = [
        AggregatedRow(thang=1, dien_giai="Thưởng sáng kiến", khoan_muc="cpk",
                      so_tien=70_900_000.0, chi_tieu="Chi khác", match_tier="llm_confirmed"),
    ]
    result = ExcelCrWriter.write(template_bytes, rows)
    wb = openpyxl.load_workbook(io.BytesIO(result))
    ws = wb.active
    assert ws["B2"].value == pytest.approx(70_900_000.0)

def test_writer_unknown_chi_tieu_is_skipped():
    template_bytes = _make_template()
    rows = [
        AggregatedRow(thang=1, dien_giai="Unknown", khoan_muc="cpk",
                      so_tien=1_000.0, chi_tieu="Không tồn tại", match_tier="direct"),
    ]
    result = ExcelCrWriter.write(template_bytes, rows)
    wb = openpyxl.load_workbook(io.BytesIO(result))
    ws = wb.active
    # B2 and B3 should be None (untouched)
    assert ws["B2"].value is None
    assert ws["B3"].value is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_excel_cr_writer.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement writer**

```python
# app/infrastructure/excel/excel_cr_writer.py
import io
import logging
import openpyxl
from app.application.use_cases.excel_cr.aggregate_and_match import AggregatedRow

logger = logging.getLogger(__name__)


class ExcelCrWriter:
    @staticmethod
    def write(template_bytes: bytes, rows: list[AggregatedRow]) -> bytes:
        """Fill template Excel with aggregated rows. Returns modified Excel bytes."""
        wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
        ws = wb.active

        # Build lookup: chi_tieu_label → row_index
        chi_tieu_col, month_row = _find_header_structure(ws)
        row_index = _build_row_index(ws, chi_tieu_col)
        col_index = _build_col_index(ws, month_row)

        for row in rows:
            if not row.chi_tieu:
                continue
            r = row_index.get(row.chi_tieu.strip())
            c = col_index.get(row.thang)
            if r is None:
                logger.warning("Chi tieu '%s' not found in template — skipping", row.chi_tieu)
                continue
            if c is None:
                logger.warning("Thang %d not found in template — skipping", row.thang)
                continue
            current = ws.cell(row=r, column=c).value or 0
            ws.cell(row=r, column=c).value = current + row.so_tien

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


def _find_header_structure(ws) -> tuple[int, int]:
    """Return (chi_tieu_column_index, month_header_row_index)."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and "chỉ tiêu" in str(cell.value).lower():
                return cell.column, cell.row
    return 1, 1


def _build_row_index(ws, chi_tieu_col: int) -> dict[str, int]:
    index = {}
    for row in ws.iter_rows():
        cell = row[chi_tieu_col - 1]
        if cell.value and isinstance(cell.value, str):
            index[cell.value.strip()] = cell.row
    return index


def _build_col_index(ws, header_row: int) -> dict[int, int]:
    """Map month number → column index by scanning header row for 'Tháng N' patterns."""
    import re
    index = {}
    for cell in ws[header_row]:
        if cell.value:
            m = re.search(r"(\d+)", str(cell.value))
            if m:
                month = int(m.group(1))
                index[month] = cell.column
    return index
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_excel_cr_writer.py -v
```

Expected: All 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/excel/excel_cr_writer.py tests/test_excel_cr_writer.py
git commit -m "feat: add ExcelCrWriter for filling Excel templates"
```

---

## Task 10: Upload + aggregate use cases

**Files:**
- Create: `app/application/use_cases/excel_cr/upload_source.py`
- Create: `app/application/use_cases/excel_cr/aggregate_and_match_uc.py`

- [ ] **Step 1: Create upload_source.py**

```python
# app/application/use_cases/excel_cr/upload_source.py
import logging
from app.domain.entities.excel_cr_session import ExcelCrSession
from app.domain.ports.storage_port import IStoragePort
from app.infrastructure.parsers.excel_cr_source_parser import parse_source_file
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository

logger = logging.getLogger(__name__)

BUCKET = "excel-cr"


class UploadSourceUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, storage: IStoragePort):
        self._repo = repo
        self._storage = storage

    async def execute(self, filename: str, file_data: bytes) -> ExcelCrSession:
        # Validate parseable before storing
        parse_source_file(file_data, filename)

        session = ExcelCrSession()
        key = f"uploads/{session.id}/source_{filename}"
        await self._storage.upload_file(BUCKET, key, file_data, "application/octet-stream")
        session.source_file_key = key
        await self._repo.save(session)
        logger.info("Excel-CR session %s created, source stored at %s", session.id, key)
        return session
```

- [ ] **Step 2: Create aggregate_and_match_uc.py (the use case orchestrator)**

```python
# app/application/use_cases/excel_cr/aggregate_and_match_uc.py
import logging
from dataclasses import asdict
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.domain.entities.excel_cr_session import ExcelCrSession
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.parsers.excel_cr_source_parser import parse_source_file
from app.application.use_cases.excel_cr.aggregate_and_match import aggregate_rows, match_rules

logger = logging.getLogger(__name__)

BUCKET = "excel-cr"


class AggregateAndMatchUseCase:
    def __init__(
        self,
        repo: SQLiteExcelCrRepository,
        storage: IStoragePort,
        rules_manager: IExcelCrRulePort,
    ):
        self._repo = repo
        self._storage = storage
        self._rules = rules_manager

    async def execute(self, session_id: str) -> dict:
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        source_bytes = await self._storage.download_file(BUCKET, session.source_file_key)
        filename = session.source_file_key.rsplit("/", 1)[-1]
        df = parse_source_file(source_bytes, filename)

        raw_rows = df.to_dict(orient="records")
        agg_rows = aggregate_rows(raw_rows)

        rules = await self._rules.load()
        matched, unmatched = match_rules(agg_rows, rules)

        session.aggregated_data = [asdict(r) for r in agg_rows]
        session.match_results = [asdict(r) for r in matched] + [asdict(r) for r in unmatched]
        session.status = "aggregated"
        await self._repo.update(session)

        return {
            "session_id": session_id,
            "total": len(agg_rows),
            "matched": len(matched),
            "unmatched": len(unmatched),
            "rows": session.match_results,
        }
```

- [ ] **Step 3: Commit**

```bash
git add app/application/use_cases/excel_cr/upload_source.py \
        app/application/use_cases/excel_cr/aggregate_and_match_uc.py
git commit -m "feat: add UploadSource and AggregateAndMatch use cases"
```

---

## Task 11: LLM classify + confirm use cases

**Files:**
- Create: `app/application/use_cases/excel_cr/llm_classify.py`
- Create: `app/application/use_cases/excel_cr/confirm_mappings.py`

- [ ] **Step 1: Create llm_classify.py**

```python
# app/application/use_cases/excel_cr/llm_classify.py
import logging
from dataclasses import asdict
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.llm.excel_cr_classifier import ExcelCrClassifier

logger = logging.getLogger(__name__)


class LlmClassifyUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, classifier: ExcelCrClassifier):
        self._repo = repo
        self._classifier = classifier

    async def execute(self, session_id: str) -> dict:
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        if not session.match_results:
            raise ValueError("Run aggregate first")

        unmatched = [r for r in session.match_results if r.get("chi_tieu") is None]
        if not unmatched:
            return {"session_id": session_id, "classified": 0}

        by_khoan_muc: dict[str, list] = {}
        for row in unmatched:
            km = row["khoan_muc"]
            by_khoan_muc.setdefault(km, []).append(row)

        # Collect all chi_tieu from session (from matched rows, as proxy for template list)
        known_chi_tieu = list({
            r["chi_tieu"] for r in session.match_results if r.get("chi_tieu")
        })

        auto_count = 0
        for khoan_muc, rows in by_khoan_muc.items():
            dien_giai_list = [r["dien_giai"] for r in rows]
            try:
                results = await self._classifier.classify(
                    khoan_muc=khoan_muc,
                    dien_giai_list=dien_giai_list,
                    chi_tieu_list=known_chi_tieu,
                )
            except Exception as e:
                logger.warning("LLM classify failed for %s: %s", khoan_muc, e)
                continue

            result_map = {r.dien_giai: r for r in results}
            for row in rows:
                res = result_map.get(row["dien_giai"])
                if res:
                    row["llm_suggested"] = res.suggested
                    row["llm_confidence"] = res.confidence
                    row["llm_reason"] = res.reason
                    row["llm_alternates"] = res.alternates
                    if res.auto_apply:
                        row["chi_tieu"] = res.suggested
                        row["match_tier"] = "llm_confirmed"
                        auto_count += 1

        session.status = "reviewed"
        await self._repo.update(session)
        return {"session_id": session_id, "classified": auto_count, "pending_review": len(unmatched) - auto_count}
```

- [ ] **Step 2: Create confirm_mappings.py**

```python
# app/application/use_cases/excel_cr/confirm_mappings.py
import logging
from typing import Any
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository

logger = logging.getLogger(__name__)


class ConfirmMappingsUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, rules_manager: IExcelCrRulePort):
        self._repo = repo
        self._rules = rules_manager

    async def execute(self, session_id: str, confirmations: list[dict[str, Any]]) -> dict:
        """confirmations: [{"dien_giai": str, "khoan_muc": str, "chi_tieu": str}]"""
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        confirm_map = {c["dien_giai"]: c for c in confirmations}

        # Apply confirmations to match_results
        for row in (session.match_results or []):
            conf = confirm_map.get(row["dien_giai"])
            if conf:
                row["chi_tieu"] = conf["chi_tieu"]
                row["match_tier"] = "llm_confirmed"

        # Persist new confirmed mappings to rules.json
        rules = await self._rules.load()
        existing_confirmed = {r["dien_giai"].lower() for r in rules["llm_confirmed"]}
        for conf in confirmations:
            if conf["dien_giai"].lower() not in existing_confirmed:
                rules["llm_confirmed"].append({
                    "dien_giai": conf["dien_giai"],
                    "chi_tieu": conf["chi_tieu"],
                })
        await self._rules.save(rules)

        session.status = "done"
        await self._repo.update(session)
        return {"session_id": session_id, "confirmed": len(confirmations)}
```

- [ ] **Step 3: Commit**

```bash
git add app/application/use_cases/excel_cr/llm_classify.py \
        app/application/use_cases/excel_cr/confirm_mappings.py
git commit -m "feat: add LlmClassify and ConfirmMappings use cases"
```

---

## Task 12: Download use case

**Files:**
- Create: `app/application/use_cases/excel_cr/download_result.py`

- [ ] **Step 1: Create download_result.py**

```python
# app/application/use_cases/excel_cr/download_result.py
import logging
from dataclasses import fields as dc_fields
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.excel_cr_rule_port import IExcelCrRulePort
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.excel.excel_cr_writer import ExcelCrWriter
from app.application.use_cases.excel_cr.aggregate_and_match import AggregatedRow

logger = logging.getLogger(__name__)

BUCKET = "excel-cr"


class DownloadResultUseCase:
    def __init__(self, repo: SQLiteExcelCrRepository, storage: IStoragePort):
        self._repo = repo
        self._storage = storage

    async def execute(self, session_id: str) -> bytes:
        session = await self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        if not session.template_key:
            raise ValueError("No template uploaded for this session")
        if not session.match_results:
            raise ValueError("No aggregated data — run aggregate first")

        template_bytes = await self._storage.download_file(BUCKET, session.template_key)

        rows = [
            AggregatedRow(
                thang=r["thang"],
                dien_giai=r["dien_giai"],
                khoan_muc=r["khoan_muc"],
                so_tien=r["so_tien"],
                chi_tieu=r.get("chi_tieu"),
                match_tier=r.get("match_tier"),
            )
            for r in session.match_results
            if r.get("chi_tieu")
        ]

        output_bytes = ExcelCrWriter.write(template_bytes, rows)

        result_key = f"results/{session_id}/output.xlsx"
        await self._storage.upload_file(BUCKET, result_key, output_bytes,
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        logger.info("Excel-CR result stored at %s", result_key)
        return output_bytes
```

- [ ] **Step 2: Commit**

```bash
git add app/application/use_cases/excel_cr/download_result.py
git commit -m "feat: add DownloadResult use case"
```

---

## Task 13: Config + dependencies wiring

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/core/dependencies.py`

- [ ] **Step 1: Add excel_cr_bucket to config**

Open `app/core/config.py`. Find the `Settings` class. Add this field alongside the other rustfs fields:

```python
excel_cr_bucket: str = Field(default="excel-cr", env="EXCEL_CR_BUCKET")
```

- [ ] **Step 2: Add Excel-CR singletons and dependency getters to dependencies.py**

At the end of `app/core/dependencies.py`, add:

```python
# ── Excel-CR ──────────────────────────────────────────────────────────────────
from app.infrastructure.rules.rustfs_rules_manager import RustfsRulesManager
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.llm.excel_cr_classifier import ExcelCrClassifier
from app.application.use_cases.excel_cr.upload_source import UploadSourceUseCase
from app.application.use_cases.excel_cr.aggregate_and_match_uc import AggregateAndMatchUseCase
from app.application.use_cases.excel_cr.llm_classify import LlmClassifyUseCase
from app.application.use_cases.excel_cr.confirm_mappings import ConfirmMappingsUseCase
from app.application.use_cases.excel_cr.download_result import DownloadResultUseCase

_rules_manager_singleton: RustfsRulesManager | None = None
_excel_cr_classifier_singleton: ExcelCrClassifier | None = None


def get_excel_cr_rules_manager() -> RustfsRulesManager:
    global _rules_manager_singleton
    if _rules_manager_singleton is None:
        s = get_settings()
        _rules_manager_singleton = RustfsRulesManager(get_storage_singleton(), s.excel_cr_bucket)
    return _rules_manager_singleton


def get_excel_cr_classifier() -> ExcelCrClassifier:
    global _excel_cr_classifier_singleton
    if _excel_cr_classifier_singleton is None:
        s = get_settings()
        _excel_cr_classifier_singleton = ExcelCrClassifier(
            api_key=s.gemini_api_key, model=s.gemini_model
        )
    return _excel_cr_classifier_singleton


def get_excel_cr_repo(db: aiosqlite.Connection = Depends(get_db_conn)) -> SQLiteExcelCrRepository:
    return SQLiteExcelCrRepository(db)


def get_excel_cr_upload_uc(
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
) -> UploadSourceUseCase:
    return UploadSourceUseCase(repo=repo, storage=storage)


def get_excel_cr_aggregate_uc(
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
) -> AggregateAndMatchUseCase:
    return AggregateAndMatchUseCase(
        repo=repo, storage=storage, rules_manager=get_excel_cr_rules_manager()
    )


def get_excel_cr_llm_classify_uc(
    repo=Depends(get_excel_cr_repo),
) -> LlmClassifyUseCase:
    return LlmClassifyUseCase(repo=repo, classifier=get_excel_cr_classifier())


def get_excel_cr_confirm_uc(
    repo=Depends(get_excel_cr_repo),
) -> ConfirmMappingsUseCase:
    return ConfirmMappingsUseCase(repo=repo, rules_manager=get_excel_cr_rules_manager())


def get_excel_cr_download_uc(
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
) -> DownloadResultUseCase:
    return DownloadResultUseCase(repo=repo, storage=storage)
```

- [ ] **Step 3: Commit**

```bash
git add app/core/config.py app/core/dependencies.py
git commit -m "feat: wire Excel-CR dependencies and config"
```

---

## Task 14: API router

**Files:**
- Create: `app/presentation/api/excel_cr_router.py`

- [ ] **Step 1: Create router**

```python
# app/presentation/api/excel_cr_router.py
import logging
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
import io
from app.core.dependencies import (
    get_excel_cr_upload_uc,
    get_excel_cr_aggregate_uc,
    get_excel_cr_llm_classify_uc,
    get_excel_cr_confirm_uc,
    get_excel_cr_download_uc,
    get_excel_cr_repo,
    get_storage,
    get_settings,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/excel-cr", tags=["excel-cr"])

BUCKET = "excel-cr"


@router.post("/upload-source")
async def upload_source(
    file: UploadFile = File(...),
    uc=Depends(get_excel_cr_upload_uc),
):
    try:
        data = await file.read()
        session = await uc.execute(filename=file.filename, file_data=data)
        return {"session_id": session.id, "status": session.status}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/upload-template/{session_id}")
async def upload_template(
    session_id: str,
    file: UploadFile = File(...),
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
    settings=Depends(get_settings),
):
    session = await repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    data = await file.read()
    key = f"uploads/{session_id}/template_{file.filename}"
    await storage.upload_file(settings.excel_cr_bucket, key, data,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    session.template_key = key
    await repo.update(session)
    return {"session_id": session_id, "template_key": key}


@router.get("/aggregate/{session_id}")
async def aggregate(session_id: str, uc=Depends(get_excel_cr_aggregate_uc)):
    try:
        return await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/llm-review/{session_id}")
async def llm_review(session_id: str, uc=Depends(get_excel_cr_llm_classify_uc)):
    try:
        return await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/confirm/{session_id}")
async def confirm(
    session_id: str,
    body: list[dict],
    uc=Depends(get_excel_cr_confirm_uc),
):
    try:
        return await uc.execute(session_id, body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/download/{session_id}")
async def download(session_id: str, uc=Depends(get_excel_cr_download_uc)):
    try:
        output_bytes = await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="excel_cr_output.xlsx"'},
    )


@router.get("/rules")
async def get_rules(rules_mgr=Depends(lambda: __import__(
    "app.core.dependencies", fromlist=["get_excel_cr_rules_manager"]
).get_excel_cr_rules_manager())):
    return await rules_mgr.load()


@router.post("/rules")
async def update_rules(body: dict, rules_mgr=Depends(lambda: __import__(
    "app.core.dependencies", fromlist=["get_excel_cr_rules_manager"]
).get_excel_cr_rules_manager())):
    await rules_mgr.save(body)
    return {"status": "saved"}
```

- [ ] **Step 2: Commit**

```bash
git add app/presentation/api/excel_cr_router.py
git commit -m "feat: add Excel-CR API router"
```

---

## Task 15: Web router + frontend HTML

**Files:**
- Create: `app/presentation/web/excel_cr_web.py`
- Create: `app/static/excel_cr/index.html`

- [ ] **Step 1: Create web router**

```python
# app/presentation/web/excel_cr_web.py
from fastapi import APIRouter
from fastapi.responses import FileResponse
import os

router = APIRouter()

@router.get("/excel-cr/", include_in_schema=False)
async def excel_cr_index():
    path = os.path.join(os.path.dirname(__file__), "../../static/excel_cr/index.html")
    return FileResponse(os.path.abspath(path))
```

- [ ] **Step 2: Create `app/static/excel_cr/` directory**

```bash
mkdir -p app/static/excel_cr
```

- [ ] **Step 3: Create index.html**

```html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Excel-CR — Tổng hợp chi phí</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }
    h1 { color: #1a237e; }
    .state { display: none; }
    .state.active { display: block; }
    .drop-zone { border: 2px dashed #ccc; padding: 40px; text-align: center; cursor: pointer; border-radius: 8px; margin: 16px 0; }
    .drop-zone:hover { border-color: #1a237e; background: #f5f5ff; }
    button { background: #1a237e; color: white; border: none; padding: 10px 24px; border-radius: 4px; cursor: pointer; font-size: 14px; }
    button:hover { background: #283593; }
    button.secondary { background: #757575; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }
    th { background: #1a237e; color: white; padding: 8px; text-align: left; }
    td { border-bottom: 1px solid #eee; padding: 8px; }
    tr:hover td { background: #f5f5ff; }
    .confidence-high { color: green; font-weight: bold; }
    .confidence-low { color: orange; }
    .stats { background: #e8f5e9; padding: 12px; border-radius: 4px; margin: 16px 0; }
    select { padding: 6px; border-radius: 4px; border: 1px solid #ccc; }
    .loading { color: #666; font-style: italic; }
    .error { color: #c62828; background: #ffebee; padding: 10px; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>Excel-CR — Tổng hợp chi phí</h1>

  <!-- STATE 1: Upload -->
  <div id="state-upload" class="state active">
    <h2>Bước 1: Upload file</h2>
    <div class="drop-zone" id="drop-source" onclick="document.getElementById('file-source').click()">
      <p>Kéo thả hoặc click để chọn file chi phí (CSV, XLS, XLSX, PDF)</p>
      <input type="file" id="file-source" accept=".csv,.xls,.xlsx,.pdf" style="display:none">
      <p id="source-name" style="color:#1a237e;font-weight:bold"></p>
    </div>
    <div class="drop-zone" id="drop-template" onclick="document.getElementById('file-template').click()">
      <p>Kéo thả hoặc click để chọn file template Excel đích</p>
      <input type="file" id="file-template" accept=".xlsx" style="display:none">
      <p id="template-name" style="color:#1a237e;font-weight:bold"></p>
    </div>
    <div id="upload-error" class="error" style="display:none"></div>
    <button onclick="startProcessing()" id="btn-start">Bắt đầu xử lý</button>
  </div>

  <!-- STATE 2: Review -->
  <div id="state-review" class="state">
    <h2>Bước 2: Xem xét kết quả</h2>
    <div id="review-stats" class="stats"></div>
    <p>Các dòng cần xác nhận thủ công (LLM không chắc hoặc chưa phân loại):</p>
    <table id="review-table">
      <thead>
        <tr><th>Tháng</th><th>Khoản mục</th><th>Diễn giải</th><th>Số tiền</th><th>Gợi ý LLM</th><th>Confidence</th><th>Chỉ tiêu</th></tr>
      </thead>
      <tbody id="review-body"></tbody>
    </table>
    <button onclick="confirmAndDownload()">Xác nhận & Tải về</button>
    <button class="secondary" onclick="location.reload()">Bắt đầu lại</button>
  </div>

  <!-- STATE 3: Done -->
  <div id="state-done" class="state">
    <h2>Hoàn thành!</h2>
    <div id="done-stats" class="stats"></div>
    <button onclick="downloadFile()">Tải file Excel</button>
    <button class="secondary" onclick="location.reload()">Xử lý file mới</button>
  </div>

  <script>
    let sessionId = null;
    let allChiTieu = [];

    function showState(name) {
      document.querySelectorAll('.state').forEach(s => s.classList.remove('active'));
      document.getElementById('state-' + name).classList.add('active');
    }

    document.getElementById('file-source').onchange = e => {
      document.getElementById('source-name').textContent = e.target.files[0]?.name || '';
    };
    document.getElementById('file-template').onchange = e => {
      document.getElementById('template-name').textContent = e.target.files[0]?.name || '';
    };

    async function startProcessing() {
      const src = document.getElementById('file-source').files[0];
      const tmpl = document.getElementById('file-template').files[0];
      const errEl = document.getElementById('upload-error');
      errEl.style.display = 'none';

      if (!src || !tmpl) { errEl.textContent = 'Vui lòng chọn cả 2 file.'; errEl.style.display = 'block'; return; }

      document.getElementById('btn-start').textContent = 'Đang xử lý...';
      document.getElementById('btn-start').disabled = true;

      try {
        // Upload source
        let fd = new FormData(); fd.append('file', src);
        let r = await fetch('/excel-cr/upload-source', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        const { session_id } = await r.json();
        sessionId = session_id;

        // Upload template
        fd = new FormData(); fd.append('file', tmpl);
        r = await fetch(`/excel-cr/upload-template/${sessionId}`, { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);

        // Aggregate
        r = await fetch(`/excel-cr/aggregate/${sessionId}`);
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        const aggData = await r.json();

        // Extract all chi_tieu from matched rows for dropdown
        allChiTieu = [...new Set(aggData.rows.filter(row => row.chi_tieu).map(row => row.chi_tieu))];

        // LLM review
        r = await fetch(`/excel-cr/llm-review/${sessionId}`, { method: 'POST' });
        // ignore LLM errors — show review UI anyway

        // Re-fetch updated aggregate data
        r = await fetch(`/excel-cr/aggregate/${sessionId}`);
        const updatedData = await r.json();

        showReview(updatedData);
      } catch (e) {
        errEl.textContent = 'Lỗi: ' + e.message;
        errEl.style.display = 'block';
        document.getElementById('btn-start').textContent = 'Bắt đầu xử lý';
        document.getElementById('btn-start').disabled = false;
      }
    }

    function showReview(data) {
      showState('review');
      document.getElementById('review-stats').innerHTML =
        `Tổng: <b>${data.total}</b> dòng &nbsp;|&nbsp; Đã khớp: <b>${data.matched}</b> &nbsp;|&nbsp; Cần xem xét: <b>${data.unmatched}</b>`;

      const tbody = document.getElementById('review-body');
      tbody.innerHTML = '';
      const needReview = data.rows.filter(r => !r.chi_tieu || r.llm_confidence < 0.85);

      if (needReview.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:green">Tất cả đã được phân loại tự động!</td></tr>';
        return;
      }

      needReview.forEach((row, i) => {
        const confidenceClass = (row.llm_confidence || 0) >= 0.85 ? 'confidence-high' : 'confidence-low';
        const options = allChiTieu.map(ct =>
          `<option value="${ct}" ${ct === (row.llm_suggested || row.chi_tieu) ? 'selected' : ''}>${ct}</option>`
        ).join('');

        tbody.innerHTML += `<tr data-dien-giai="${row.dien_giai}" data-khoan-muc="${row.khoan_muc}">
          <td>${row.thang}</td>
          <td>${row.khoan_muc}</td>
          <td title="${row.llm_reason || ''}">${row.dien_giai}</td>
          <td>${row.so_tien?.toLocaleString('vi-VN')}</td>
          <td>${row.llm_suggested || '—'}</td>
          <td class="${confidenceClass}">${row.llm_confidence ? (row.llm_confidence * 100).toFixed(0) + '%' : '—'}</td>
          <td><select class="chi-tieu-select" data-idx="${i}"><option value="">-- Bỏ qua --</option>${options}</select></td>
        </tr>`;
      });
    }

    async function confirmAndDownload() {
      const rows = document.querySelectorAll('#review-body tr[data-dien-giai]');
      const confirmations = [];
      rows.forEach(row => {
        const sel = row.querySelector('.chi-tieu-select');
        if (sel && sel.value) {
          confirmations.push({
            dien_giai: row.dataset.dienGiai,
            khoan_muc: row.dataset.khoanMuc,
            chi_tieu: sel.value,
          });
        }
      });

      if (confirmations.length > 0) {
        await fetch(`/excel-cr/confirm/${sessionId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(confirmations),
        });
      } else {
        // Nothing to confirm — just mark done
        await fetch(`/excel-cr/confirm/${sessionId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify([]),
        });
      }

      showState('done');
      document.getElementById('done-stats').textContent = `Session: ${sessionId} — Sẵn sàng tải xuống.`;
    }

    async function downloadFile() {
      const r = await fetch(`/excel-cr/download/${sessionId}`);
      if (!r.ok) { alert('Lỗi tải file: ' + r.statusText); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'excel_cr_output.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    }
  </script>
</body>
</html>
```

- [ ] **Step 4: Commit**

```bash
git add app/presentation/web/excel_cr_web.py app/static/excel_cr/index.html
git commit -m "feat: add Excel-CR web router and frontend HTML"
```

---

## Task 16: Mount in main.py + create RustFS bucket on startup

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add Excel-CR router imports and bucket init in main.py**

In `app/main.py`, after the existing import lines at the top add:

```python
from app.presentation.api.excel_cr_router import router as excel_cr_api_router
from app.presentation.web.excel_cr_web import router as excel_cr_web_router
```

In the `lifespan` function, after the existing `storage.ensure_buckets(...)` call, add:

```python
        await storage.ensure_buckets(
            settings.rustfs_bucket_invoices,
            settings.rustfs_bucket_exports,
            settings.excel_cr_bucket,
        )
```

At the bottom of `main.py`, after `app.include_router(web_router)`, add:

```python
app.include_router(excel_cr_api_router)
app.include_router(excel_cr_web_router)
```

- [ ] **Step 2: Verify app starts without errors**

```bash
poetry run python -c "from app.main import app; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: mount Excel-CR routers and init excel-cr RustFS bucket on startup"
```

---

## Task 17: E2E smoke test

- [ ] **Step 1: Start the app (dev mode)**

```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 2: Open browser at http://localhost:8000/excel-cr/**

Verify the 3-state upload UI loads without JS errors.

- [ ] **Step 3: Upload test files**

- Source: `Chi phi khac 2025 sau kt 22.1.xls - CP đúng.csv`
- Template: `Bao cao tinh hinh thuc hien 2025 sau KT 2.2.xlsx`

Verify:
- `session_id` returned
- `/aggregate/{id}` returns rows with `thang`, `dien_giai`, `so_tien`, `khoan_muc`
- Total `so_tien` in response ≈ sum of all rows in source CSV
- LLM review runs without 500 errors
- Download returns a valid `.xlsx` file
- Open downloaded file in Excel — confirm Chỉ tiêu cells filled, no `#REF!` errors

- [ ] **Step 4: Run full test suite**

```bash
poetry run pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat: Excel-CR integration complete — E2E verified"
```

---

## Summary of all new files

```
app/domain/entities/excel_cr_session.py
app/domain/ports/excel_cr_rule_port.py
app/application/use_cases/excel_cr/__init__.py
app/application/use_cases/excel_cr/upload_source.py
app/application/use_cases/excel_cr/aggregate_and_match.py
app/application/use_cases/excel_cr/aggregate_and_match_uc.py
app/application/use_cases/excel_cr/llm_classify.py
app/application/use_cases/excel_cr/confirm_mappings.py
app/application/use_cases/excel_cr/download_result.py
app/infrastructure/parsers/excel_cr_source_parser.py
app/infrastructure/excel/excel_cr_writer.py
app/infrastructure/rules/__init__.py
app/infrastructure/rules/rustfs_rules_manager.py
app/infrastructure/llm/excel_cr_classifier.py
app/infrastructure/repositories/sqlite_excel_cr_repo.py
app/presentation/api/excel_cr_router.py
app/presentation/web/excel_cr_web.py
app/static/excel_cr/index.html
tests/test_excel_cr_db.py
tests/test_excel_cr_parser.py
tests/test_excel_cr_rules.py
tests/test_excel_cr_aggregate.py
tests/test_excel_cr_classifier.py
tests/test_excel_cr_writer.py
```
