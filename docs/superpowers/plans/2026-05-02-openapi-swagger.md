# OpenAPI / Swagger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full OpenAPI/Swagger support to all endpoints — typed Pydantic response models for Excel-CR, `summary`/`tags` on every route, standardize Excel-CR prefix to `/api/v1/excel-cr/`, and extract API docs into `docs/api-endpoints.md`.

**Architecture:** Presentation-layer only changes. New `excel_cr_schemas.py` defines Pydantic models for Excel-CR I/O. Both routers get annotated decorators. FastAPI auto-generates `/docs` and `/openapi.json` from these annotations.

**Tech Stack:** FastAPI, Pydantic v2, pytest + httpx (TestClient)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/presentation/api/excel_cr_schemas.py` | **Create** | Pydantic models for all Excel-CR request/response types |
| `app/presentation/api/excel_cr_router.py` | **Modify** | Fix prefix → `/api/v1/excel-cr`, add `response_model` + `summary` + `tags` |
| `app/presentation/api/router.py` | **Modify** | Add `summary` + `tags=["invoices"]` to all invoice endpoints |
| `app/main.py` | **Modify** | Update `FastAPI(title, version, description, openapi_tags)` |
| `tests/presentation/test_excel_cr_router.py` | **Create** | Prefix change + response shape tests |
| `docs/api-endpoints.md` | **Create** | Full API reference (all endpoints, both routers) |
| `docs/huong-dan-excel-cr.md` | **Modify** | Remove Section 4 (API Reference), add link to `api-endpoints.md` |

---

## Task 1: Pydantic schemas for Excel-CR

**Files:**
- Create: `app/presentation/api/excel_cr_schemas.py`
- Test: `tests/presentation/test_excel_cr_router.py` (partial — schema tests)

- [ ] **Step 1: Create `excel_cr_schemas.py`**

```python
# app/presentation/api/excel_cr_schemas.py
from pydantic import BaseModel


class UploadSourceResponse(BaseModel):
    session_id: str
    status: str


class UploadTemplateResponse(BaseModel):
    session_id: str
    template_key: str


class AggregateResponse(BaseModel):
    session_id: str
    matched: int
    unmatched: int
    status: str


class LlmReviewResponse(BaseModel):
    session_id: str
    classified: int


class ConfirmItem(BaseModel):
    dien_giai: str
    khoan_muc: str
    chi_tieu: str


class ConfirmResponse(BaseModel):
    session_id: str
    confirmed: int


class LlmConfirmedRule(BaseModel):
    dien_giai: str
    chi_tieu: str


class KeywordRule(BaseModel):
    khoan_muc: str
    keywords: list[str]
    chi_tieu: str


class RulesResponse(BaseModel):
    llm_confirmed: list[LlmConfirmedRule]
    keyword: list[KeywordRule]
    direct: dict[str, str]
```

- [ ] **Step 2: Write schema validation tests**

Create `tests/presentation/test_excel_cr_router.py`:

```python
import pytest
from app.presentation.api.excel_cr_schemas import (
    UploadSourceResponse, AggregateResponse, ConfirmItem,
    RulesResponse, LlmConfirmedRule, KeywordRule,
)


def test_upload_source_response():
    r = UploadSourceResponse(session_id="abc", status="pending")
    assert r.session_id == "abc"
    assert r.status == "pending"


def test_aggregate_response():
    r = AggregateResponse(session_id="abc", matched=10, unmatched=2, status="aggregated")
    assert r.matched == 10
    assert r.unmatched == 2


def test_confirm_item_required_fields():
    with pytest.raises(Exception):
        ConfirmItem(dien_giai="foo")  # missing khoan_muc, chi_tieu


def test_rules_response_structure():
    r = RulesResponse(
        llm_confirmed=[LlmConfirmedRule(dien_giai="foo", chi_tieu="642")],
        keyword=[KeywordRule(khoan_muc="CP VP", keywords=["in ấn"], chi_tieu="642")],
        direct={"CP điện thoại": "641"},
    )
    assert r.llm_confirmed[0].chi_tieu == "642"
    assert r.direct["CP điện thoại"] == "641"
```

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/presentation/test_excel_cr_router.py::test_upload_source_response \
  tests/presentation/test_excel_cr_router.py::test_aggregate_response \
  tests/presentation/test_excel_cr_router.py::test_confirm_item_required_fields \
  tests/presentation/test_excel_cr_router.py::test_rules_response_structure -v
```

Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add app/presentation/api/excel_cr_schemas.py tests/presentation/test_excel_cr_router.py
git commit -m "feat: add Pydantic schemas for Excel-CR API responses"
```

---

## Task 2: Update Excel-CR router — prefix + response_model + summary

**Files:**
- Modify: `app/presentation/api/excel_cr_router.py`
- Test: `tests/presentation/test_excel_cr_router.py` (add prefix tests)

- [ ] **Step 1: Write failing prefix test**

Add to `tests/presentation/test_excel_cr_router.py`:

```python
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from app.main import app

client = TestClient(app)


def test_old_prefix_returns_404():
    """Old /excel-cr/ prefix must no longer exist."""
    response = client.get("/excel-cr/rules")
    assert response.status_code == 404


def test_new_prefix_rules_endpoint_exists():
    """New /api/v1/excel-cr/rules must exist (even if it returns error without DB)."""
    response = client.get("/api/v1/excel-cr/rules")
    # 200 or 500 (no DB in test) — but NOT 404
    assert response.status_code != 404
```

- [ ] **Step 2: Run to confirm old prefix test PASSES (it passes now — old prefix exists)**

```bash
poetry run pytest tests/presentation/test_excel_cr_router.py::test_old_prefix_returns_404 -v
```

Expected: FAIL (currently `/excel-cr/rules` returns 200, not 404) — confirms we need the change.

- [ ] **Step 3: Rewrite `excel_cr_router.py`**

```python
# app/presentation/api/excel_cr_router.py
import logging
import io
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
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
from app.presentation.api.excel_cr_schemas import (
    UploadSourceResponse,
    UploadTemplateResponse,
    AggregateResponse,
    LlmReviewResponse,
    ConfirmItem,
    ConfirmResponse,
    RulesResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/excel-cr", tags=["excel-cr"])

BUCKET = "excel-cr"


@router.post(
    "/upload-source",
    response_model=UploadSourceResponse,
    summary="Upload file nguồn chi phí",
)
async def upload_source(
    file: UploadFile = File(...),
    uc=Depends(get_excel_cr_upload_uc),
):
    try:
        data = await file.read()
        session = await uc.execute(filename=file.filename, file_data=data)
        return UploadSourceResponse(session_id=session.id, status=session.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post(
    "/upload-template/{session_id}",
    response_model=UploadTemplateResponse,
    summary="Upload file template Excel",
)
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
    await storage.upload_file(
        settings.excel_cr_bucket, key, data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    session.template_key = key
    await repo.update(session)
    return UploadTemplateResponse(session_id=session_id, template_key=key)


@router.get(
    "/aggregate/{session_id}",
    response_model=AggregateResponse,
    summary="Tổng hợp & match tự động (3 tầng rules)",
)
async def aggregate(session_id: str, uc=Depends(get_excel_cr_aggregate_uc)):
    try:
        return await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/llm-review/{session_id}",
    response_model=LlmReviewResponse,
    summary="LLM gợi ý chỉ tiêu cho dòng chưa khớp",
)
async def llm_review(session_id: str, uc=Depends(get_excel_cr_llm_classify_uc)):
    try:
        return await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post(
    "/confirm/{session_id}",
    response_model=ConfirmResponse,
    summary="Xác nhận mapping, lưu vào rules",
)
async def confirm(
    session_id: str,
    body: list[ConfirmItem],
    uc=Depends(get_excel_cr_confirm_uc),
):
    try:
        raw = [item.model_dump() for item in body]
        return await uc.execute(session_id, raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/download/{session_id}",
    summary="Tải file Excel kết quả",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "File Excel kết quả tổng hợp chi phí",
        }
    },
)
async def download(session_id: str, uc=Depends(get_excel_cr_download_uc)):
    try:
        output_bytes = await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="excel_cr_output.xlsx"'},
    )


@router.get(
    "/rules",
    response_model=RulesResponse,
    summary="Xem toàn bộ rules mapping hiện tại",
)
async def get_rules(
    rules_mgr=Depends(
        lambda: __import__(
            "app.core.dependencies", fromlist=["get_excel_cr_rules_manager"]
        ).get_excel_cr_rules_manager()
    ),
):
    return await rules_mgr.load()


@router.post(
    "/rules",
    summary="Ghi đè toàn bộ rules mapping",
)
async def update_rules(
    body: RulesResponse,
    rules_mgr=Depends(
        lambda: __import__(
            "app.core.dependencies", fromlist=["get_excel_cr_rules_manager"]
        ).get_excel_cr_rules_manager()
    ),
):
    await rules_mgr.save(body.model_dump())
    return {"status": "saved"}
```

- [ ] **Step 4: Run prefix tests**

```bash
poetry run pytest tests/presentation/test_excel_cr_router.py::test_old_prefix_returns_404 \
  tests/presentation/test_excel_cr_router.py::test_new_prefix_rules_endpoint_exists -v
```

Expected: 2 PASS

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
poetry run pytest --tb=short -q
```

Expected: all previous tests still PASS (no invoice tests broken)

- [ ] **Step 6: Commit**

```bash
git add app/presentation/api/excel_cr_router.py tests/presentation/test_excel_cr_router.py
git commit -m "feat: standardize Excel-CR prefix to /api/v1/excel-cr, add response_model and summary"
```

---

## Task 3: Annotate invoice router

**Files:**
- Modify: `app/presentation/api/router.py`

- [ ] **Step 1: Add `summary` and `tags` to every endpoint in `router.py`**

Replace the existing `router = APIRouter(prefix="/api/v1")` line and all `@router.*` decorators:

```python
router = APIRouter(prefix="/api/v1", tags=["invoices"])
```

Then add `summary=` to each decorator:

```python
@router.post("/jobs", response_model=list[JobResponse],
             summary="Upload hóa đơn PDF/XML/ZIP")

@router.get("/jobs", response_model=list[JobResponse],
            summary="Danh sách hóa đơn (filter theo status)")

@router.get("/jobs/{job_id}", response_model=JobResponse,
            summary="Chi tiết hóa đơn theo ID")

@router.patch("/jobs/{job_id}/review", response_model=JobResponse,
              summary="Cập nhật dữ liệu trích xuất trước khi xác nhận")

@router.post("/jobs/{job_id}/confirm", response_model=JobResponse,
             summary="Xác nhận hóa đơn — lưu vào Excel tổng hợp")

@router.post("/jobs/{job_id}/retry", response_model=JobResponse,
             summary="Retry hóa đơn bị lỗi")

@router.post("/jobs/{job_id}/reject", response_model=JobResponse,
             summary="Từ chối hóa đơn")

@router.get("/exports/{year}/{month}",
            summary="Tải file Excel tổng hợp theo tháng",
            responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
```

- [ ] **Step 2: Run tests**

```bash
poetry run pytest tests/ --tb=short -q
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add app/presentation/api/router.py
git commit -m "feat: add summary and tags to invoice API endpoints"
```

---

## Task 4: Update FastAPI app metadata

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Update `FastAPI(...)` call in `main.py`**

Find the line:
```python
app = FastAPI(title="Thu Hóa Đơn", lifespan=lifespan)
```

Replace with:
```python
app = FastAPI(
    title="Thu Hóa Đơn API",
    version="1.0.0",
    description=(
        "API thu thập và xử lý hóa đơn điện tử từ email.\n\n"
        "- **Swagger UI:** `/docs`\n"
        "- **OpenAPI JSON:** `/openapi.json`"
    ),
    openapi_tags=[
        {"name": "invoices", "description": "Xử lý hóa đơn PDF/XML từ email"},
        {"name": "excel-cr", "description": "Tổng hợp chi phí vào template Excel (Excel-CR)"},
    ],
    lifespan=lifespan,
)
```

- [ ] **Step 2: Verify Swagger UI**

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` — verify:
- Title shows "Thu Hóa Đơn API"
- Two tag groups: "invoices" and "excel-cr"
- All endpoints have summary text
- Excel-CR endpoints show typed request/response schemas (not `{}`)

- [ ] **Step 3: Verify OpenAPI JSON has no empty schemas**

```bash
curl http://localhost:8000/openapi.json | python3 -c "
import json, sys
spec = json.load(sys.stdin)
empty = [(p, m) for p, methods in spec['paths'].items()
         for m, op in methods.items()
         if isinstance(op, dict) and op.get('responses', {}).get('200', {}).get('content', {}) == {}]
print('Empty 200 responses:', empty if empty else 'None — all good')
"
```

Expected: `Empty 200 responses: None — all good`

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: configure FastAPI OpenAPI metadata with title, version, tags"
```

---

## Task 5: Create `docs/api-endpoints.md`

**Files:**
- Create: `docs/api-endpoints.md`
- Modify: `docs/huong-dan-excel-cr.md`

- [ ] **Step 1: Create `docs/api-endpoints.md`**

```markdown
# API Reference — Thu Hóa Đơn

**Base URL:** `http://localhost:8000` (dev) | configured via env in prod  
**Swagger UI:** `GET /docs`  
**OpenAPI JSON:** `GET /openapi.json`

---

## Invoice API — `/api/v1/`

| Method | Endpoint | Summary |
|--------|----------|---------|
| `POST` | `/api/v1/jobs` | Upload hóa đơn PDF/XML/ZIP |
| `GET` | `/api/v1/jobs` | Danh sách hóa đơn (filter: `?status=pending`) |
| `GET` | `/api/v1/jobs/{id}` | Chi tiết hóa đơn theo ID |
| `PATCH` | `/api/v1/jobs/{id}/review` | Cập nhật dữ liệu trích xuất |
| `POST` | `/api/v1/jobs/{id}/confirm` | Xác nhận hóa đơn |
| `POST` | `/api/v1/jobs/{id}/retry` | Retry hóa đơn lỗi |
| `POST` | `/api/v1/jobs/{id}/reject` | Từ chối hóa đơn |
| `GET` | `/api/v1/exports/{year}/{month}` | Tải Excel tổng hợp tháng |

### Response: `JobResponse`

```json
{
  "id": "uuid",
  "filename": "invoice.xml",
  "file_type": "xml",
  "status": "pending | processing | confirmed | rejected | failed",
  "created_at": "2026-05-01T10:00:00Z",
  "extracted_items": [...],
  "extracted_line_items": [...],
  "source_paths": ["rustfs://invoices/..."],
  "error": null
}
```

---

## Excel-CR API — `/api/v1/excel-cr/`

| Method | Endpoint | Summary |
|--------|----------|---------|
| `POST` | `/api/v1/excel-cr/upload-source` | Upload file nguồn chi phí |
| `POST` | `/api/v1/excel-cr/upload-template/{session_id}` | Upload file template Excel |
| `GET` | `/api/v1/excel-cr/aggregate/{session_id}` | Tổng hợp & match tự động |
| `POST` | `/api/v1/excel-cr/llm-review/{session_id}` | LLM gợi ý cho dòng chưa khớp |
| `POST` | `/api/v1/excel-cr/confirm/{session_id}` | Xác nhận mapping |
| `GET` | `/api/v1/excel-cr/download/{session_id}` | Tải file Excel kết quả |
| `GET` | `/api/v1/excel-cr/rules` | Xem rules mapping |
| `POST` | `/api/v1/excel-cr/rules` | Ghi đè rules mapping |

### Session states: `pending → aggregated → reviewed → done`

### `POST /api/v1/excel-cr/confirm/{session_id}` — request body

```json
[
  {
    "dien_giai": "Mua văn phòng phẩm",
    "khoan_muc": "Chi phí văn phòng",
    "chi_tieu": "642"
  }
]
```

### `GET /api/v1/excel-cr/rules` — response

```json
{
  "llm_confirmed": [{"dien_giai": "...", "chi_tieu": "642"}],
  "keyword": [{"khoan_muc": "...", "keywords": ["..."], "chi_tieu": "642"}],
  "direct": {"Chi phí điện thoại": "641"}
}
```

---

## Error Responses

| Status | Meaning |
|--------|---------|
| `404` | Resource not found (session_id, job_id) |
| `422` | Validation error (wrong file format, wrong state) |
| `500` | Server error (check logs) |
```

- [ ] **Step 2: Update `docs/huong-dan-excel-cr.md` — remove Section 4, add link**

In `docs/huong-dan-excel-cr.md`, replace Section 4 entirely:

Old text (lines starting with `## 4. API Reference` through the end of the rules `POST` endpoint block):

```markdown
## 4. API Reference
...
> **Cảnh báo:** Ghi đè toàn bộ — lấy `GET /rules` trước, sửa, rồi `POST` lại để không mất dữ liệu cũ.
```

Replace with:

```markdown
## 4. API Reference

Xem tài liệu API đầy đủ tại: [`docs/api-endpoints.md`](../api-endpoints.md)

Hoặc dùng Swagger UI khi server đang chạy: `http://localhost:8000/docs`
```

- [ ] **Step 3: Commit**

```bash
git add docs/api-endpoints.md docs/huong-dan-excel-cr.md
git commit -m "docs: add api-endpoints.md, trim API section from huong-dan-excel-cr.md"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Pydantic schemas for Excel-CR → Task 1
- ✅ Prefix `/excel-cr` → `/api/v1/excel-cr` → Task 2
- ✅ `response_model` + `summary` on Excel-CR → Task 2
- ✅ `summary` + `tags` on invoice endpoints → Task 3
- ✅ FastAPI app metadata → Task 4
- ✅ `docs/api-endpoints.md` created → Task 5
- ✅ `huong-dan-excel-cr.md` trimmed → Task 5
- ✅ Breaking change (prefix) documented in spec migration note → Task 2 test confirms

**Placeholder scan:** None found.

**Type consistency:**
- `ConfirmItem.model_dump()` called in Task 2 router — matches Pydantic v2 API ✅
- `RulesResponse.model_dump()` called in `update_rules` — consistent ✅
- `AggregateResponse` fields (`matched`, `unmatched`, `status`) — must match what `uc.execute()` returns. Check: `aggregate_and_match_uc.py` returns a dict with these keys (confirmed from earlier read).
