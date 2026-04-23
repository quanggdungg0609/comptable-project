# Hướng Dẫn Test Email với Invoice

## Tổng Quan

Ứng dụng đã được cấu hình để lắng nghe email Gmail. Bạn có thể gửi email với file hóa đơn (PDF hoặc XML) để test quy trình xử lý tự động.

## Định Dạng File Hỗ Trợ

### 1. **XML** (Recommended - E-Invoice)
- Định dạng: Hóa đơn điện tử theo chuẩn Việt Nam
- Ưu điểm: Đã có thông tin chi tiết (items, taxes, etc.)
- Ví dụ: `tests/samples/invoice_test.xml`

### 2. **PDF** (Invoice)
- Định dạng: File PDF chứa hóa đơn
- Ưu điểm: Có thể gửi hóa đơn từ các nhà cung cấp
- App sẽ dùng OCR/LLM để trích xuất thông tin

## Cách Gửi Email Test

### Cách 1: Gửi từ Gmail Web
1. Mở [Gmail](https://gmail.com)
2. Nhấn "Viết" (Compose)
3. **Địa chỉ nhận**: chu0tc0n196@gmail.com (Tài khoản bạn đã cấu hình)
4. **Chủ đề**: Bất kỳ (ví dụ: "Invoice Test", "Hóa Đơn Vận Chuyển")
5. **Nội dung**: Mô tả hoặc để trống
6. **Đính kèm file**: Chọn file XML hoặc PDF
7. Nhấn "Gửi" (Send)

### Cách 2: Gửi từ Outlook/Email khác
- Tương tự Gmail Web
- Gửi đến: chu0tc0n196@gmail.com
- Đính kèm: File PDF hoặc XML

### Cách 3: Gửi từ Terminal (Test Script)
```bash
# Cần cài đặt: pip install yagmail

python3 << 'EOF'
import yagmail

yag = yagmail.SMTP('chu0tc0n196@gmail.com', 'dqumwozpjljydxaa')
yag.send(
    'chu0tc0n196@gmail.com',
    subject='Invoice Test',
    contents='Test invoice file',
    attachments=['tests/samples/invoice_test.xml']
)
print("Email sent successfully!")
EOF
```

## Sample Files để Test

### File XML (E-Invoice)
```
tests/samples/invoice_test.xml
```
- Hóa đơn điện tử từ CÔNG TY TNHH ĐẦU TƯ VÀ VẬN TẢI AN PHÚ
- Ngày tạo: 18/03/2026
- Ký hiệu: C26TAA
- Số HĐ: 00000064
- Tổng tiền: 480,600,000 VND

### File PDF (Invoice)
```
tests/samples/invoice_test.pdf
```
- PDF sample cho testing

## Quy Trình Xử Lý Tự Động

### 1. **Email Arrives** (Liên tục 5 phút một lần)
```
[EmailListener] Email listener started (polling every 300s)
[EmailListener] Poll cycle #1 starting
[EmailListener] Connecting to IMAP server
[EmailListener] Found 1 new emails
[EmailListener] Email 1/1 - From: user@example.com, Subject: Invoice Test
```

### 2. **Tải File & Trích Xuất Dữ Liệu**
```
[ProcessInvoice] Starting processing for job <JOB_ID>: invoice_test.xml (XML)
[ProcessInvoice] File saved: data/pending/<JOB_ID>.xml
[ProcessInvoice] Extracted 12 line items from XML
[ProcessInvoice] LLM extracted 1 invoice items
```

### 3. **Kiểm Tra Trùng Lặp**
```
[ProcessInvoice] Checking for duplicates: C26TAA/00000064 from 0201582012
[ProcessInvoice] No duplicate found
[ProcessInvoice] Job status set to AWAITING_REVIEW
```

### 4. **Thông Báo Người Dùng**
```
[ProcessInvoice] Notification sent for job <JOB_ID>
```

## Theo Dõi Kết Quả

### 1. **Xem Logs Real-time**
```bash
tail -f logs/app.log
```

### 2. **Lọc Logs cho Email Processing**
```bash
grep "\[EmailListener\]\|\[ProcessInvoice\]" logs/app.log
```

### 3. **Xem Job Cụ Thể**
```bash
# Thay JOB_ID bằng ID từ logs
grep "550e8400-e29b-41d4-a716-446655440000" logs/app.log
```

### 4. **Kiểm Tra Web UI**
- Mở: http://localhost:8000
- Xem trong phần "Jobs" hoặc dashboard
- Job status sẽ là: AWAITING_REVIEW

## Các Tình Huống Test

### Test 1: Email với File XML
**Input:**
- Email từ: user@example.com
- Subject: "Hóa Đơn E-Invoice"
- Attachment: `invoice_test.xml`

**Expected Output:**
- ✅ Job created
- ✅ 12 line items extracted
- ✅ Status: AWAITING_REVIEW
- ✅ Logs show successful processing

---

### Test 2: Email với File PDF
**Input:**
- Email từ: user@example.com
- Subject: "Invoice PDF"
- Attachment: File PDF bất kỳ

**Expected Output:**
- ✅ Job created
- ✅ LLM extracts invoice data
- ✅ Status: AWAITING_REVIEW
- ⚠️ Có thể cần review/edit vì OCR không chính xác 100%

---

### Test 3: Email Không Có File
**Input:**
- Email từ: user@example.com
- Subject: "Test"
- Attachment: KHÔNG

**Expected Output:**
- ❌ Email ignored (no attachment)
- ℹ️ Logs show: "No attachment found"

---

### Test 4: Email với File Không Hỗ Trợ
**Input:**
- Email từ: user@example.com
- Subject: "Test"
- Attachment: `.docx`, `.txt`, etc.

**Expected Output:**
- ❌ Job failed
- ❌ Logs show: "Unsupported file type: .docx"

---

### Test 5: Duplicate Invoice
**Input:**
- Gửi cùng file 2 lần

**Expected Output:**
- ✅ Job 1 created - Status: AWAITING_REVIEW
- ⚠️ Job 2 created - Status: DUPLICATE
- ✅ Logs show: "Found duplicate! Job X is duplicate of Job Y"

## Troubleshooting

### Email không được xử lý?

**Kiểm tra 1: Email Listener đang chạy?**
```bash
grep "\[EmailListener\] Email listener started" logs/app.log
```

**Kiểm tra 2: IMAP kết nối OK?**
```bash
grep "\[IMAPClient\] Successfully connected" logs/app.log
```

**Kiểm tra 3: Có email mới?**
```bash
grep "\[EmailListener\] Found.*emails" logs/app.log
```

**Kiểm tra 4: File hỗ trợ?**
- File phải là `.pdf` hoặc `.xml`
- Kiểm tra kích thước file

---

### Job failed?

**Xem chi tiết lỗi:**
```bash
grep "\[ProcessInvoice\] Job .* failed:" logs/app.log
grep "ERROR" logs/error.log
```

**Các lỗi phổ biến:**
1. **Unsupported file type** - File không phải PDF/XML
2. **File read error** - File bị corrupt
3. **LLM extraction failed** - Lỗi kết nối LLM (Gemini/Ollama)
4. **Database error** - Lỗi lưu vào database

---

### Email listener không tìm được email?

**Nguyên nhân:**
1. Gmail không nhận được email
2. Email không mark as UNSEEN
3. IMAP timeout

**Giải pháp:**
1. Kiểm tra email đã đến Gmail
2. Refresh email (có thể cần gửi lại)
3. Kiểm tra IMAP connection logs

---

### App không nhận được email mới?

**Nguyên nhân:**
- Email Listener disabled trong .env
- Các cấu hình Gmail sai

**Giải pháp:**
```bash
# Kiểm tra .env
grep "EMAIL_LISTENER_ENABLED\|IMAP_" .env

# Nên có:
# EMAIL_LISTENER_ENABLED=true
# IMAP_HOST=imap.gmail.com
# IMAP_PORT=993
# IMAP_USERNAME=chu0tc0n196@gmail.com
# IMAP_PASSWORD=dqumwozpjljydxaa
```

## Performance Notes

- **Poll Interval**: 300 giây (5 phút) - Có thể sửa `EMAIL_POLL_INTERVAL` trong .env
- **Fetch Limit**: 10 email cuối cùng mỗi lần poll
- **Processing**: Xử lý song song (async)

## Next Steps Sau Test

1. **Review Job**: Mở job trong UI, kiểm tra dữ liệu trích xuất
2. **Edit (Nếu Cần)**: Sửa những thông tin không chính xác
3. **Confirm**: Nhấn Confirm để lưu vào Excel export
4. **Download**: Xuất Excel reports

---

## Ví Dụ Log Hoàn Chỉnh

```
[2026-04-23 19:47:00] INFO [EmailListener:start:18] Email listener started (polling every 300s)
[2026-04-23 19:47:05] DEBUG [EmailListener:start:23] Poll cycle #1 starting
[2026-04-23 19:47:05] DEBUG [EmailListener:start:25] Connecting to IMAP server
[2026-04-23 19:47:06] INFO [IMAPClient:connect:42] Connected and authenticated to imap.gmail.com:993 as chu0tc0n196@gmail.com
[2026-04-23 19:47:06] DEBUG [EmailListener:start:29] Fetching new emails
[2026-04-23 19:47:07] INFO [EmailListener:start:30] Found 1 new emails
[2026-04-23 19:47:07] INFO [EmailListener:start:35] Email 1/1 - From: user@example.com, Subject: Invoice Test
[2026-04-23 19:47:08] INFO [ProcessInvoice:execute:26] Starting processing for job 550e8400-e29b-41d4-a716-446655440000: invoice_test.xml (XML)
[2026-04-23 19:47:09] INFO [ProcessInvoice:execute:54] File saved: data/pending/550e8400-e29b-41d4-a716-446655440000.xml
[2026-04-23 19:47:10] INFO [ProcessInvoice:execute:61] Extracted 12 line items from XML
[2026-04-23 19:47:12] INFO [ProcessInvoice:execute:64] LLM extracted 1 invoice items
[2026-04-23 19:47:13] INFO [ProcessInvoice:execute:81] Job 550e8400-e29b-41d4-a716-446655440000 status set to AWAITING_REVIEW
[2026-04-23 19:47:14] INFO [ProcessInvoice:execute:108] Successfully completed job 550e8400-e29b-41d4-a716-446655440000
```

---

## Tips for Testing

1. **Gửi từ nhiều email khác nhau** để test các sender khác nhau
2. **Test cả PDF và XML** để đảm bảo cả format đều hoạt động
3. **Xem logs cùng lúc** khi gửi email để theo dõi real-time
4. **Test duplicate** bằng cách gửi cùng file 2 lần
5. **Check web UI** để xem job details sau khi processing

---

## Chạy Test Tự Động (Optional)

Để test tự động mà không cần gửi email thực tế, bạn có thể tạo test script:

```python
# test_email_processing.py
import asyncio
from app.core.config import get_settings
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase

async def test_invoice_processing():
    settings = get_settings()
    
    with open('tests/samples/invoice_test.xml', 'rb') as f:
        file_data = f.read()
    
    # Initialize use case (need repo, llm, notification)
    # ... setup code ...
    
    job = await process_uc.execute(
        filename='invoice_test.xml',
        file_data=file_data,
        paired_pdf=None
    )
    
    print(f"Job ID: {job.id}")
    print(f"Status: {job.status}")
    print(f"Items: {len(job.extracted_items)}")

asyncio.run(test_invoice_processing())
```

Thực hiện: `python test_email_processing.py`
