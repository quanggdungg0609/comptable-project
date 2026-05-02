# Hướng dẫn sử dụng: Excel-CR (Tổng hợp chi phí)

**Ngày:** 2026-05-01

---

## 1. Excel-CR làm gì?

Tổng hợp các dòng chi phí từ file báo cáo nguồn (CSV/XLS/PDF) vào template Excel chuẩn, tự động map cột **Diễn giải** → **Chỉ tiêu kế toán** qua 3 tầng:

1. **llm_confirmed** — khớp chính xác diễn giải đã được xác nhận trước đó
2. **keyword** — khớp khoản mục + từ khóa trong diễn giải
3. **direct** — map trực tiếp khoản mục → chỉ tiêu

Những dòng không khớp → LLM gợi ý → người dùng xác nhận → lưu vào `rules.json` để dùng lại lần sau.

---

## 2. Luồng sử dụng

```
Upload file nguồn  →  Upload template  →  Aggregate & Match
       ↓
  Dòng khớp tự động (3 tầng)
  Dòng không khớp → LLM classify → Review & Confirm
       ↓
  Tải file Excel kết quả
```

**Trạng thái session:**

| Trạng thái | Ý nghĩa |
|-----------|---------|
| `pending` | Mới tạo, chờ upload |
| `aggregated` | Đã tổng hợp & match xong |
| `reviewed` | Đã LLM classify xong, chờ xác nhận |
| `done` | Hoàn thành, sẵn sàng tải |

---

## 3. Sử dụng qua Web UI

Truy cập: `http://localhost:8000/excel-cr/`

### Bước 1 — Upload file

- **File nguồn**: file báo cáo chi phí (CSV, XLS, XLSX, PDF)
- **File template**: file Excel chuẩn có sẵn các cột chỉ tiêu

Nhấn **"Bắt đầu xử lý"** → hệ thống tự động upload, aggregate, LLM classify.

### Bước 2 — Review & Confirm

Bảng hiển thị các dòng **chưa khớp được tự động**, gồm:
- Diễn giải gốc
- Khoản mục
- Gợi ý của LLM + % confidence
- Dropdown chọn chỉ tiêu (hoặc bỏ qua)

Chọn chỉ tiêu đúng → nhấn **"Xác nhận và tải file"**.

> Mapping được xác nhận sẽ lưu vào `rules.json` → lần sau tự động khớp, không cần review lại.

### Bước 3 — Tải kết quả

Nhấn **"Tải file Excel"** → file Excel kết quả tải về.

---

## 4. API Reference

Tất cả endpoints mount dưới prefix `/excel-cr`.  
Xem interactive docs tại: `http://localhost:8000/docs#/excel-cr`

### Tổng quan

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/excel-cr/upload-source` | Upload file nguồn, tạo session mới |
| `POST` | `/excel-cr/upload-template/{session_id}` | Upload file template Excel |
| `GET`  | `/excel-cr/aggregate/{session_id}` | Tổng hợp & match tự động (3 tầng) |
| `POST` | `/excel-cr/llm-review/{session_id}` | LLM gợi ý cho dòng chưa khớp |
| `POST` | `/excel-cr/confirm/{session_id}` | Xác nhận mapping, lưu vào rules |
| `GET`  | `/excel-cr/download/{session_id}` | Tải file Excel kết quả |
| `GET`  | `/excel-cr/rules` | Xem toàn bộ rules hiện tại |
| `POST` | `/excel-cr/rules` | Ghi đè toàn bộ rules |

---

### `POST /excel-cr/upload-source`

Upload file nguồn (CSV / XLS / XLSX / PDF), tạo session mới.

```
POST /excel-cr/upload-source
Content-Type: multipart/form-data

file: <file nguồn>
```

**Response:**
```json
{"session_id": "abc-123", "status": "pending"}
```

**Lỗi:** `422` nếu file không đúng định dạng.

---

### `POST /excel-cr/upload-template/{session_id}`

Upload file template Excel (XLSX). Template phải có sẵn các cột chỉ tiêu kế toán.

```
POST /excel-cr/upload-template/abc-123
Content-Type: multipart/form-data

file: <template.xlsx>
```

**Response:**
```json
{"session_id": "abc-123", "template_key": "uploads/abc-123/template_report.xlsx"}
```

**Lỗi:** `404` nếu session không tồn tại.

---

### `GET /excel-cr/aggregate/{session_id}`

Tổng hợp dữ liệu từ file nguồn, match tự động qua 3 tầng rules. Phải upload cả source lẫn template trước.

```
GET /excel-cr/aggregate/abc-123
```

**Response:**
```json
{
  "session_id": "abc-123",
  "matched": 42,
  "unmatched": 5,
  "status": "aggregated"
}
```

**Lỗi:** `404` nếu session không tồn tại hoặc chưa upload template.

---

### `POST /excel-cr/llm-review/{session_id}`

Gọi LLM để gợi ý chỉ tiêu cho các dòng chưa khớp. Phải chạy aggregate trước.

```
POST /excel-cr/llm-review/abc-123
```

**Response:**
```json
{"session_id": "abc-123", "classified": 5}
```

> Nếu `classified: 0` → tất cả dòng đã khớp tự động, bỏ qua bước này.

**Lỗi:** `422` nếu chưa chạy aggregate.

---

### `POST /excel-cr/confirm/{session_id}`

Xác nhận mapping cho các dòng LLM gợi ý. Mapping được lưu vào `rules.json` (`llm_confirmed`) để dùng lại lần sau.

```
POST /excel-cr/confirm/abc-123
Content-Type: application/json

[
  {
    "dien_giai": "Mua văn phòng phẩm",
    "khoan_muc": "Chi phí văn phòng",
    "chi_tieu": "642"
  }
]
```

> Gửi `[]` (mảng rỗng) nếu không có gì cần confirm — session vẫn chuyển sang `done`.

**Response:**
```json
{"session_id": "abc-123", "confirmed": 3}
```

---

### `GET /excel-cr/download/{session_id}`

Tải file Excel kết quả. Session phải ở trạng thái `done`.

```
GET /excel-cr/download/abc-123
```

**Response:** file `excel_cr_output.xlsx` (stream).  
**Lỗi:** `422` nếu session chưa hoàn thành hoặc chưa có dữ liệu aggregate.

---

### `GET /excel-cr/rules`

Xem toàn bộ rules mapping hiện tại trên RustFS.

```
GET /excel-cr/rules
```

**Response:**
```json
{
  "llm_confirmed": [
    {"dien_giai": "Mua văn phòng phẩm", "chi_tieu": "642"}
  ],
  "keyword": [
    {"khoan_muc": "Chi phí văn phòng", "keywords": ["văn phòng", "in ấn"], "chi_tieu": "642"}
  ],
  "direct": {
    "Chi phí điện thoại": "641"
  }
}
```

---

### `POST /excel-cr/rules`

Ghi đè toàn bộ rules. Dùng để thêm/sửa rule `keyword` hoặc `direct` thủ công.

```
POST /excel-cr/rules
Content-Type: application/json

{
  "llm_confirmed": [...],
  "keyword": [...],
  "direct": {...}
}
```

**Response:**
```json
{"status": "saved"}
```

> **Cảnh báo:** Ghi đè toàn bộ — lấy `GET /rules` trước, sửa, rồi `POST` lại để không mất dữ liệu cũ.

---

## 5. rules.json — Bộ nhớ mapping

**Không tạo thủ công.** File tự động quản lý trên RustFS tại `config/rules.json`.

Hệ thống tự tạo mặc định khi chưa có:
```json
{
  "llm_confirmed": [],
  "keyword": [],
  "direct": []
}
```

### Cấu trúc

**`llm_confirmed`** — mapping đã xác nhận từ LLM review:
```json
[
  {"dien_giai": "Mua văn phòng phẩm", "chi_tieu": "642"}
]
```

**`keyword`** — khớp theo khoản mục + từ khóa trong diễn giải:
```json
[
  {
    "khoan_muc": "Chi phí văn phòng",
    "keywords": ["văn phòng", "in ấn", "photocopy"],
    "chi_tieu": "642"
  }
]
```

**`direct`** — map trực tiếp khoản mục (không cần xét diễn giải):
```json
{
  "Chi phí điện thoại": "641",
  "Chi phí đi lại": "642"
}
```

> Mỗi lần xác nhận mapping trong UI, `llm_confirmed` tự cập nhật. Không cần chỉnh `rules.json` thủ công trừ khi muốn thêm rule `keyword` hoặc `direct`.

---

## 6. Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|-----|-------------|-----------|
| `422 Unprocessable Entity` khi upload | File không đúng định dạng | Kiểm tra file là CSV/XLS/XLSX/PDF |
| `"Run aggregate first"` | Gọi LLM review trước aggregate | Gọi `/aggregate` trước `/llm-review` |
| `"No template uploaded"` | Chưa upload template | Gọi `/upload-template/{id}` trước `/aggregate` |
| LLM review trả về `classified: 0` | Tất cả đã khớp tự động | Bình thường — bỏ qua bước review |
| Session not found | `session_id` sai hoặc hết hạn | Tạo session mới |

---

## 7. Cấu trúc file Input → Output

### File nguồn (input)

Hệ thống đọc 4 cột bắt buộc. Tên cột dùng **partial match** (không phân biệt hoa thường):

| Tên cột trong file | Được nhận dạng bởi | Kiểu |
|--------------------|--------------------|------|
| `Tháng` / `Tháng 1` / `tháng` | chứa `"tháng"` | int |
| `Diễn giải` / `Diễn Giải` | chứa `"diễn giải"` | str |
| `Số tiền` / `Số Tiền (VNĐ)` | chứa `"số tiền"` | float |
| `Khoản mục` / `Khoản Mục` | chứa `"khoản mục"` | str |

**Ví dụ file nguồn hợp lệ:**

| Tháng | Khoản mục | Diễn giải | Số tiền |
|-------|-----------|-----------|---------|
| 1 | Chi phí văn phòng | Mua văn phòng phẩm | 500,000 |
| 1 | Chi phí văn phòng | In tài liệu | 200,000 |
| 2 | Chi phí điện thoại | Cước điện thoại tháng 2 | 1,200,000 |

> - Dòng có `Khoản mục` là số thuần (ví dụ: `"1"`, `"642"`) → tự động loại bỏ (dòng tổng/header).
> - `Số tiền` chấp nhận dấu phẩy phân cách nghìn (e.g. `1,500,000`).
> - PDF: chỉ đọc được PDF có bảng dạng text. PDF scan (ảnh) không được hỗ trợ.

---

### Bước tổng hợp (aggregate)

Sau khi parse, hệ thống **group by `(Tháng, Diễn giải, Khoản mục)` và SUM `Số tiền`**:

```
Tháng 1 | Chi phí VP | Mua văn phòng phẩm | 500,000 ┐
Tháng 1 | Chi phí VP | Mua văn phòng phẩm | 300,000 ┘→ gộp: 800,000
```

Sau gộp, mỗi dòng được gán `Chỉ tiêu` qua 3 tầng rules (xem Mục 1).

---

### File template (input)

File Excel chuẩn, phải có:

1. **Cột "Chỉ tiêu"** — hệ thống tìm cell đầu tiên chứa chữ `"chỉ tiêu"` (không phân biệt hoa thường) để xác định cột.
2. **Hàng header tháng** — cùng hàng với "Chỉ tiêu", các cột còn lại phải chứa số tháng (e.g. `"Tháng 1"`, `"T1"`, `"1"`).

**Ví dụ layout template:**

|   | A | B | C | ... |
|---|---|---|---|-----|
| 1 | **Chỉ tiêu** | **Tháng 1** | **Tháng 2** | ... |
| 2 | 641 - CP điện thoại | | | |
| 3 | 642 - CP văn phòng | | | |

---

### File output

Output = template gốc **giữ nguyên format**, chỉ điền số tiền vào các ô tương ứng.

**Logic điền:**
- Tìm hàng theo `Chỉ tiêu` (khớp chính xác tên ô trong cột chỉ tiêu)
- Tìm cột theo `Tháng` (quét header tìm số tháng)
- **Cộng dồn** vào giá trị hiện có trong ô (nếu ô đã có số → cộng thêm)

**Dòng bị bỏ qua (log warning):**
- Dòng không có `chi_tieu` (chưa được xác nhận)
- `chi_tieu` không tìm thấy trong template
- Tháng không tìm thấy trong template
