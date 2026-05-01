# ZIP Support Design

**Date:** 2026-05-01  
**Status:** Approved

## Problem

Emails and manual uploads sometimes contain ZIP files with multiple invoice files (PDF, XML, or XML+PDF pairs). Current system raises `ValueError` for any non-PDF/XML attachment.

## Approach

Extract ZIP at intake layer before existing pipeline. Downstream code (XML/PDF pairing, `ProcessInvoice`, `FileType`) unchanged.

## New Component: `ZipExtractor`

**Path:** `app/infrastructure/parsers/zip_extractor.py`

**Interface:**
```python
def extract_zip_contents(zip_filename: str, zip_data: bytes) -> list[dict]:
    # returns: [{"filename": str, "data": bytes}, ...]
```

**Rules:**
- stdlib `zipfile` only — no new dependencies
- Keep only `.pdf` and `.xml` files
- Skip: `__MACOSX/`, `.DS_Store`, hidden files, nested ZIPs, unsupported extensions
- Flat extraction only (no recursion into nested ZIPs)
- On corrupt/invalid ZIP: log error, return empty list

## Email Path

**File:** `app/infrastructure/email/email_listener.py`  
**Change:** Expand ZIPs inline before XML/PDF split in `_process_emails`.

```python
from app.infrastructure.parsers.zip_extractor import extract_zip_contents

expanded = []
for a in attachments:
    if a['filename'].lower().endswith('.zip'):
        extracted = extract_zip_contents(a['filename'], a['data'])
        logger.info(f"[EmailListener] ZIP {a['filename']} → {len(extracted)} files")
        expanded.extend(extracted)
    else:
        expanded.append(a)
attachments = expanded
# existing xml/pdf/others split continues unchanged
```

## Upload Path

**File:** `app/presentation/api/router.py`  
**Change:** Expand ZIPs before building `file_map` in `upload_invoices`.

```python
from app.infrastructure.parsers.zip_extractor import extract_zip_contents

expanded: list[tuple[str, bytes]] = []
for f in files:
    raw = await f.read()
    if f.filename.lower().endswith('.zip'):
        for item in extract_zip_contents(f.filename, raw):
            expanded.append((item['filename'], item['data']))
    else:
        expanded.append((f.filename, raw))

file_map: dict[str, dict] = {}
for filename, data in expanded:
    base = filename.rsplit(".", 1)[0].lower()
    ext = filename.rsplit(".", 1)[-1].lower()
    if base not in file_map:
        file_map[base] = {}
    file_map[base][ext] = (filename, data)
```

## Error Handling

| Scenario | Behavior |
|---|---|
| Corrupt/invalid ZIP | Log error, skip entire ZIP (0 jobs created) |
| ZIP with no valid files | Log warning, skip |
| Unsupported file inside ZIP | Log + skip that file only |
| Nested ZIP | Log + skip |

## Files Changed

| File | Change |
|---|---|
| `app/infrastructure/parsers/zip_extractor.py` | **New** — ZIP extraction utility |
| `app/infrastructure/email/email_listener.py` | Add ZIP expansion before split logic |
| `app/presentation/api/router.py` | Add ZIP expansion before file_map loop |

## Files NOT Changed

- `app/domain/value_objects/file_type.py` — ZIP never reaches `FileType`
- `app/application/use_cases/process_invoice.py` — unchanged
- DB schema, entities, API schemas — unchanged

## Tests

- Unit: `test_zip_extractor.py` — valid ZIP, corrupt ZIP, empty ZIP, nested ZIP, mixed content, `__MACOSX` filtering
- Integration: email with ZIP → N jobs created
- Integration: upload ZIP → N jobs created
