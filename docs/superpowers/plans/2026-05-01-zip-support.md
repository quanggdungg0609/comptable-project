# ZIP Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support ZIP file attachments in both email intake and manual upload, extracting contained PDF/XML files and processing them through the existing pipeline.

**Architecture:** New `ZipExtractor` utility extracts PDF/XML files from ZIP bytes at intake layer. Both `EmailListener` and the API upload route expand ZIP attachments before existing XML/PDF pairing logic — downstream code (`ProcessInvoice`, `FileType`, DB schema) unchanged.

**Tech Stack:** Python stdlib `zipfile`, FastAPI `UploadFile`, existing `ProcessInvoice` use case.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/infrastructure/parsers/zip_extractor.py` | **Create** | Extract PDF/XML from ZIP bytes |
| `tests/infrastructure/test_zip_extractor.py` | **Create** | Unit tests for ZipExtractor |
| `app/infrastructure/email/email_listener.py` | **Modify** | Expand ZIPs before XML/PDF split |
| `app/presentation/api/router.py` | **Modify** | Expand ZIPs before file_map loop |

---

### Task 1: ZipExtractor utility (TDD)

**Files:**
- Create: `app/infrastructure/parsers/zip_extractor.py`
- Test: `tests/infrastructure/test_zip_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/infrastructure/test_zip_extractor.py
import io
import zipfile
import pytest
from app.infrastructure.parsers.zip_extractor import extract_zip_contents


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_extracts_pdf_and_xml():
    data = _make_zip({"invoice.pdf": b"pdf", "invoice.xml": b"xml"})
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 2
    names = {r["filename"] for r in result}
    assert names == {"invoice.pdf", "invoice.xml"}


def test_skips_unsupported_types():
    data = _make_zip({"invoice.pdf": b"pdf", "readme.txt": b"txt", "data.csv": b"csv"})
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.pdf"


def test_skips_macosx_entries():
    data = _make_zip({
        "__MACOSX/._invoice.pdf": b"junk",
        "invoice.pdf": b"pdf",
    })
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.pdf"


def test_skips_hidden_files():
    data = _make_zip({".DS_Store": b"junk", "invoice.xml": b"xml"})
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.xml"


def test_skips_nested_zip():
    inner = _make_zip({"inner.pdf": b"pdf"})
    outer = _make_zip({"nested.zip": inner, "invoice.pdf": b"pdf"})
    result = extract_zip_contents("outer.zip", outer)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.pdf"


def test_empty_zip_returns_empty_list():
    data = _make_zip({})
    result = extract_zip_contents("empty.zip", data)
    assert result == []


def test_corrupt_zip_returns_empty_list():
    result = extract_zip_contents("corrupt.zip", b"not a zip file at all")
    assert result == []


def test_preserves_file_data():
    pdf_bytes = b"%PDF-1.4 fake content"
    data = _make_zip({"real.pdf": pdf_bytes})
    result = extract_zip_contents("test.zip", data)
    assert result[0]["data"] == pdf_bytes


def test_strips_directory_prefix_from_filename():
    data = _make_zip({"subdir/invoice.pdf": b"pdf"})
    result = extract_zip_contents("test.zip", data)
    assert result[0]["filename"] == "invoice.pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/infrastructure/test_zip_extractor.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `zip_extractor` doesn't exist yet.

- [ ] **Step 3: Implement ZipExtractor**

```python
# app/infrastructure/parsers/zip_extractor.py
import io
import logging
import zipfile

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".pdf", ".xml"}


def extract_zip_contents(zip_filename: str, zip_data: bytes) -> list[dict]:
    """Extract PDF and XML files from a ZIP archive.

    Returns list of {"filename": str, "data": bytes} dicts.
    Returns empty list on error or no valid files.
    """
    try:
        buf = io.BytesIO(zip_data)
        with zipfile.ZipFile(buf, "r") as zf:
            results = []
            for info in zf.infolist():
                name = info.filename
                basename = name.split("/")[-1]

                if not basename:
                    continue
                if basename.startswith("."):
                    continue
                if "__MACOSX" in name:
                    continue

                ext = "." + basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
                if ext == ".zip":
                    logger.warning(f"[ZipExtractor] Skipping nested ZIP: {name}")
                    continue
                if ext not in _ALLOWED_EXTENSIONS:
                    logger.debug(f"[ZipExtractor] Skipping unsupported file: {name}")
                    continue

                data = zf.read(name)
                results.append({"filename": basename, "data": data})
                logger.debug(f"[ZipExtractor] Extracted: {basename} ({len(data)} bytes)")

            if not results:
                logger.warning(f"[ZipExtractor] No valid invoice files found in {zip_filename}")
            return results

    except zipfile.BadZipFile:
        logger.error(f"[ZipExtractor] Invalid or corrupt ZIP: {zip_filename}")
        return []
    except Exception as e:
        logger.error(f"[ZipExtractor] Unexpected error reading {zip_filename}: {e}")
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/infrastructure/test_zip_extractor.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/parsers/zip_extractor.py tests/infrastructure/test_zip_extractor.py
git commit -m "feat: add ZipExtractor utility for ZIP attachment support"
```

---

### Task 2: Email listener — ZIP expansion

**Files:**
- Modify: `app/infrastructure/email/email_listener.py:62-112`

- [ ] **Step 1: Add ZIP expansion before XML/PDF split**

In `_process_emails`, after line `attachments = self._extract_attachments_from_raw(raw)` and before `xmls = [...]`, insert:

```python
from app.infrastructure.parsers.zip_extractor import extract_zip_contents

# Expand ZIP attachments before XML/PDF split
expanded = []
for a in attachments:
    if a['filename'].lower().endswith('.zip'):
        extracted = extract_zip_contents(a['filename'], a['data'])
        logger.info(f"[EmailListener] ZIP {a['filename']} → {len(extracted)} files extracted")
        expanded.extend(extracted)
    else:
        expanded.append(a)
attachments = expanded
```

The full block after this change (lines ~62–112) looks like:

```python
attachments = self._extract_attachments_from_raw(raw)

if not attachments:
    logger.warning(f"[EmailListener] No attachments found in email {email['id']}")
    continue

# Expand ZIP attachments before XML/PDF split
from app.infrastructure.parsers.zip_extractor import extract_zip_contents
expanded = []
for a in attachments:
    if a['filename'].lower().endswith('.zip'):
        extracted = extract_zip_contents(a['filename'], a['data'])
        logger.info(f"[EmailListener] ZIP {a['filename']} → {len(extracted)} files extracted")
        expanded.extend(extracted)
    else:
        expanded.append(a)
attachments = expanded

if not attachments:
    logger.warning(f"[EmailListener] No processable files in email {email['id']} after ZIP expansion")
    continue

xmls = [a for a in attachments if a['filename'].lower().endswith(".xml")]
pdfs = [a for a in attachments if a['filename'].lower().endswith(".pdf")]
others = [
    a for a in attachments
    if not a['filename'].lower().endswith((".xml", ".pdf"))
]
# ... rest unchanged
```

Move the `import` to the top of the file (with other imports).

- [ ] **Step 2: Move import to top of file**

Add to imports at top of `app/infrastructure/email/email_listener.py`:

```python
from app.infrastructure.parsers.zip_extractor import extract_zip_contents
```

Remove inline import from `_process_emails`.

- [ ] **Step 3: Run existing tests to verify nothing broke**

```bash
python -m pytest tests/ -v --ignore=tests/infrastructure/test_zip_extractor.py
```

Expected: all existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/infrastructure/email/email_listener.py
git commit -m "feat: expand ZIP attachments in email listener before XML/PDF split"
```

---

### Task 3: API upload route — ZIP expansion

**Files:**
- Modify: `app/presentation/api/router.py:9-33`

- [ ] **Step 1: Refactor upload_invoices to expand ZIPs**

Replace the current `upload_invoices` function body:

```python
@router.post("/jobs", response_model=list[JobResponse])
async def upload_invoices(
    files: list[UploadFile] = File(...),
    process_uc=Depends(get_process_invoice_uc),
    repo=Depends(get_job_repo),
):
    from app.infrastructure.parsers.zip_extractor import extract_zip_contents

    # Read all files, expanding ZIPs inline
    expanded: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        if f.filename.lower().endswith('.zip'):
            for item in extract_zip_contents(f.filename, raw):
                expanded.append((item['filename'], item['data']))
        else:
            expanded.append((f.filename, raw))

    # Pair XML + PDF by base filename (same logic as before)
    file_map: dict[str, dict] = {}
    for filename, data in expanded:
        base = filename.rsplit(".", 1)[0].lower()
        ext = filename.rsplit(".", 1)[-1].lower()
        if base not in file_map:
            file_map[base] = {}
        file_map[base][ext] = (filename, data)

    jobs = []
    for base, exts in file_map.items():
        if "xml" in exts:
            filename, data = exts["xml"]
            paired_pdf = exts.get("pdf", (None, None))[1]
        else:
            filename, data = exts["pdf"]
            paired_pdf = None
        job = await process_uc.execute(filename=filename, file_data=data, paired_pdf=paired_pdf)
        jobs.append(_job_to_response(job))
    return jobs
```

Move import to top of file with other imports.

- [ ] **Step 2: Move import to top of file**

Add to imports at top of `app/presentation/api/router.py`:

```python
from app.infrastructure.parsers.zip_extractor import extract_zip_contents
```

Remove inline import from `upload_invoices`.

- [ ] **Step 3: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/presentation/api/router.py
git commit -m "feat: expand ZIP files in upload route before XML/PDF pairing"
```

---

### Task 4: Manual smoke test

- [ ] **Step 1: Create test ZIP and upload via API**

```bash
cd /tmp
# Create a test ZIP with one PDF and one XML
python3 -c "
import io, zipfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as zf:
    zf.writestr('test_invoice.pdf', b'%PDF-1.4 fake')
    zf.writestr('test_invoice.xml', b'<invoice/>')
open('test_invoices.zip', 'wb').write(buf.getvalue())
print('ZIP created')
"

# Upload to running server
curl -s -X POST http://localhost:8000/api/v1/jobs \
  -F "files=@test_invoices.zip" | python3 -m json.tool
```

Expected: response contains 1 job (XML+PDF paired) or 2 jobs (if unpaired), status `PENDING` or `PROCESSING`.

- [ ] **Step 2: Verify in UI**

Open `http://localhost:8000` — confirm jobs appear from ZIP upload.

- [ ] **Step 3: Final commit (if no changes needed)**

```bash
git log --oneline -5
```

All 3 feature commits should be present.
