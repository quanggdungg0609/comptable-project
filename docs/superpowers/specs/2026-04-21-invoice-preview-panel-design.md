# Invoice Preview Panel — Design Spec

**Date:** 2026-04-21  
**Feature:** Hiển thị file hóa đơn (XML/PDF) bên cạnh form review để tiện đối chiếu

---

## Overview

Trang review (`/jobs/{job_id}/review`) hiện chỉ hiển thị form chỉnh sửa các trường đã trích xuất. Feature này thêm một panel bên trái hiển thị file gốc (XML pretty-printed có syntax highlighting, hoặc PDF native browser viewer) để reviewer có thể đối chiếu trực tiếp mà không cần mở file riêng.

---

## Architecture

### Backend — 1 route mới

**`GET /jobs/{job_id}/preview`** trong `app/presentation/web/router.py`

- Đọc `job.pending_file_path` từ DB qua `repo.get(job_id)`
- Nếu job không tồn tại → HTTP 404
- Nếu `pending_file_path` là None hoặc file không tồn tại trên disk → HTTP 404 với message "File không còn khả dụng"
- Đọc file và trả về `FileResponse` với Content-Type phù hợp:
  - XML → `application/xml`
  - PDF → `application/pdf`

### Frontend — Split layout

`app/presentation/web/templates/review.html` đổi layout thành 2 cột Bootstrap:

```
┌──────────────────────┬──────────────────────┐
│   Preview Panel      │   Form Edit          │
│   (col-md-6)         │   (col-md-6)         │
│                      │                      │
│  [iframe: PDF]       │  [form hiện tại]     │
│  hoặc                │                      │
│  [pre: XML]          │                      │
│                      │                      │
└──────────────────────┴──────────────────────┘
```

- Preview panel: `position: sticky; top: 0; height: 100vh; overflow: auto`
- Form panel: scroll độc lập, giữ nguyên nội dung hiện tại

---

## Component Details

### PDF Preview

```html
<iframe src="/jobs/{{ job.id }}/preview"
        style="width:100%; height:100vh; border:none;">
</iframe>
```

Dùng native PDF viewer của browser — không cần thư viện.

### XML Preview

```html
<pre style="height:100vh; overflow:auto; margin:0;">
  <code class="language-xml" id="xml-preview"></code>
</pre>
```

JS flow (inline script trong review.html):
1. `fetch("/jobs/{{ job.id }}/preview")` → `response.text()`
2. `new DOMParser().parseFromString(text, "text/xml")` → parse XML
3. Custom indent function → pretty-print string với 2-space indent
4. Set `element.innerText = prettyXml`
5. `hljs.highlightElement(element)` → syntax highlight

highlight.js load từ CDN (unpkg.com) — chỉ thêm vào `review.html`, không ảnh hưởng các trang khác.

---

## Error States

| Tình huống | Hiển thị |
|---|---|
| Job đang PROCESSING | Panel hiện "Đang xử lý, file chưa sẵn sàng" |
| File đã bị xóa (post-confirm) | Panel hiện "File không còn khả dụng" (lấy từ 404 response) |
| Lỗi fetch | Panel hiện "Không thể tải file" |

Với PDF: `<iframe>` không có sự kiện lỗi dễ dùng → dùng fallback `<p>` bên trong iframe.
Với XML: dùng `.catch()` trong fetch chain để hiện error message.

---

## Files Changed

| File | Thay đổi |
|---|---|
| `app/presentation/web/router.py` | Thêm route `GET /jobs/{job_id}/preview` |
| `app/presentation/web/templates/review.html` | Đổi layout split ngang, thêm preview panel + JS cho XML |

Không cần thay đổi domain, use cases, hay infrastructure.

---

## Dependencies

- **highlight.js** — load từ CDN, không cài package
- **Bootstrap** — đã có sẵn trong `base.html`
- **FileResponse** — đã có trong FastAPI (không cần import mới)
