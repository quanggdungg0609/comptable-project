# Telegram Notification Feature — Design Spec

**Date:** 2026-04-24  
**Status:** Approved

## Overview

Gửi thông báo Telegram tới nhóm chat kế toán khi có hóa đơn mới cần xem xét, khi hóa đơn được xác nhận, và khi hóa đơn bị từ chối.

## Thông tin Telegram

- **Bot:** `comptable123_bot`
- **Group chat:** Phòng Kế Toán (`-5268360021`)
- Config qua biến môi trường (không hardcode trong code)

## Kiến trúc

### 1. Mở rộng `INotificationPort`

Cập nhật `app/domain/ports/notification_port.py`:

- `notify_new_invoice` — cập nhật signature thêm `seller_name` và `invoice_number`
- Thêm 2 method abstract mới:

```python
@abstractmethod
async def notify_new_invoice(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
    """Thông báo hóa đơn mới cần xem xét."""

@abstractmethod
async def notify_confirmed(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
    """Thông báo hóa đơn đã được xác nhận."""

@abstractmethod
async def notify_rejected(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
    """Thông báo hóa đơn đã bị từ chối."""
```

`seller_name` và `invoice_number` được truyền từ `items[0]` (đã có sau khi LLM xử lý xong). Nếu `items` rỗng → fallback `"Chưa xác định"`.

### 2. `TelegramNotifier` (file mới)

**Path:** `app/infrastructure/notifications/telegram_notifier.py`

- Implement `INotificationPort`
- Dùng `httpx.AsyncClient` để gọi Telegram Bot API (`sendMessage`)
- Dùng `parse_mode=HTML` để format message
- Lỗi gửi message được log warning, không raise exception (không làm gián đoạn business flow)

### 3. `ConsoleNotifier`

Thêm implement cho 2 method mới (`notify_confirmed`, `notify_rejected`) — log ra console như cũ.

### 4. `ReviewAndConfirmUseCase`

- Constructor nhận thêm `notification: Optional[INotificationPort] = None`
- `finalize_confirm`: gọi `notify_confirmed` sau khi job status = `CONFIRMED`, truyền `seller_name` và `invoice_number` từ `updated_items[0]`
- `reject`: gọi `notify_rejected` sau khi job status = `REJECTED`. Vì `reject()` hiện chỉ nhận `job_id`, cần query repo để lấy `items` trước khi gọi notify. Nếu không có items → fallback `"Chưa xác định"`.

### 5. `dependencies.py`

`get_review_confirm_uc` inject thêm `notification=get_notifier()`.

## Format tin nhắn (tiếng Việt)

**Hóa đơn mới:**
```
📄 Hóa đơn mới cần xem xét

📁 File: {filename}
🏢 Nhà cung cấp: {seller_name}
🔢 Số hóa đơn: {invoice_number}
🔗 Xem xét: {app_base_url}/review/{job_id}
```

**Đã xác nhận:**
```
✅ Hóa đơn đã được xác nhận

📁 File: {filename}
🏢 Nhà cung cấp: {seller_name}
🔢 Số hóa đơn: {invoice_number}
```

**Đã từ chối:**
```
❌ Hóa đơn đã bị từ chối

📁 File: {filename}
🏢 Nhà cung cấp: {seller_name}
🔢 Số hóa đơn: {invoice_number}
```

Nếu `seller_name` hoặc `invoice_number` không có → hiển thị `"Chưa xác định"`.

## Luồng dữ liệu

```
Email/Upload → ProcessInvoiceUseCase
  → status = PENDING_REVIEW
  → notify_new_invoice() → Telegram

Review UI → ReviewAndConfirmUseCase.finalize_confirm()
  → status = CONFIRMED
  → notify_confirmed() → Telegram

Review UI → ReviewAndConfirmUseCase.reject()
  → status = REJECTED
  → notify_rejected() → Telegram
```

## Cấu hình `.env`

```env
NOTIFICATION_TYPE=telegram
TELEGRAM_BOT_TOKEN=8427565961:AAES_y4B3SW_hatu4dKHS_Y1BSj4T_8D5Hs
TELEGRAM_CHAT_ID=-5268360021
APP_BASE_URL=http://localhost:8000
```

## Xử lý lỗi

- Lỗi gọi Telegram API: log `WARNING`, không raise — business flow không bị ảnh hưởng
- `seller_name`/`invoice_number` thiếu: fallback về `"Chưa xác định"`
- `httpx` timeout: 10 giây

## Dependencies

- `httpx` (đã có trong project qua `aiohttp` hoặc cần thêm) — kiểm tra khi implement

## Files cần thay đổi

| File | Thay đổi |
|------|----------|
| `app/domain/ports/notification_port.py` | Cập nhật `notify_new_invoice`, thêm `notify_confirmed`, `notify_rejected` |
| `app/infrastructure/notifications/telegram_notifier.py` | Tạo mới |
| `app/infrastructure/notifications/console_notifier.py` | Thêm 2 method mới |
| `app/application/use_cases/process_invoice.py` | Truyền `seller_name`, `invoice_number` vào `notify_new_invoice` |
| `app/application/use_cases/review_and_confirm.py` | Inject notifier, gọi notify confirmed/rejected |
| `app/core/dependencies.py` | Inject notifier vào `get_review_confirm_uc` |
| `.env` | Thêm Telegram config |
