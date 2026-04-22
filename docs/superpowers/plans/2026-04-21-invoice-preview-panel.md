# Invoice Preview Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiển thị file hóa đơn gốc (XML pretty-printed + highlight / PDF native viewer) trong panel bên trái trang review, split 50/50 với form chỉnh sửa.

**Architecture:** Thêm endpoint `GET /jobs/{job_id}/preview` phục vụ file từ `data/pending/`. Review template đổi thành 2 cột Bootstrap — cột trái render preview theo file_type, cột phải giữ nguyên form hiện tại. JS fetch + DOMParser xử lý XML, `<iframe>` xử lý PDF.

**Tech Stack:** FastAPI `FileResponse`, Bootstrap 5 grid, highlight.js (CDN unpkg), vanilla JS DOMParser

---

## Files Changed

| File | Vai trò |
|---|---|
| `app/presentation/web/router.py` | Thêm route `GET /jobs/{job_id}/preview` |
| `app/presentation/web/templates/review.html` | Đổi layout split ngang, thêm preview panel + JS |
| `tests/presentation/test_web_router.py` | Test mới cho preview endpoint |
| `tests/presentation/__init__.py` | Init file cho package test mới |

---

## Task 1: Preview endpoint

**Files:**
- Modify: `app/presentation/web/router.py`
- Create: `tests/presentation/__init__.py`
- Create: `tests/presentation/test_web_router.py`

- [ ] **Step 1: Tạo test file cho web router**

```bash
mkdir -p tests/presentation
touch tests/presentation/__init__.py
```

- [ ] **Step 2: Viết failing test cho preview endpoint — XML**

Tạo file `tests/presentation/test_web_router.py`:

```python
import pytest
import tempfile
import os
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.dependencies import get_job_repo
from app.domain.entities.processing_job import ProcessingJob
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus


def make_xml_job(tmp_path: str) -> ProcessingJob:
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    job.status = InvoiceStatus.AWAITING_REVIEW
    xml_file = os.path.join(tmp_path, f"{job.id}.xml")
    with open(xml_file, "wb") as f:
        f.write(b"<HDon><TTChung>test</TTChung></HDon>")
    job.pending_file_path = xml_file
    return job


def make_pdf_job(tmp_path: str) -> ProcessingJob:
    job = ProcessingJob.create("hd001.pdf", FileType.PDF)
    job.status = InvoiceStatus.AWAITING_REVIEW
    pdf_file = os.path.join(tmp_path, f"{job.id}.pdf")
    with open(pdf_file, "wb") as f:
        f.write(b"%PDF-1.4 fake content")
    job.pending_file_path = pdf_file
    return job


def test_preview_xml_returns_200_with_xml_content_type():
    with tempfile.TemporaryDirectory() as tmp:
        job = make_xml_job(tmp)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = job
        app.dependency_overrides[get_job_repo] = lambda: mock_repo
        try:
            client = TestClient(app)
            resp = client.get(f"/jobs/{job.id}/preview")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]


def test_preview_pdf_returns_200_with_pdf_content_type():
    with tempfile.TemporaryDirectory() as tmp:
        job = make_pdf_job(tmp)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = job
        app.dependency_overrides[get_job_repo] = lambda: mock_repo
        try:
            client = TestClient(app)
            resp = client.get(f"/jobs/{job.id}/preview")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert "pdf" in resp.headers["content-type"]


def test_preview_returns_404_when_job_not_found():
    mock_repo = AsyncMock()
    mock_repo.get.return_value = None
    app.dependency_overrides[get_job_repo] = lambda: mock_repo
    try:
        client = TestClient(app)
        resp = client.get("/jobs/nonexistent-id/preview")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


def test_preview_returns_404_when_file_missing():
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    job.pending_file_path = "/tmp/nonexistent-file-xyz.xml"
    mock_repo = AsyncMock()
    mock_repo.get.return_value = job
    app.dependency_overrides[get_job_repo] = lambda: mock_repo
    try:
        client = TestClient(app)
        resp = client.get(f"/jobs/{job.id}/preview")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
```

- [ ] **Step 3: Chạy test để xác nhận FAIL**

```bash
cd /Users/quangdung/Documents/collect_invoice
poetry run pytest tests/presentation/test_web_router.py -v
```

Expected: `FAILED` với `404` hoặc route not found.

- [ ] **Step 4: Thêm route preview vào router.py**

Mở `app/presentation/web/router.py`, thêm import và route mới:

Thêm vào phần imports (dòng 1-2):
```python
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
```

Thêm route sau `review_page` (sau dòng 48):
```python
@router.get("/jobs/{job_id}/preview")
async def preview_file(job_id: str, repo=Depends(get_job_repo)):
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    path = job.pending_file_path
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="File không còn khả dụng")
    content_type = "application/xml" if job.file_type.value == "XML" else "application/pdf"
    return FileResponse(path, media_type=content_type)
```

- [ ] **Step 5: Chạy test để xác nhận PASS**

```bash
poetry run pytest tests/presentation/test_web_router.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/presentation/web/router.py tests/presentation/__init__.py tests/presentation/test_web_router.py
git commit -m "feat: add GET /jobs/{job_id}/preview endpoint"
```

---

## Task 2: Split layout và preview panel trong review.html

**Files:**
- Modify: `app/presentation/web/templates/review.html`

- [ ] **Step 1: Thay toàn bộ nội dung review.html**

Thay nội dung file `app/presentation/web/templates/review.html` bằng:

```html
{% extends "base.html" %}
{% block title %}Review Hóa Đơn — {{ job.filename }}{% endblock %}
{% block content %}
<div class="row g-0" style="min-height: 100vh;">

  {# ── Cột trái: preview file ── #}
  <div class="col-md-6 border-end" style="position: sticky; top: 0; height: 100vh; overflow: auto;">
    <div class="p-2 bg-light border-bottom d-flex align-items-center gap-2">
      <span class="fw-semibold small">{{ job.filename }}</span>
      <span class="badge bg-secondary">{{ job.file_type }}</span>
    </div>

    {% if job.file_type.value == "PDF" %}
      <iframe src="/jobs/{{ job.id }}/preview"
              style="width:100%; height:calc(100vh - 44px); border:none;">
        <p class="p-3 text-muted">Trình duyệt không hỗ trợ xem PDF trực tiếp.</p>
      </iframe>

    {% else %}
      {# XML: fetch + pretty-print + highlight #}
      <link rel="stylesheet"
            href="https://unpkg.com/highlight.js@11.9.0/styles/github.min.css">
      <script src="https://unpkg.com/highlight.js@11.9.0/lib/core.min.js"></script>
      <script src="https://unpkg.com/highlight.js@11.9.0/lib/languages/xml.min.js"></script>

      <div id="xml-loading" class="p-4 text-muted small">Đang tải file...</div>
      <pre id="xml-pre" style="display:none; height:calc(100vh - 44px); overflow:auto; margin:0; font-size:12px;">
        <code class="language-xml" id="xml-code"></code>
      </pre>
      <div id="xml-error" style="display:none;" class="p-4 text-danger small">Không thể tải file.</div>

      <script>
        (function () {
          function indentXml(xml) {
            const INDENT = '  ';
            let result = '';
            let depth = 0;
            // Normalize: remove existing whitespace-only text nodes between tags
            const tokens = xml.replace(/>\s*</g, '><').split(/(<[^>]+>)/);
            for (const token of tokens) {
              if (!token.trim()) continue;
              if (/^<\//.test(token)) {          // closing tag
                depth--;
                result += INDENT.repeat(Math.max(depth, 0)) + token + '\n';
              } else if (/\/>$/.test(token)) {   // self-closing tag
                result += INDENT.repeat(depth) + token + '\n';
              } else if (/^<[^?!]/.test(token)) { // opening tag
                result += INDENT.repeat(depth) + token + '\n';
                depth++;
              } else {                            // text node or declaration
                result += INDENT.repeat(depth) + token + '\n';
              }
            }
            return result;
          }

          fetch('/jobs/{{ job.id }}/preview')
            .then(function (r) {
              if (!r.ok) throw new Error('HTTP ' + r.status);
              return r.text();
            })
            .then(function (text) {
              const pretty = indentXml(text);
              const codeEl = document.getElementById('xml-code');
              codeEl.textContent = pretty;
              hljs.highlightElement(codeEl);
              document.getElementById('xml-loading').style.display = 'none';
              document.getElementById('xml-pre').style.display = 'block';
            })
            .catch(function () {
              document.getElementById('xml-loading').style.display = 'none';
              document.getElementById('xml-error').style.display = 'block';
            });
        })();
      </script>
    {% endif %}
  </div>

  {# ── Cột phải: form review ── #}
  <div class="col-md-6" style="height: 100vh; overflow: auto;">
    <div class="p-3">
      <h5 class="mb-3">Review: {{ job.filename }}</h5>
      <form action="/jobs/{{ job.id }}/confirm" method="post">
        {% for item in job.extracted_items %}
        <div class="card mb-3">
          <div class="card-header">Dòng {{ loop.index }}</div>
          <div class="card-body">
            <div class="row g-2">
              {% set fields = [
              ("invoice_symbol", "Ký hiệu HĐ"), ("invoice_number", "Số HĐ"),
              ("invoice_date", "Ngày phát hành"), ("seller_name", "Tên người bán"),
              ("seller_tax_code", "Mã số thuế"), ("description", "Mặt hàng"),
              ("price_before_tax", "Doanh số chưa thuế"), ("tax_rate", "Thuế suất"),
              ("price_after_tax", "Thuế GTGT")
              ] %}
              {% for fname, label in fields %}
              <div class="col-md-6">
                <label class="form-label small mb-1">{{ label }}</label>
                <input class="form-control form-control-sm" type="text"
                       name="{{ fname }}_{{ item.id }}"
                       value="{{ item[fname] if fname != 'invoice_date' else item.invoice_date.isoformat() }}">
              </div>
              {% endfor %}
            </div>
          </div>
        </div>
        {% endfor %}
        <div class="d-flex gap-2 mt-3 pb-4">
          <button type="submit" class="btn btn-success btn-sm">Xác nhận & Lưu vào XLS</button>
          <a href="/jobs/{{ job.id }}/reject" class="btn btn-danger btn-sm"
             onclick="return confirm('Từ chối hóa đơn này?')">Từ chối</a>
          <a href="/jobs" class="btn btn-secondary btn-sm">Quay lại</a>
        </div>
      </form>
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Kiểm tra template không lỗi cú pháp Jinja2**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('app/presentation/web/templates'))
env.get_template('review.html')
print('Template OK')
"
```

Expected: `Template OK`

- [ ] **Step 3: Chạy toàn bộ test suite để đảm bảo không regression**

```bash
poetry run pytest --tb=short -q
```

Expected: tất cả test PASS (bao gồm 4 test mới từ Task 1).

- [ ] **Step 4: Commit**

```bash
git add app/presentation/web/templates/review.html
git commit -m "feat: split-panel review page with XML/PDF preview"
```

---

## Task 3: Kiểm tra thủ công trên trình duyệt

- [ ] **Step 1: Khởi động server**

```bash
poetry run uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Upload một file XML và một file PDF**

Truy cập `http://localhost:8000`, upload file hóa đơn XML. Sau khi xử lý xong, click "Review".

- [ ] **Step 3: Xác nhận layout split hoạt động đúng**

Checklist:
- [ ] Panel trái hiển thị XML pretty-printed có syntax highlight (màu sắc rõ ràng)
- [ ] Panel trái hiển thị PDF qua native browser viewer (có thanh scroll, zoom)
- [ ] Panel phải giữ nguyên form với đầy đủ các trường
- [ ] Hai panel scroll độc lập — cuộn form không cuộn preview
- [ ] Nút "Xác nhận", "Từ chối", "Quay lại" hoạt động bình thường
- [ ] Thông báo "Đang tải file..." hiện trong khi XML đang fetch

- [ ] **Step 4: Kiểm tra edge case file không tồn tại**

Xóa tay một file pending rồi reload trang review:
```bash
rm data/pending/<job_id>.xml
```
Expected: panel trái hiện "Không thể tải file." (không crash trang).
