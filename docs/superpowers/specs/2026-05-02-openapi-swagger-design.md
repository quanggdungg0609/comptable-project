# OpenAPI / Swagger — Design Spec

**Date:** 2026-05-02  
**Status:** Approved

## Problem

- Excel-CR endpoints return raw `dict` — no `response_model`, invisible to TypeScript codegen
- Invoice endpoints missing `summary` / `description` — Swagger UI unhelpful
- Prefix inconsistency: invoices use `/api/v1/...`, Excel-CR uses `/excel-cr/...`
- No structured API docs file separate from usage guide

## Goal

1. Full Swagger UI (`/docs`) — clean, typed, human-readable for FE dev
2. `/openapi.json` usable by TypeScript generators (`openapi-typescript`, `orval`)
3. Prefix standardized: all JSON APIs under `/api/v1/`
4. Separate `docs/api-endpoints.md` as canonical API reference

## Scope

- Add Pydantic response schemas for all Excel-CR endpoints
- Annotate all endpoints with `response_model`, `summary`, `tags`
- Rename Excel-CR router prefix `/excel-cr` → `/api/v1/excel-cr`
- Configure FastAPI app-level OpenAPI metadata
- Extract API section from `huong-dan-excel-cr.md` into `docs/api-endpoints.md`

## Out of Scope

- Auth / security schemes (no auth currently)
- Request body schemas for invoice endpoints (already working)
- Frontend code generation tooling setup

## Architecture

No new layers. Changes are purely in the presentation layer.

```
app/presentation/api/
  schemas.py                  ← existing (invoice schemas, unchanged)
  excel_cr_schemas.py         ← NEW: Pydantic models for Excel-CR I/O
  router.py                   ← add summary/description to invoice endpoints
  excel_cr_router.py          ← fix prefix, add response_model + summary
app/main.py                   ← update FastAPI metadata + openapi_tags
docs/
  api-endpoints.md            ← NEW: full API reference (extracted + expanded)
  huong-dan-excel-cr.md       ← remove section 4, add link to api-endpoints.md
```

## New File: `excel_cr_schemas.py`

```python
from pydantic import BaseModel

# --- Responses ---

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

class ConfirmResponse(BaseModel):
    session_id: str
    confirmed: int

# --- Request bodies ---

class ConfirmItem(BaseModel):
    dien_giai: str
    khoan_muc: str
    chi_tieu: str

# --- Rules ---

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

## Modified: `excel_cr_router.py`

| Change | Detail |
|--------|--------|
| Prefix | `"/excel-cr"` → `"/api/v1/excel-cr"` |
| `upload-source` | `response_model=UploadSourceResponse`, `summary="Upload file nguồn chi phí"` |
| `upload-template` | `response_model=UploadTemplateResponse`, `summary="Upload file template Excel"` |
| `aggregate` | `response_model=AggregateResponse`, `summary="Tổng hợp & match tự động"` |
| `llm-review` | `response_model=LlmReviewResponse`, `summary="LLM gợi ý cho dòng chưa khớp"` |
| `confirm` | Body type `list[ConfirmItem]`, `response_model=ConfirmResponse`, `summary="Xác nhận mapping"` |
| `download` | No `response_model` (binary stream). Add `responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}}`, `summary="Tải file Excel kết quả"` |
| `GET /rules` | `response_model=RulesResponse`, `summary="Xem rules mapping"` |
| `POST /rules` | Request body typed as `RulesResponse`, `summary="Cập nhật rules mapping"` |

All Excel-CR routes: `tags=["excel-cr"]`

## Modified: `router.py` (invoice)

Add `summary` and ensure `tags=["invoices"]` on each route:

| Endpoint | Summary |
|----------|---------|
| `POST /jobs` | Upload hóa đơn PDF/XML |
| `GET /jobs` | Danh sách hóa đơn |
| `GET /jobs/{id}` | Chi tiết hóa đơn |
| `POST /jobs/{id}/confirm` | Xác nhận hóa đơn |
| `POST /jobs/{id}/reject` | Từ chối hóa đơn |
| `GET /exports/{year}/{month}` | Tải Excel tổng hợp tháng |

## Modified: `main.py`

```python
app = FastAPI(
    title="Thu Hóa Đơn API",
    version="1.0.0",
    description="API thu thập và xử lý hóa đơn điện tử từ email. Swagger UI: /docs",
    openapi_tags=[
        {"name": "invoices", "description": "Xử lý hóa đơn PDF/XML từ email"},
        {"name": "excel-cr", "description": "Tổng hợp chi phí vào template Excel (Excel-CR)"},
    ],
)
```

## New File: `docs/api-endpoints.md`

Full API reference extracted from `huong-dan-excel-cr.md` Section 4 + expanded with invoice endpoints. Structure:

```
# API Reference — Thu Hóa Đơn
## Base URL & Swagger
## Invoice Endpoints (/api/v1/jobs/*)
## Excel-CR Endpoints (/api/v1/excel-cr/*)
## Changelog
```

## Error Handling

No change to error behavior. Schemas only affect OpenAPI generation, not runtime validation of outgoing responses (FastAPI validates if `response_model` is set — existing passing tests confirm shape is correct).

## Testing

- Start server: `uvicorn app.main:app --reload`
- Visit `http://localhost:8000/docs` — verify all endpoints have summary + schema
- Visit `http://localhost:8000/openapi.json` — verify no `{}` response schemas remain
- Test prefix change: `GET /api/v1/excel-cr/rules` returns 200 (old `/excel-cr/rules` → 404)

## Migration Note

**Breaking change** for any existing FE/client calling `/excel-cr/*` directly. After this change, all calls must use `/api/v1/excel-cr/*`.
