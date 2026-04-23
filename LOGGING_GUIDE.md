# Hướng Dẫn Logging

## Tổng Quan

Ứng dụng đã được cập nhật với logging chi tiết trên tất cả các use cases và business logic để dễ dàng theo dõi quá trình xử lý.

## Cấu Hình Logging

Logging được cấu hình tự động khi ứng dụng khởi động. Xem: `app/core/logging_config.py`

### Cấp Độ Log

- **DEBUG**: Thông tin chi tiết cho mục đích debug
- **INFO**: Thông tin chung về quy trình chính
- **WARNING**: Cảnh báo (soft fail, fallback, etc.)
- **ERROR**: Lỗi (job failure, exception, etc.)

## Nơi Ghi Log

### 1. **Console Output**
- Tất cả log level INFO trở lên được in ra console
- Format: `[YYYY-MM-DD HH:MM:SS] LEVEL-8s MESSAGE`

### 2. **File Logs**

#### `logs/app.log` (Tất Cả Logs)
- Ghi tất cả log từ DEBUG level trở lên
- Tự động rotate khi đạt 10MB
- Lưu giữ 5 file backup

#### `logs/error.log` (Chỉ Lỗi)
- Ghi chỉ ERROR level logs
- Tự động rotate khi đạt 5MB
- Lưu giữ 3 file backup

## Log Prefixes (Dễ Dàng Theo Dõi)

Tất cả logs được đánh dấu với prefix để dễ dàng tìm kiếm:

### Application Lifecycle
```
[App Startup] - Khởi động ứng dụng
[App Shutdown] - Tắt ứng dụng
```

### Email Processing
```
[EmailListener] - Email listener operations
[IMAPClient] - IMAP client operations
```

### Invoice Processing
```
[ProcessInvoice] - Processing invoice use case
[ReviewAndConfirm] - Review and confirm use case
[ExportExcel] - Excel export operations
[GetExports] - Getting export data
```

## Theo Dõi Job Processing

### 1. Email Arrives
```
[EmailListener] Found 1 new emails
[EmailListener] Email 1/1 - From: sender@example.com, Subject: Invoice PDF
```

### 2. Processing Job
```
[ProcessInvoice] Starting processing for job 550e8400-e29b-41d4-a716-446655440000: invoice.pdf (PDF)
[ProcessInvoice] File saved: data/pending/550e8400-e29b-41d4-a716-446655440000.pdf
[ProcessInvoice] Extracted text from PDF
[ProcessInvoice] LLM extracted 1 invoice items
[ProcessInvoice] Saved 1 items to repository
[ProcessInvoice] No duplicate found
[ProcessInvoice] Job 550e8400-e29b-41d4-a716-446655440000 status set to AWAITING_REVIEW
[ProcessInvoice] Successfully completed job 550e8400-e29b-41d4-a716-446655440000
```

### 3. Review & Confirm
```
[ReviewAndConfirm] Preparing confirmation for job 550e8400-e29b-41d4-a716-446655440000
[ReviewAndConfirm] Updated 1 items and 1 line items
[ReviewAndConfirm] Saved updated items to repository
[ReviewAndConfirm] Job 550e8400-e29b-41d4-a716-446655440000 status set to CONFIRMING
[ReviewAndConfirm] Starting background finalization for job 550e8400-e29b-41d4-a716-446655440000
[ReviewAndConfirm] Uploading 1 files and generating Excel reports
[ReviewAndConfirm] All parallel tasks completed
[ReviewAndConfirm] Job 550e8400-e29b-41d4-a716-446655440000 successfully confirmed and finalized
```

## Trích Xuất Logs

### Xem Tất Cả Logs
```bash
tail -f logs/app.log
```

### Xem Lỗi
```bash
tail -f logs/error.log
```

### Lọc Logs Theo Từ Khóa
```bash
# Xem logs của một job cụ thể
grep "550e8400-e29b-41d4-a716-446655440000" logs/app.log

# Xem logs của invoice processing
grep "\[ProcessInvoice\]" logs/app.log

# Xem logs của email listener
grep "\[EmailListener\]" logs/app.log

# Xem logs của review & confirm
grep "\[ReviewAndConfirm\]" logs/app.log
```

### Xem Logs Với Timestamp
```bash
# Xem 100 dòng cuối cùng
tail -100 logs/app.log

# Xem logs từ thời điểm cụ thể
grep "2026-04-23 19:45:" logs/app.log
```

## Độ Chi Tiết Của Logs

### DEBUG Level
- Kết nối/đóng kết nối cơ sở dữ liệu
- Chi tiết về file I/O
- Chi tiết truy vấn cơ sở dữ liệu
- Chi tiết gọi API

### INFO Level
- Bắt đầu/kết thúc job processing
- Thay đổi trạng thái
- Các thao tác chính hoàn tất
- Số lượng items xử lý

### WARNING Level
- Duplicate detection
- Soft failures (notification failed, dup check failed)
- Fallback operations
- Timeout hoặc kết nối chậm

### ERROR Level
- Job failures
- Exceptions
- File not found
- Database errors

## Ví Dụ Sử Dụng

### 1. Theo Dõi Một Job Từ Bắt Đầu Đến Kết Thúc
```bash
grep "job_id_here" logs/app.log | grep -E "\[ProcessInvoice\]|\[ReviewAndConfirm\]"
```

### 2. Tìm Tất Cả Duplicates
```bash
grep "Found duplicate" logs/app.log
```

### 3. Tìm Tất Cả Failures
```bash
grep -E "\[ERROR\]|failed|FAILED" logs/app.log
```

### 4. Xem Tất Cả Email Processing
```bash
grep -E "\[EmailListener\]|\[IMAPClient\]" logs/app.log
```

### 5. Xem Thời Gian Xử Lý
```bash
# Xem thời gian bắt đầu và kết thúc của một job
grep "Starting processing\|Successfully completed" logs/app.log | head -2
```

## Performance Monitoring

Các log này giúp bạn:

1. **Theo dõi tiến độ**: Xem job đang ở trạng thái nào
2. **Debug issues**: Tìm ra lỗi chính xác ở đâu
3. **Phân tích hiệu suất**: Xem thời gian xử lý của từng bước
4. **Giám sát email listener**: Xem IMAP kết nối và lấy email thành công
5. **Kiểm tra duplicates**: Theo dõi các hóa đơn trùng lặp

## Cấu Hình Tùy Chỉnh

Để thay đổi log level hoặc cấu hình, sửa file:
```python
# app/main.py
setup_logging(logging.DEBUG)  # Thay logging.INFO thành logging.DEBUG để chi tiết hơn
```

## Troubleshooting

### Logs không hiển thị?
- Kiểm tra thư mục `logs/` tồn tại
- Kiểm tra quyền ghi file
- Kiểm tra log level trong `app/core/logging_config.py`

### Logs quá nhiều?
- Tăng log level: `logging.INFO` → `logging.WARNING`
- Lọc logs: `grep` khi cần

### Cần log ngay lập tức?
- Logs được flush tự động
- Sử dụng `tail -f` để theo dõi real-time
