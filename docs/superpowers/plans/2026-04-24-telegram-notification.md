# Telegram Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gửi thông báo Telegram tới nhóm kế toán khi hóa đơn mới cần review, khi xác nhận, và khi từ chối.

**Architecture:** Mở rộng `INotificationPort` với 3 method đầy đủ thông tin. Tạo `TelegramNotifier` implement port dùng `httpx`. Inject notifier vào `ReviewAndConfirmUseCase` để gửi notify tại confirm/reject. Update `ProcessInvoiceUseCase` để truyền `seller_name` và `invoice_number` khi notify.

**Tech Stack:** Python 3.12, `httpx` (đã có), `pytest-asyncio`, `unittest.mock.AsyncMock`

---

## File Map

| File | Action | Mô tả |
|------|--------|-------|
| `app/domain/ports/notification_port.py` | Modify | Thêm `notify_confirmed`, `notify_rejected`; cập nhật signature `notify_new_invoice` |
| `app/infrastructure/notifications/telegram_notifier.py` | Create | TelegramNotifier implement INotificationPort |
| `app/infrastructure/notifications/console_notifier.py` | Modify | Thêm implement 2 method mới |
| `app/application/use_cases/process_invoice.py` | Modify | Truyền `seller_name`, `invoice_number` vào `notify_new_invoice` |
| `app/application/use_cases/review_and_confirm.py` | Modify | Inject notifier, gọi notify tại confirm/reject |
| `app/core/dependencies.py` | Modify | Inject notifier vào `get_review_confirm_uc` |
| `tests/infrastructure/test_telegram_notifier.py` | Create | Unit tests cho TelegramNotifier |
| `tests/application/test_process_invoice.py` | Modify | Cập nhật assert cho signature mới |
| `tests/application/test_review_and_confirm.py` | Modify | Thêm tests notify confirmed/rejected |

---

## Task 1: Mở rộng `INotificationPort`

**Files:**
- Modify: `app/domain/ports/notification_port.py`

- [ ] **Step 1: Viết test verify interface có đủ 3 method**

```python
# tests/domain/test_notification_port.py
from app.domain.ports.notification_port import INotificationPort
import inspect

def test_notification_port_has_required_methods():
    methods = {name for name, _ in inspect.getmembers(INotificationPort, predicate=inspect.isfunction)}
    assert "notify_new_invoice" in methods
    assert "notify_confirmed" in methods
    assert "notify_rejected" in methods

def test_notify_new_invoice_signature():
    sig = inspect.signature(INotificationPort.notify_new_invoice)
    params = list(sig.parameters.keys())
    assert params == ["self", "job_id", "filename", "seller_name", "invoice_number"]

def test_notify_confirmed_signature():
    sig = inspect.signature(INotificationPort.notify_confirmed)
    params = list(sig.parameters.keys())
    assert params == ["self", "job_id", "filename", "seller_name", "invoice_number"]

def test_notify_rejected_signature():
    sig = inspect.signature(INotificationPort.notify_rejected)
    params = list(sig.parameters.keys())
    assert params == ["self", "job_id", "filename", "seller_name", "invoice_number"]
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/domain/test_notification_port.py -v
```
Expected: FAIL — `notify_confirmed` và `notify_rejected` không tồn tại, `notify_new_invoice` thiếu params.

- [ ] **Step 3: Cập nhật `INotificationPort`**

Thay toàn bộ nội dung `app/domain/ports/notification_port.py`:

```python
from abc import ABC, abstractmethod


class INotificationPort(ABC):
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

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
pytest tests/domain/test_notification_port.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/domain/ports/notification_port.py tests/domain/test_notification_port.py
git commit -m "feat: extend INotificationPort with confirm/reject methods and full invoice info"
```

---

## Task 2: Cập nhật `ConsoleNotifier`

**Files:**
- Modify: `app/infrastructure/notifications/console_notifier.py`

- [ ] **Step 1: Viết test cho ConsoleNotifier**

```python
# tests/infrastructure/test_console_notifier.py
import pytest
from app.infrastructure.notifications.console_notifier import ConsoleNotifier

@pytest.mark.asyncio
async def test_notify_new_invoice_logs(caplog):
    import logging
    notifier = ConsoleNotifier()
    with caplog.at_level(logging.INFO):
        await notifier.notify_new_invoice("job-1", "hd001.xml", "Cty ABC", "0001")
    assert "hd001.xml" in caplog.text

@pytest.mark.asyncio
async def test_notify_confirmed_logs(caplog):
    import logging
    notifier = ConsoleNotifier()
    with caplog.at_level(logging.INFO):
        await notifier.notify_confirmed("job-1", "hd001.xml", "Cty ABC", "0001")
    assert "hd001.xml" in caplog.text

@pytest.mark.asyncio
async def test_notify_rejected_logs(caplog):
    import logging
    notifier = ConsoleNotifier()
    with caplog.at_level(logging.INFO):
        await notifier.notify_rejected("job-1", "hd001.xml", "Cty ABC", "0001")
    assert "hd001.xml" in caplog.text
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/infrastructure/test_console_notifier.py -v
```
Expected: FAIL — `notify_confirmed`, `notify_rejected` chưa có, `notify_new_invoice` sai signature.

- [ ] **Step 3: Cập nhật `ConsoleNotifier`**

Thay toàn bộ nội dung `app/infrastructure/notifications/console_notifier.py`:

```python
import logging

logger = logging.getLogger(__name__)


class ConsoleNotifier:
    async def notify_new_invoice(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        logger.info("[Notification] Hóa đơn mới cần xem xét: %s (NCC: %s, Số: %s, job: %s)", filename, seller_name, invoice_number, job_id)

    async def notify_confirmed(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        logger.info("[Notification] Hóa đơn đã xác nhận: %s (NCC: %s, Số: %s, job: %s)", filename, seller_name, invoice_number, job_id)

    async def notify_rejected(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        logger.info("[Notification] Hóa đơn đã từ chối: %s (NCC: %s, Số: %s, job: %s)", filename, seller_name, invoice_number, job_id)
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
pytest tests/infrastructure/test_console_notifier.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/notifications/console_notifier.py tests/infrastructure/test_console_notifier.py
git commit -m "feat: update ConsoleNotifier to implement extended INotificationPort"
```

---

## Task 3: Tạo `TelegramNotifier`

**Files:**
- Create: `app/infrastructure/notifications/telegram_notifier.py`
- Create: `tests/infrastructure/test_telegram_notifier.py`

- [ ] **Step 1: Viết tests cho TelegramNotifier**

```python
# tests/infrastructure/test_telegram_notifier.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.notifications.telegram_notifier import TelegramNotifier


@pytest.fixture
def notifier():
    return TelegramNotifier(
        bot_token="test-token",
        chat_id="-123456",
        app_base_url="http://localhost:8000",
    )


@pytest.mark.asyncio
async def test_notify_new_invoice_calls_telegram_api(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_new_invoice("job-1", "hd001.xml", "Cty ABC", "0001")

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "sendMessage" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert payload["chat_id"] == "-123456"
        assert "hd001.xml" in payload["text"]
        assert "Cty ABC" in payload["text"]
        assert "0001" in payload["text"]
        assert "http://localhost:8000/review/job-1" in payload["text"]


@pytest.mark.asyncio
async def test_notify_confirmed_calls_telegram_api(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_confirmed("job-1", "hd001.xml", "Cty ABC", "0001")

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert "xác nhận" in payload["text"]
        assert "hd001.xml" in payload["text"]


@pytest.mark.asyncio
async def test_notify_rejected_calls_telegram_api(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_rejected("job-1", "hd001.xml", "Cty ABC", "0001")

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args[1]["json"]
        assert "từ chối" in payload["text"]


@pytest.mark.asyncio
async def test_telegram_api_error_does_not_raise(notifier):
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        # Không được raise exception
        await notifier.notify_new_invoice("job-1", "hd001.xml", "Cty ABC", "0001")


@pytest.mark.asyncio
async def test_missing_seller_info_shows_fallback(notifier):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        await notifier.notify_new_invoice("job-1", "hd001.xml", "", "")

        payload = mock_client.post.call_args[1]["json"]
        assert "Chưa xác định" in payload["text"]
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/infrastructure/test_telegram_notifier.py -v
```
Expected: FAIL — module chưa tồn tại.

- [ ] **Step 3: Tạo `TelegramNotifier`**

```python
# app/infrastructure/notifications/telegram_notifier.py
import logging
import httpx
from app.domain.ports.notification_port import INotificationPort

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier(INotificationPort):
    def __init__(self, bot_token: str, chat_id: str, app_base_url: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._app_base_url = app_base_url.rstrip("/")

    async def notify_new_invoice(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        seller = seller_name or "Chưa xác định"
        number = invoice_number or "Chưa xác định"
        text = (
            "📄 <b>Hóa đơn mới cần xem xét</b>\n\n"
            f"📁 File: {filename}\n"
            f"🏢 Nhà cung cấp: {seller}\n"
            f"🔢 Số hóa đơn: {number}\n"
            f"🔗 Xem xét: {self._app_base_url}/review/{job_id}"
        )
        await self._send(text)

    async def notify_confirmed(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        seller = seller_name or "Chưa xác định"
        number = invoice_number or "Chưa xác định"
        text = (
            "✅ <b>Hóa đơn đã được xác nhận</b>\n\n"
            f"📁 File: {filename}\n"
            f"🏢 Nhà cung cấp: {seller}\n"
            f"🔢 Số hóa đơn: {number}"
        )
        await self._send(text)

    async def notify_rejected(self, job_id: str, filename: str, seller_name: str, invoice_number: str) -> None:
        seller = seller_name or "Chưa xác định"
        number = invoice_number or "Chưa xác định"
        text = (
            "❌ <b>Hóa đơn đã bị từ chối</b>\n\n"
            f"📁 File: {filename}\n"
            f"🏢 Nhà cung cấp: {seller}\n"
            f"🔢 Số hóa đơn: {number}"
        )
        await self._send(text)

    async def _send(self, text: str) -> None:
        url = _TELEGRAM_API.format(token=self._bot_token)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                })
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("[TelegramNotifier] Gửi thông báo thất bại: %s", exc)
```

- [ ] **Step 4: Chạy test để xác nhận PASS**

```bash
pytest tests/infrastructure/test_telegram_notifier.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/notifications/telegram_notifier.py tests/infrastructure/test_telegram_notifier.py
git commit -m "feat: add TelegramNotifier implementing INotificationPort"
```

---

## Task 4: Cập nhật `ProcessInvoiceUseCase`

**Files:**
- Modify: `app/application/use_cases/process_invoice.py`
- Modify: `tests/application/test_process_invoice.py`

- [ ] **Step 1: Cập nhật test hiện có cho signature mới**

Trong `tests/application/test_process_invoice.py`, tìm dòng:
```python
notification.notify_new_invoice.assert_called_once_with(job.id, "hd049.xml")
```
Thay bằng:
```python
notification.notify_new_invoice.assert_called_once_with(
    job.id, "hd049.xml", "Cty XYZ", "49"
)
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/application/test_process_invoice.py::test_xml_file_creates_job_awaiting_review -v
```
Expected: FAIL — assert_called_once_with sai arguments.

- [ ] **Step 3: Cập nhật call site trong `process_invoice.py`**

Tìm đoạn (khoảng dòng 117–120):
```python
            if self._notification:
                try:
                    logger.debug(f"[ProcessInvoice] Sending notification for job {job.id}")
                    await self._notification.notify_new_invoice(job.id, filename)
```

Thay bằng:
```python
            if self._notification:
                try:
                    logger.debug(f"[ProcessInvoice] Sending notification for job {job.id}")
                    first = items[0] if items else None
                    seller_name = first.seller_name if first else ""
                    invoice_number = first.invoice_number if first else ""
                    await self._notification.notify_new_invoice(job.id, filename, seller_name, invoice_number)
```

- [ ] **Step 4: Chạy toàn bộ test process_invoice để xác nhận PASS**

```bash
pytest tests/application/test_process_invoice.py -v
```
Expected: PASS (tất cả tests)

- [ ] **Step 5: Commit**

```bash
git add app/application/use_cases/process_invoice.py tests/application/test_process_invoice.py
git commit -m "feat: pass seller_name and invoice_number to notify_new_invoice"
```

---

## Task 5: Inject notifier vào `ReviewAndConfirmUseCase`

**Files:**
- Modify: `app/application/use_cases/review_and_confirm.py`
- Modify: `tests/application/test_review_and_confirm.py`

- [ ] **Step 1: Viết tests mới cho notify confirmed/rejected**

Thêm vào cuối `tests/application/test_review_and_confirm.py`:

```python
@pytest.mark.asyncio
async def test_finalize_confirm_sends_notification(tmp_path):
    repo = AsyncMock()
    storage = AsyncMock()
    excel = AsyncMock()
    excel_detail = AsyncMock()
    notification = AsyncMock()
    excel.append_rows.return_value = ("Bang_ke_thue_2026_03.xlsx", b"xlsx_bytes")
    excel_detail.append_rows.return_value = ("Chi_tiet_hoa_don_T3_2026.xlsx", b"detail_bytes")
    storage.download_file.return_value = b""
    job = make_job_with_items()
    pending = tmp_path / f"{job.id}.xml"
    pending.write_bytes(b"<HDon/>")
    job.pending_file_path = str(pending)
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices="invoices", bucket_exports="exports",
        notification=notification,
    )
    await uc.finalize_confirm(
        job_id=job.id,
        updated_items=job.extracted_items,
        updated_line_items=[],
    )

    notification.notify_confirmed.assert_called_once_with(
        job.id, job.filename, "Cty XYZ", "49"
    )


@pytest.mark.asyncio
async def test_reject_sends_notification():
    repo = AsyncMock()
    notification = AsyncMock()
    job = make_job_with_items()
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(
        repo=repo, storage=AsyncMock(), excel=AsyncMock(), excel_detail=AsyncMock(),
        bucket_invoices="i", bucket_exports="e",
        notification=notification,
    )
    await uc.reject(job_id=job.id)

    notification.notify_rejected.assert_called_once_with(
        job.id, job.filename, "Cty XYZ", "49"
    )


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_confirm(tmp_path):
    repo = AsyncMock()
    storage = AsyncMock()
    excel = AsyncMock()
    excel_detail = AsyncMock()
    notification = AsyncMock()
    notification.notify_confirmed.side_effect = Exception("Telegram down")
    excel.append_rows.return_value = ("f.xlsx", b"bytes")
    excel_detail.append_rows.return_value = ("f.xlsx", b"bytes")
    storage.download_file.return_value = b""
    job = make_job_with_items()
    pending = tmp_path / f"{job.id}.xml"
    pending.write_bytes(b"<HDon/>")
    job.pending_file_path = str(pending)
    repo.get.return_value = job

    uc = ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices="invoices", bucket_exports="exports",
        notification=notification,
    )
    await uc.finalize_confirm(
        job_id=job.id,
        updated_items=job.extracted_items,
        updated_line_items=[],
    )

    # Job vẫn CONFIRMED dù notification lỗi
    repo.update_status.assert_called_with(job.id, InvoiceStatus.CONFIRMED)
```

- [ ] **Step 2: Chạy tests mới để xác nhận FAIL**

```bash
pytest tests/application/test_review_and_confirm.py::test_finalize_confirm_sends_notification tests/application/test_review_and_confirm.py::test_reject_sends_notification -v
```
Expected: FAIL — `ReviewAndConfirmUseCase` chưa nhận `notification`.

- [ ] **Step 3: Cập nhật `ReviewAndConfirmUseCase`**

Trong `app/application/use_cases/review_and_confirm.py`:

Thêm import ở đầu file:
```python
from typing import Optional
from app.domain.ports.notification_port import INotificationPort
```

Thêm `notification` vào `__init__`:
```python
    def __init__(
        self,
        repo: IJobRepository,
        storage: IStoragePort,
        excel: IExcelPort,
        excel_detail: IExcelDetailPort,
        bucket_invoices: str,
        bucket_exports: str,
        notification: Optional[INotificationPort] = None,
    ):
        self._repo = repo
        self._storage = storage
        self._excel = excel
        self._excel_detail = excel_detail
        self._bucket_invoices = bucket_invoices
        self._bucket_exports = bucket_exports
        self._notification = notification
```

Trong `finalize_confirm`, thêm đoạn sau `await self._repo.update_status(job_id, InvoiceStatus.CONFIRMED)`:
```python
            if self._notification:
                try:
                    first = updated_items[0] if updated_items else None
                    seller_name = first.seller_name if first else ""
                    invoice_number = first.invoice_number if first else ""
                    await self._notification.notify_confirmed(job_id, job.filename, seller_name, invoice_number)
                except Exception as notify_exc:
                    logger.warning(f"[ReviewAndConfirm] Notification failed for job {job_id}: {notify_exc}")
```

Trong `reject`, thay nội dung hiện tại:
```python
    async def reject(self, job_id: str) -> ProcessingJob:
        logger.info(f"[ReviewAndConfirm] Rejecting job {job_id}")
        job = await self._repo.get(job_id)
        await self._repo.update_status(job_id, InvoiceStatus.REJECTED)
        job.status = InvoiceStatus.REJECTED
        logger.info(f"[ReviewAndConfirm] Job {job_id} marked as REJECTED")
        if self._notification:
            try:
                first = job.extracted_items[0] if job.extracted_items else None
                seller_name = first.seller_name if first else ""
                invoice_number = first.invoice_number if first else ""
                await self._notification.notify_rejected(job_id, job.filename, seller_name, invoice_number)
            except Exception as notify_exc:
                logger.warning(f"[ReviewAndConfirm] Notification failed for job {job_id}: {notify_exc}")
        return job
```

- [ ] **Step 4: Chạy toàn bộ test review_and_confirm để xác nhận PASS**

```bash
pytest tests/application/test_review_and_confirm.py -v
```
Expected: PASS (tất cả tests)

- [ ] **Step 5: Commit**

```bash
git add app/application/use_cases/review_and_confirm.py tests/application/test_review_and_confirm.py
git commit -m "feat: inject INotificationPort into ReviewAndConfirmUseCase for confirm/reject events"
```

---

## Task 6: Wiring — inject notifier vào dependencies và cấu hình `.env`

**Files:**
- Modify: `app/core/dependencies.py`
- Modify: `.env` (hoặc tạo mới nếu chưa có)

- [ ] **Step 1: Cập nhật `get_review_confirm_uc` trong `dependencies.py`**

Tìm function `get_review_confirm_uc`:
```python
def get_review_confirm_uc(
    repo=Depends(get_job_repo),
    storage=Depends(get_storage),
    excel=Depends(get_excel),
    excel_detail=Depends(get_excel_detail),
    settings: Settings = Depends(get_settings),
) -> ReviewAndConfirmUseCase:
    return ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices=settings.rustfs_bucket_invoices,
        bucket_exports=settings.rustfs_bucket_exports,
    )
```

Thay bằng:
```python
def get_review_confirm_uc(
    repo=Depends(get_job_repo),
    storage=Depends(get_storage),
    excel=Depends(get_excel),
    excel_detail=Depends(get_excel_detail),
    settings: Settings = Depends(get_settings),
) -> ReviewAndConfirmUseCase:
    return ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices=settings.rustfs_bucket_invoices,
        bucket_exports=settings.rustfs_bucket_exports,
        notification=get_notifier(),
    )
```

- [ ] **Step 2: Thêm config Telegram vào `.env`**

Thêm vào file `.env` (tạo mới nếu chưa có):
```env
NOTIFICATION_TYPE=telegram
TELEGRAM_BOT_TOKEN=8427565961:AAES_y4B3SW_hatu4dKHS_Y1BSj4T_8D5Hs
TELEGRAM_CHAT_ID=-5268360021
APP_BASE_URL=http://localhost:8000
```

> **Lưu ý:** `APP_BASE_URL` cần được cập nhật thành URL thực của server khi deploy production.

- [ ] **Step 3: Chạy toàn bộ test suite**

```bash
pytest --tb=short -q
```
Expected: tất cả PASS, không có regression.

- [ ] **Step 4: Commit**

```bash
git add app/core/dependencies.py
git commit -m "feat: wire TelegramNotifier into ReviewAndConfirmUseCase via dependency injection"
```

---

## Task 7: Kiểm tra thủ công end-to-end

- [ ] **Step 1: Khởi động ứng dụng**

```bash
docker compose up -d
```
Hoặc nếu chạy local:
```bash
poetry run uvicorn app.main:app --reload
```

- [ ] **Step 2: Upload một hóa đơn test**

Dùng UI hoặc curl để upload file hóa đơn. Kiểm tra nhóm Telegram **Phòng Kế Toán** — phải nhận được tin nhắn "📄 Hóa đơn mới cần xem xét".

- [ ] **Step 3: Confirm hóa đơn qua UI**

Vào trang review, xác nhận hóa đơn. Kiểm tra nhóm Telegram — phải nhận được tin nhắn "✅ Hóa đơn đã được xác nhận".

- [ ] **Step 4: Reject một hóa đơn khác qua UI**

Upload thêm một hóa đơn, từ chối nó. Kiểm tra nhóm Telegram — phải nhận được tin nhắn "❌ Hóa đơn đã bị từ chối".
