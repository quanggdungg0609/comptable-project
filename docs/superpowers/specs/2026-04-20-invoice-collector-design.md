# Invoice Collector — Design Spec
**Date:** 2026-04-20  
**Stack:** Python 3.11+, FastAPI, Ollama/gemma4:e2b, RustFS, Docker Compose  
**Target:** Raspberry Pi 4B 8GB RAM hoặc Pi 5

---

## Mục tiêu

Hệ thống hỗ trợ phòng kế toán tự động thu thập và tổng hợp hóa đơn điện tử (PDF/XML) vào Bảng kê hóa đơn GTGT hàng mua vào (mẫu kèm tờ khai 01/GTGT).

- **Luồng chính:** Hệ thống lắng nghe email có subject `[Hóa đơn] ...` → tải attachment về → lưu vào thư mục chờ → **thông báo nhân viên** (Telegram/Slack/Console) → nhân viên vào web app review/sửa → xác nhận → ghi XLS + lưu RustFS
- **Luồng thủ công (fallback):** Nhân viên có thể upload thủ công qua web app khi cần

---

## Kiến trúc tổng thể

### Docker Compose Services

```
app (FastAPI :8000) ──▶ ollama (:11434)
                   ──▶ rustfs (:9000)
```

- **`app`**: FastAPI — chứa email listener (background task), xử lý upload, processing pipeline, UI (Jinja2 + HTMX), REST API `/api/v1/...`
- **`ollama`**: Chạy gemma4:e2b local, expose OpenAI-compatible API
- **`rustfs`**: Local S3-compatible object storage

### Clean Architecture Layers

```
presentation → application → domain ← infrastructure
```

Dependencies chảy vào trong. Domain không biết gì về infrastructure. Infrastructure implement các port định nghĩa trong domain.

```
app/
├── domain/                  # Không phụ thuộc gì
│   ├── entities/            # InvoiceItem, ProcessingJob
│   ├── value_objects/       # InvoiceStatus, FileType
│   └── ports/               # IStoragePort, ILLMPort, IJobRepository, IExcelPort, INotificationPort
│
├── application/             # Phụ thuộc domain only
│   └── use_cases/           # ProcessInvoice, ReviewAndConfirm, ExportToXLS
│
├── infrastructure/          # Implements domain ports
│   ├── storage/             # RustFS/S3 client (boto3)
│   ├── llm/                 # Ollama client
│   ├── parsers/             # markitdown (PDF), lxml (XML)
│   ├── excel/               # openpyxl writer
│   ├── notifications/       # Telegram, Slack, Console adapters
│   └── email/               # IMAP client, attachment extractor, background listener
│
└── presentation/            # Phụ thuộc application use cases
    ├── api/                 # REST /api/v1/... (cho React/mobile sau này)
    └── web/                 # Jinja2 + HTMX routes
```

---

## Processing Pipeline

```
Email với subject [Hóa đơn] đến hộp thư
      │
      ▼
IMAP Listener (background task, poll mỗi N phút)
      │
      ▼ Tải attachment PDF/XML
      │
      ├── Có cả XML + PDF cùng hóa đơn? → ghép cặp theo base filename
      │       (invoice_test.xml + invoice_test.pdf) → dùng XML, lưu PDF vào RustFS
      │
      ├── XML branch: lxml parse → raw text → LLM → InvoiceItem
      └── PDF branch: markitdown → markdown text → LLM → InvoiceItem
                                                    │
                                          Status: AWAITING_REVIEW
                                                    │
                                  Thông báo nhân viên (Telegram/Slack/Console)
                                    "Hóa đơn mới cần phê duyệt: invoice_test.xml"
                                                    │
                                              Review UI (web)
                                    (nhân viên xem, sửa từng field)
                                         Confirm / Reject
                                              │
                          Confirm → ghi XLS + lưu RustFS + đánh dấu CONFIRMED trong DB
                          Reject  → status "rejected", không ghi XLS
```

**Note:** Sample files available for testing in `tests/samples/`:
- `invoice_test.pdf` - Vietnamese e-invoice PDF (supplier: "CÔNG TY TNHH ĐẦU TƯ VÀ VẬN TẢI AN PHÚ")
- `invoice_test.xml` - Corresponding XML file with structured invoice data

### Upload thủ công (fallback)

Nhân viên có thể vào web app upload PDF/XML trực tiếp — pipeline giống hệt luồng email từ bước parse trở đi.

### Trạng thái ProcessingJob

```
PENDING → PROCESSING → AWAITING_REVIEW → CONFIRMED
                    ↘                  ↘ REJECTED
                     FAILED
```

---

## Domain Entities

### InvoiceItem
Các trường trích xuất từ hóa đơn — mapping trực tiếp với cột trong Bảng kê thuế:

| Field | Tên hiển thị | Kiểu |
|---|---|---|
| `invoice_symbol` | Ký hiệu hóa đơn | `str` |
| `invoice_number` | Số hóa đơn | `str` |
| `invoice_date` | Ngày phát hành | `date` |
| `seller_name` | Tên người bán | `str` |
| `seller_tax_code` | Mã số thuế người bán | `str` |
| `description` | Mặt hàng / dịch vụ | `str` |
| `price_before_tax` | Doanh số chưa thuế | `Decimal` |
| `tax_rate` | Thuế suất | `Decimal` (0.08 / 0.10) |
| `price_after_tax` | Thuế GTGT | `Decimal` |

### ProcessingJob
```python
id: UUID
filename: str
file_type: FileType           # PDF | XML
status: InvoiceStatus
extracted_items: list[InvoiceItem]
source_paths: list[str]       # RustFS paths sau khi CONFIRMED
created_at: datetime
error: str | None
pending_file_path: str | None # local temp path cho đến khi CONFIRMED
```

### Domain Ports
```
IStoragePort        → upload_file(), download_file(), get_presigned_url()
ILLMPort            → extract_invoice(text: str) -> list[InvoiceItem]
IJobRepository      → save(), get(), list_all(), update_status(), ...  # backed by SQLite
IExcelPort          → append_rows(items, year, month, existing_data) -> bytes
INotificationPort   → notify_new_invoice(job_id: str, filename: str) -> None
```

---

## API Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/v1/jobs` | Upload 1 hoặc nhiều file (manual fallback) |
| `GET` | `/api/v1/jobs` | Danh sách jobs (filter by status) |
| `GET` | `/api/v1/jobs/{id}` | Chi tiết job + extracted data |
| `PATCH` | `/api/v1/jobs/{id}/review` | Submit data đã sửa |
| `POST` | `/api/v1/jobs/{id}/confirm` | Xác nhận → ghi XLS + lưu RustFS |
| `POST` | `/api/v1/jobs/{id}/reject` | Từ chối hóa đơn |
| `GET` | `/api/v1/exports/{year}/{month}` | Download file XLS tổng hợp |

Web routes (`/web/...`) gọi các use case tương tự — không duplicate logic.

---

## Application Use Cases

- **ProcessInvoiceUseCase** — nhận file → detect type → parse → gọi LLM → tạo ProcessingJob `AWAITING_REVIEW` → **gọi INotificationPort** để thông báo
- **ReviewAndConfirmUseCase** — nhận data đã review → validate → ghi XLS (append) → upload file gốc lên RustFS → status `CONFIRMED`
- **ExportExcelUseCase** — generate / download `Bang_ke_thue_{year}_{month}.xlsx`

---

## Notification Service

### INotificationPort
```python
async def notify_new_invoice(job_id: str, filename: str) -> None
```

### Implementations

| Type | Mô tả |
|---|---|
| `TelegramNotifier` | Gửi message qua Telegram Bot API. Cần `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` |
| `SlackNotifier` | POST tới Slack Incoming Webhook URL |
| `ConsoleNotifier` | In ra stdout — dùng khi dev/test hoặc chưa cấu hình |

Message mẫu (Telegram):
```
📄 Hóa đơn mới cần phê duyệt
File: HD0049.xml
👉 http://localhost:8000/jobs/{job_id}/review
```

Nếu notification fail → log warning, **không** fail job.

### Cấu hình
```
NOTIFICATION_TYPE=telegram     # telegram | slack | console
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
SLACK_WEBHOOK_URL=...
APP_BASE_URL=http://localhost:8000
```

---

## Email Listener (IMAP)

Background task chạy bên trong tiến trình `app` (không phải service riêng).

```
infrastructure/email/
├── imap_client.py           # Kết nối IMAP (stdlib imaplib + asyncio.to_thread)
├── attachment_extractor.py  # Lấy .pdf/.xml từ email (stdlib email module)
└── email_listener.py        # Background task, poll mỗi N giây
```

**Subject filter:** Fetch UNSEEN emails → lọc trong Python: `"[Hóa đơn]" in subject`

**Flow:**
1. Poll INBOX, lấy UNSEEN có `[Hóa đơn]` trong subject
2. Đánh dấu email đã đọc (`\Seen`)
3. Trích attachment PDF/XML
4. Ghép cặp XML+PDF theo base filename
5. Gọi `ProcessInvoiceUseCase.execute()` cho từng cặp/file
6. Use case tự gửi thông báo sau khi tạo job

**Config:**
```
IMAP_HOST=mail.example.com
IMAP_PORT=993
IMAP_USERNAME=ketoan@example.com
IMAP_PASSWORD=...
IMAP_USE_SSL=true
EMAIL_LISTENER_ENABLED=true
EMAIL_POLL_INTERVAL=300       # giây
```

Listener khởi động khi `EMAIL_LISTENER_ENABLED=true`. Khi `false`, chỉ dùng web upload thủ công.

---

## File Storage Structure (RustFS)

```
s3://invoices/{năm}/{tháng:02d}/{tên_khách_hàng}/{invoice_number}.pdf
s3://invoices/{năm}/{tháng:02d}/{tên_khách_hàng}/{invoice_number}.xml
s3://exports/Bang_ke_thue_{năm}_{tháng:02d}.xlsx
```

File XLS tổng hợp được **append** mỗi khi confirm — không ghi đè toàn bộ.

Pending files lưu local tại `data/pending/{job_id}.{ext}` cho đến khi CONFIRMED, sau đó xóa.

---

## Error Handling

| Tình huống | Xử lý |
|---|---|
| File không phải PDF/XML | Reject ngay, trả lỗi rõ ràng |
| LLM trả JSON không hợp lệ | Retry 2 lần → nếu vẫn lỗi: status `FAILED`, nhân viên nhập tay |
| RustFS không kết nối | Job giữ `CONFIRMED`, retry upload khi reconnect |
| XML sai schema hóa đơn VN | Fallback sang PDF nếu có, không thì `FAILED` |
| Ollama chưa load model | Health check trước khi nhận job, UI hiện "hệ thống đang khởi động" |
| IMAP kết nối lỗi | Log error, tiếp tục poll vòng sau, không crash app |
| Thông báo gửi thất bại | Log warning, không fail job |
| Email không có attachment hợp lệ | Bỏ qua, không tạo job |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI |
| UI | Jinja2 + HTMX + Bootstrap 5 |
| Future UI | REST API sẵn sàng cho React / mobile |
| LLM | Ollama + gemma4:e2b (local) |
| PDF parse | markitdown |
| XML parse | lxml |
| Object storage | RustFS (boto3, S3-compatible) |
| Excel | openpyxl |
| IMAP | stdlib imaplib + asyncio.to_thread |
| Email parse | stdlib email module |
| Notification | httpx (Telegram/Slack) |
| Container | Docker Compose |
| Runtime | Python 3.11+, Raspberry Pi 4B 8GB / Pi 5 |
