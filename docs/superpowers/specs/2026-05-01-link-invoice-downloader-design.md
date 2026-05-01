# Link Invoice Downloader — Design Spec

**Date:** 2026-05-01  
**Status:** Approved

## Problem

Some invoice emails (e.g. VNPT, Fast e-Invoice) do not attach PDF/XML files. Instead they embed direct download links in the HTML body. Current `EmailListener` skips emails with no attachments. These invoices are lost.

## Goal

Detect emails with no attachments, extract PDF/XML download links from the HTML body using heuristic scoring, download the files via HTTP, and inject them into the existing attachment pipeline — no change to downstream processing.

## Scope

- Handle any provider (generic, not whitelist-based)
- Support PDF and XML file types
- Direct HTTP links only (no auth, no captcha, no JS rendering)
- Fallback: if link download also fails, log warning and skip email (same behavior as today)

## Architecture

New flow in `EmailListener._process_emails`:

```
email received
  ├── has attachments? → existing pipeline (unchanged)
  └── no attachments?
        → extract HTML body
        → score all <a href> links
        → HTTP download top-scored links
        → filter by Content-Type (pdf/xml only)
        → inject as synthetic {filename, data} dicts
        → existing pipeline (unchanged)
```

### New Files

| File | Responsibility |
|------|---------------|
| `app/infrastructure/parsers/link_extractor.py` | Parse HTML body, score and rank links |
| `app/infrastructure/email/invoice_link_downloader.py` | Async HTTP download, filename inference, type filtering |

### Modified File

| File | Change |
|------|--------|
| `app/infrastructure/email/email_listener.py` | Replace lines 65-67 (skip on no attachments) with link-download fallback |

## Link Scoring Logic

`link_extractor.extract_scored_links(html: str) -> list[dict]`

Parses HTML with `lxml.html`, scores every `<a href>` tag:

| Signal | Points |
|--------|--------|
| Anchor text contains "pdf" or "xml" (case-insensitive) | +3 each |
| Anchor text contains "tải", "download", "click here", "nhấn vào đây" | +2 |
| Anchor text contains "hóa đơn", "invoice" | +1 |
| URL path ends with `.pdf` or `.xml` | +3 |
| URL path contains "download", "pdf", "xml", "invoice", "export" | +2 |
| Sibling/parent text near link contains "PDF" or "XML" | +1 |

**Threshold:** score ≥ 3 → candidate  
**Cap:** max 5 links per email  
**Dedup:** skip duplicate hrefs  

Returns: `list[{url, inferred_type: "pdf"|"xml"|"unknown", score}]` sorted by score descending.

## HTTP Downloader

`invoice_link_downloader.download_links(links: list[dict]) -> list[dict]`

- `httpx` async GET, 30s timeout, follow redirects
- File type detection order:
  1. `Content-Type` response header (`application/pdf`, `application/xml`, `text/xml`)
  2. URL path extension (`.pdf`, `.xml`)
- Skip links where type cannot be confirmed as pdf or xml
- Filename inference order:
  1. `Content-Disposition: attachment; filename=...` header
  2. URL path basename
  3. `invoice_{timestamp}.{ext}` fallback
- Returns list of `{filename, data}` — same shape as existing attachment dicts
- Per-link try/except: log warning on failure, continue to next link

## Integration Point

`email_listener.py` — replace:
```python
if not attachments:
    logger.warning(f"[EmailListener] No attachments found in email {email['id']}")
    continue
```

With:
```python
if not attachments:
    attachments = await download_links_from_email(raw)
if not attachments:
    logger.warning(f"[EmailListener] No attachments or downloadable links in email {email['id']}")
    continue
```

`download_links_from_email(raw: bytes) -> list[dict]`:
1. Parse raw bytes → get `text/html` body part
2. `link_extractor.extract_scored_links(html)`
3. `invoice_link_downloader.download_links(scored_links)`
4. Return results (may be empty)

## Error Handling

- Link extraction failure → log error, return empty list
- Individual link download failure → log warning, skip, try next link
- All links fail → email skipped with warning (same as current no-attachment behavior)
- No behavior change for emails that already have attachments

## Dependencies

- `lxml` (already in deps) — used directly via `lxml.html` for HTML parsing
- `httpx` (already in deps) — async HTTP downloads

## Out of Scope

- Portal-based downloads requiring captcha or login
- Browser automation
- Provider-specific parsers
- Retry logic for failed downloads (rely on existing email retry mechanism)
