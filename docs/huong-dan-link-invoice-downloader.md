# Hướng dẫn: Link Invoice Downloader

**Ngày:** 2026-05-01  
**Tính năng:** Tự động tải hóa đơn từ link trong email (không có file đính kèm)

---

## 1. Tính năng làm gì?

Một số nhà cung cấp (VNPT, Fast e-Invoice...) **không đính kèm file PDF/XML** vào email mà chỉ nhúng link tải về trong thân email HTML.

Trước đây: hệ thống bỏ qua những email không có đính kèm.  
Từ nay: hệ thống tự phát hiện link, tải file về, xử lý như bình thường.

---

## 2. Luồng hoạt động

```
Email nhận
  ├── Có đính kèm (PDF/XML) → pipeline cũ (không đổi)
  └── Không có đính kèm?
        → Trích xuất HTML body
        → Chấm điểm tất cả <a href> trong email
        → HTTP GET các link điểm cao nhất
        → Lọc theo Content-Type (pdf/xml)
        → Inject vào pipeline như attachment bình thường
```

---

## 3. Hệ thống chấm điểm link

Hệ thống tự động chấm điểm từng link trong email:

| Tín hiệu | Điểm |
|----------|------|
| Anchor text chứa "pdf" hoặc "xml" | +3 mỗi từ |
| Anchor text chứa "tải", "download", "click here", "nhấn vào đây" | +2 |
| Anchor text chứa "hóa đơn", "invoice" | +1 |
| URL kết thúc bằng `.pdf` hoặc `.xml` | +3 |
| URL chứa "download", "pdf", "xml", "invoice", "export" | +2 |
| Text xung quanh link chứa "PDF" hoặc "XML" | +1 |

**Ngưỡng:** score ≥ 3 → link được chọn  
**Giới hạn:** tối đa 5 link/email  
**Loại trùng:** bỏ qua href giống nhau

---

## 4. Đặt tên file tải về

Thứ tự ưu tiên:
1. Header `Content-Disposition: attachment; filename=...` trong response
2. Tên file từ URL path (ví dụ: `/files/invoice_123.pdf`)
3. Fallback: `invoice.pdf` hoặc `invoice.xml`

---

## 5. Kiểm tra hoạt động (Testing)

### 5.1. Kiểm tra log

Khi email không có đính kèm nhưng có link hóa đơn, log sẽ hiển thị:

```
[EmailListener] No attachments found in email <id>, checking for download links...
[EmailListener] Found 2 potential invoice links in email <id>
[LinkDownloader] Downloading https://example.com/invoice.pdf
[EmailListener] Successfully downloaded 2 files from links
```

Nếu không tìm được link nào:
```
[EmailListener] No attachments or valid download links found in email <id>
```

### 5.2. Test thủ công với HTML mẫu

```python
from app.infrastructure.parsers.link_extractor import extract_scored_links

html = """
<p>Vui lòng <a href="https://example.com/download/invoice_123.pdf">tải PDF hóa đơn</a> tại đây.</p>
"""

links = extract_scored_links(html)
# Kết quả mong đợi:
# [{'url': 'https://example.com/download/invoice_123.pdf', 'inferred_type': 'pdf', 'score': 10}]
print(links)
```

### 5.3. Test tải file

```python
import asyncio
from app.infrastructure.email.invoice_link_downloader import download_invoices_from_links

links = [
    {"url": "https://example.com/invoice.pdf", "inferred_type": "pdf", "score": 8}
]

results = asyncio.run(download_invoices_from_links(links))
# Kết quả: list of (filename, bytes)
for filename, data in results:
    print(f"Tải về: {filename} ({len(data)} bytes)")
```

### 5.4. Trường hợp cần test

| Trường hợp | Kết quả mong đợi |
|------------|-----------------|
| Email có link `.pdf` rõ ràng trong URL | Tải về, xử lý bình thường |
| Email có link với anchor text "tải hóa đơn" | Tải về nếu score ≥ 3 |
| Email có link nhưng server trả 404 | Log warning, bỏ qua link đó |
| Email có link nhưng Content-Type là `text/html` (không phải PDF/XML) | Bỏ qua, không inject |
| Email vừa có đính kèm vừa có link | Dùng đính kèm, không check link |
| Tất cả link đều fail | Email bị skip, log warning |

---

## 6. rules.json — Có cần tạo không?

**Không cần tạo thủ công.**

`rules.json` được quản lý bởi `RustfsRulesManager` và lưu trên RustFS tại:
```
config/rules.json
```

Khi chưa có file, hệ thống tự dùng cấu trúc mặc định:
```json
{
  "llm_confirmed": [],
  "keyword": [],
  "direct": []
}
```

File được tự động cập nhật mỗi khi người dùng xác nhận mapping trong tính năng Excel-CR.

### Cấu trúc rules.json

| Trường | Mô tả |
|--------|-------|
| `llm_confirmed` | Mapping do LLM đề xuất, người dùng đã xác nhận |
| `keyword` | Mapping dựa trên từ khóa trong tên hàng hóa |
| `direct` | Mapping trực tiếp (tên hàng → tài khoản kế toán) |

Để xem nội dung hiện tại, truy cập RustFS bucket `excel-cr` → `config/rules.json`.

---

## 7. Xử lý lỗi

| Lỗi | Hành vi |
|-----|---------|
| HTML parse error | Log error, trả về danh sách rỗng |
| Link download timeout (>30s) | Log warning, thử link tiếp theo |
| HTTP status != 200 | Log warning, thử link tiếp theo |
| Tất cả link thất bại | Email bị skip (giống hành vi cũ khi không có đính kèm) |
| Email có đính kèm | Không ảnh hưởng — tính năng này chỉ kích hoạt khi KHÔNG có đính kèm |
