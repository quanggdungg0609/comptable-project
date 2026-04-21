# Invoice Line Items (Chi Tiết Hàng Hóa) — Design Spec

**Date:** 2026-04-21  
**Status:** Approved

## Overview

Thêm tính năng trích xuất và lưu trữ từng dòng hàng hóa/dịch vụ (line items) từ hóa đơn vào một bảng riêng, hiển thị và chỉnh sửa được trên trang review, và xuất ra file Excel chi tiết riêng khi confirm.

---

## 1. Data Model

### Entity: `InvoiceLineItem`
File: `app/domain/entities/invoice_line_item.py`

| Field | Type | Description |
|---|---|---|
| `id` | str (UUID) | Primary key |
| `invoice_symbol` | str | Ký hiệu hóa đơn |
| `invoice_number` | str | Số hóa đơn |
| `invoice_date` | date | Ngày phát hành |
| `seller_name` | str | Tên nhà cung cấp |
| `seller_tax_code` | str | Mã số thuế người bán |
| `ten_hang_hoa` | str | Tên mặt hàng / dịch vụ |
| `don_vi_tinh` | str | Đơn vị tính |
| `so_luong` | Decimal | Số lượng |
| `don_gia` | Decimal | Đơn giá |
| `thanh_tien` | Decimal | Thành tiền (so_luong × don_gia) |
| `tax_rate` | Decimal | Thuế suất (0.08, 0.10, v.v.) |
| `tax_amount` | Decimal | Thuế GTGT |

### DB Table: `invoice_line_items`
```sql
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
```

### `ProcessingJob` entity
Thêm field: `extracted_line_items: list[InvoiceLineItem] = field(default_factory=list)`

### Repository (`IJobRepository` + `SQLiteJobRepository`)
Thêm 3 method:
- `save_line_items(job_id, items: list[InvoiceLineItem]) -> None`
- `update_line_items(job_id, items: list[InvoiceLineItem]) -> None`
- `get()` tự load `invoice_line_items` kèm theo khi fetch job

---

## 2. Extraction Layer

### XML — `extract_line_items_from_xml(data: bytes) -> list[InvoiceLineItem]`
File: `app/infrastructure/parsers/xml_parser.py`

- Đọc header một lần: `KHHDon`, `SHDon`, `NLap`, `NBan.Ten`, `NBan.MST`
- Duyệt từng `<HHDVu>`, skip dòng `SLuong == 0`
- Lấy: `THHDVu` → `ten_hang_hoa`, `DVTinh` → `don_vi_tinh`, `SLuong`, `DGia`, `ThTien` → `thanh_tien`, `TSuat` → `tax_rate`, `TThue` → `tax_amount`
- Gán header vào mỗi line item
- Không cần LLM, hoàn toàn deterministic

### PDF / LLM — Cập nhật `EXTRACTION_PROMPT`
File: `app/infrastructure/llm/ollama_client.py` (dùng chung cho cả Gemini)

Prompt yêu cầu trả về JSON với hai key:
```json
{
  "items": [/* gộp theo thuế suất — giữ nguyên format cũ */],
  "line_items": [
    {
      "ten_hang_hoa": "...",
      "don_vi_tinh": "kg",
      "so_luong": 10,
      "don_gia": 50000,
      "thanh_tien": 500000,
      "tax_rate": 0.10,
      "tax_amount": 50000
    }
  ]
}
```

- Header (invoice_symbol, invoice_number, invoice_date, seller_name, seller_tax_code) kế thừa từ `items[0]` khi parse — LLM không cần lặp lại cho mỗi line item.
- `maxOutputTokens` tăng lên 2048 (để chứa thêm line_items).

### Processing use case (`process_invoice.py`)
- XML flow: sau khi extract `items` → gọi `extract_line_items_from_xml()` → `repo.save_line_items()`
- PDF/LLM flow: parse `line_items` từ LLM response → gán header từ `items[0]` → `repo.save_line_items()`

---

## 3. Review Page & Confirm

### Review page (`review.html`)
- Giữ nguyên phần invoice_items cards hiện tại (bên phải, trên)
- Thêm section mới bên dưới: **bảng chi tiết có thể chỉnh sửa**
  - Header: "Chi tiết hàng hóa/dịch vụ — X dòng"
  - Mỗi dòng trong `<table>` với ô `<input>` cho: tên hàng hóa, đơn vị tính, số lượng, đơn giá, thành tiền, thuế suất, thuế GTGT
  - JS tự tính lại `thanh_tien` khi user sửa `so_luong` hoặc `don_gia`
  - Name của input: `li_ten_hang_hoa_{id}`, `li_don_vi_tinh_{id}`, v.v. (prefix `li_` để phân biệt)

### Confirm handler (`web/router.py` — `POST /jobs/{job_id}/confirm`)
- Parse thêm line item fields từ form data
- Rebuild list `InvoiceLineItem`
- Gọi `repo.update_line_items(job_id, line_items)` trước khi confirm

### Confirm use case (`review_and_confirm.py`)
- Nhận thêm tham số `line_items: list[InvoiceLineItem]`
- Sau khi export Excel tổng hợp → export thêm Excel chi tiết
- Gọi `ExcelDetailPort.append_rows()` → upload lên storage

---

## 4. Excel Chi Tiết

### Port mới: `IExcelDetailPort`
File: `app/domain/ports/excel_detail_port.py`

```python
class IExcelDetailPort(ABC):
    async def append_rows(
        self, items: list[InvoiceLineItem], year: int, month: int, existing_data: bytes
    ) -> tuple[str, bytes]: ...
```

### Writer: `OpenpyxlDetailWriter`
File: `app/infrastructure/excel/openpyxl_detail_writer.py`

- Load từ template `Mau_xuat_du_lieu_chi_tiet.xlsx` (hoặc existing monthly file)
- Append mỗi `InvoiceLineItem` theo mapping cột:

| Cột | Nội dung |
|---|---|
| A | STT |
| B | *(trống — Ký hiệu mẫu HĐ không có trong data)* |
| C | invoice_symbol |
| D | invoice_number |
| E | invoice_date |
| F | seller_name |
| G | seller_tax_code |
| H | ten_hang_hoa |
| I | don_vi_tinh |
| J | so_luong |
| K | don_gia |
| L | thanh_tien |
| M | tax_rate (%) |
| N | tax_amount |

- Filename: `Chi_tiet_hoa_don_T{month}_{year}.xlsx`
- Lưu lên RustFS bucket `exports` cùng với file tổng hợp

### Dependency injection (`dependencies.py`)
- Thêm `get_excel_detail_writer()` factory

---

## 5. API Schemas

`InvoiceLineItemSchema` (Pydantic) thêm vào `schemas.py`.  
`JobResponse` thêm field `extracted_line_items: list[InvoiceLineItemSchema]`.

---

## Out of Scope

- Export chi tiết qua API endpoint riêng (chỉ trigger lúc confirm)
- Tìm kiếm/lọc theo tên hàng hóa
- Merge/split line items trên UI
