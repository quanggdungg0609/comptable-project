# Duplicate Invoice Detection — Design Spec

**Date:** 2026-04-22
**Status:** Approved

## Problem

Cùng một hóa đơn có thể được upload nhiều lần với tên file khác nhau, hoặc bởi nhiều người khác nhau. Nếu cả hai job đều được review và confirm, hóa đơn đó sẽ bị tính hai lần trong export dữ liệu hàng tháng.

## Tiêu chí trùng lặp

Hai hóa đơn được coi là trùng nếu có cùng bộ `(invoice_symbol, invoice_number, seller_tax_code)` và job kia đang ở status `CONFIRMED` hoặc `AWAITING_REVIEW`.

- `FAILED` và `REJECTED` không tính là trùng — cho phép upload lại hóa đơn đã từ chối.
- Kiểm tra chỉ dựa trên `invoice_items` (bảng tổng hợp), không phải `invoice_line_items`.

## Luồng xử lý

1. User upload file → job được tạo, xử lý bình thường.
2. Sau khi `ProcessInvoiceUseCase` extract xong và lưu `invoice_items`:
   - Query tìm job nào có cùng `(invoice_symbol, invoice_number, seller_tax_code)` và status `CONFIRMED` hoặc `AWAITING_REVIEW`.
   - Nếu tìm thấy: set job mới thành `DUPLICATE`, ghi `duplicate_of = <job_id_gốc>`, dừng sớm (không gửi notification).
   - Nếu không tìm thấy: tiếp tục bình thường → `AWAITING_REVIEW` + notify.

## Database

### Migration — bảng `jobs`

Thêm cột:
```sql
ALTER TABLE jobs ADD COLUMN duplicate_of TEXT;
```

### InvoiceStatus enum

Thêm value: `DUPLICATE = "DUPLICATE"`

## Domain

### `ProcessingJob`

Thêm field: `duplicate_of: Optional[str] = None`

### `IJobRepository` — 2 method mới

```python
async def find_duplicate(
    self,
    invoice_symbol: str,
    invoice_number: str,
    seller_tax_code: str,
) -> Optional[ProcessingJob]: ...

async def update_duplicate_of(self, job_id: str, duplicate_of_id: str) -> None: ...
```

`find_duplicate` query:
```sql
SELECT DISTINCT j.id FROM jobs j
JOIN invoice_items ii ON ii.job_id = j.id
WHERE ii.invoice_symbol = ?
  AND ii.invoice_number = ?
  AND ii.seller_tax_code = ?
  AND j.status IN ('CONFIRMED', 'AWAITING_REVIEW')
LIMIT 1
```

## Application

### `ProcessInvoiceUseCase.execute()`

Sau `await self._repo.save_items(job.id, items)`, thêm:

```python
if items:
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
```

Không gửi notification cho job `DUPLICATE`.

## Presentation

### Trang `/jobs` (jobs.html)

Badge màu cam `Trùng lặp` cho job có status `DUPLICATE`.

### Trang `/jobs/{job_id}/review` (review.html)

Nếu `job.status == DUPLICATE`:
- Banner cảnh báo đỏ: "Hóa đơn này đã tồn tại trong hệ thống" + link đến `/jobs/{job.duplicate_of}/review`
- Nút Confirm ẩn/disabled
- Chỉ hiển thị nút "Từ chối"

### `POST /jobs/{job_id}/confirm` (web router)

Guard đầu handler: nếu `job.status == DUPLICATE` → raise `HTTPException(400, "Hóa đơn trùng lặp")`.

## Error handling

- Nếu `find_duplicate` raise exception: log warning, tiếp tục xử lý bình thường (không block job). Ưu tiên availability hơn correctness trong trường hợp lỗi DB.
- Nếu `items` rỗng (extract thất bại): bỏ qua duplicate check.

## Testing

- Unit test `find_duplicate`: trả về job khi có match `CONFIRMED`/`AWAITING_REVIEW`, trả về `None` khi status là `FAILED`/`REJECTED`.
- Unit test `ProcessInvoiceUseCase`: khi `find_duplicate` trả về job → status là `DUPLICATE`, `duplicate_of` được set, không gọi `notify`.
- Integration test: upload cùng hóa đơn 2 lần → job thứ 2 có status `DUPLICATE`.
- Presentation test: review page với job `DUPLICATE` → không có nút Confirm, có banner cảnh báo.
