# Link Invoice Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download invoice PDF/XML files from links embedded in email HTML bodies when no attachments are present, and inject them into the existing attachment pipeline.

**Architecture:** Two new modules — `link_extractor` scores `<a href>` links in HTML email bodies using keyword heuristics, `invoice_link_downloader` downloads top-scored links via `httpx` and returns dicts matching existing attachment shape. `EmailListener._process_emails` falls back to these when no attachments are found.

**Tech Stack:** Python 3.12, `lxml.html` (HTML parsing), `httpx` (async HTTP), `pytest` (tests)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/infrastructure/parsers/link_extractor.py` | Score and rank `<a href>` links in HTML |
| Create | `app/infrastructure/email/invoice_link_downloader.py` | Async HTTP download + filename inference |
| Modify | `app/infrastructure/email/email_listener.py:65-67` | Fallback to link download when no attachments |
| Create | `tests/infrastructure/test_link_extractor.py` | Unit tests for link extractor |
| Create | `tests/infrastructure/test_invoice_link_downloader.py` | Unit tests for downloader |

---

### Task 1: Link extractor

**Files:**
- Create: `app/infrastructure/parsers/link_extractor.py`
- Test: `tests/infrastructure/test_link_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/infrastructure/test_link_extractor.py`:

```python
import pytest
from app.infrastructure.parsers.link_extractor import extract_scored_links


def test_empty_html_returns_empty():
    assert extract_scored_links("") == []


def test_link_with_pdf_anchor_text_scores_above_threshold():
    html = '<a href="https://example.com/file">Download PDF</a>'
    results = extract_scored_links(html)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/file"
    assert results[0]["score"] >= 3


def test_link_with_xml_url_extension_scores_above_threshold():
    html = '<a href="https://example.com/invoice.xml">Click here</a>'
    results = extract_scored_links(html)
    assert len(results) == 1
    assert results[0]["inferred_type"] == "xml"
    assert results[0]["score"] >= 3


def test_link_below_threshold_excluded():
    html = '<a href="https://example.com/page">Home</a>'
    results = extract_scored_links(html)
    assert results == []


def test_duplicate_urls_deduplicated():
    html = '''
        <a href="https://example.com/invoice.pdf">Download PDF</a>
        <a href="https://example.com/invoice.pdf">PDF again</a>
    '''
    results = extract_scored_links(html)
    assert len(results) == 1


def test_results_capped_at_five():
    links = "".join(
        f'<a href="https://example.com/invoice{i}.pdf">Download PDF {i}</a>'
        for i in range(10)
    )
    html = f"<div>{links}</div>"
    results = extract_scored_links(html)
    assert len(results) <= 5


def test_results_sorted_by_score_descending():
    html = '''
        <a href="https://example.com/a">invoice</a>
        <a href="https://example.com/b.pdf">Download PDF invoice hóa đơn</a>
    '''
    results = extract_scored_links(html)
    assert len(results) >= 2
    assert results[0]["score"] >= results[1]["score"]


def test_vnpt_style_email_extracts_pdf_link():
    html = '''
        <p>Để tải hóa đơn dạng PDF: <a href="https://vnpt.vn/download/00000237.pdf">Nhấp chuột tại đây</a></p>
    '''
    results = extract_scored_links(html)
    assert len(results) == 1
    assert results[0]["inferred_type"] == "pdf"


def test_fast_einvoice_style_extracts_xml_and_pdf_links():
    html = '''
        <p>Để tải tệp thông tin hóa đơn điện tử (To download the XML file)
           <a href="https://fast.com/download/1056.xml">Nhấn vào đây</a></p>
        <p>Để tải tệp bản thể hiện của hóa đơn điện tử (To download the PDF file)
           <a href="https://fast.com/download/1056.pdf">Nhấn vào đây</a></p>
    '''
    results = extract_scored_links(html)
    types = {r["inferred_type"] for r in results}
    assert "pdf" in types
    assert "xml" in types


def test_non_http_links_ignored():
    html = '<a href="mailto:test@example.com">Email us</a>'
    results = extract_scored_links(html)
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/infrastructure/test_link_extractor.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — `link_extractor` does not exist yet.

- [ ] **Step 3: Implement link_extractor.py**

Create `app/infrastructure/parsers/link_extractor.py`:

```python
import logging
from urllib.parse import urlparse
import lxml.html

logger = logging.getLogger(__name__)

_ANCHOR_SCORES: list[tuple[str, int]] = [
    ("pdf", 3),
    ("xml", 3),
    ("tải", 2),
    ("download", 2),
    ("click here", 2),
    ("nhấn vào đây", 2),
    ("hóa đơn", 1),
    ("invoice", 1),
]

_URL_KEYWORD_SCORES: list[tuple[str, int]] = [
    ("download", 2),
    ("pdf", 2),
    ("xml", 2),
    ("invoice", 2),
    ("export", 2),
]

_THRESHOLD = 3
_MAX_LINKS = 5


def extract_scored_links(html: str) -> list[dict]:
    if not html:
        return []
    try:
        doc = lxml.html.fromstring(html)
    except Exception as e:
        logger.error(f"[LinkExtractor] HTML parse error: {e}")
        return []

    seen: set[str] = set()
    candidates: list[dict] = []

    for a in doc.iter("a"):
        href = (a.get("href") or "").strip()
        if not href.startswith("http"):
            continue
        if href in seen:
            continue
        seen.add(href)

        anchor_text = (a.text_content() or "").lower()
        url_path = urlparse(href).path.lower()
        score = 0

        for keyword, pts in _ANCHOR_SCORES:
            if keyword in anchor_text:
                score += pts

        if url_path.endswith(".pdf"):
            score += 3
        elif url_path.endswith(".xml"):
            score += 3
        for keyword, pts in _URL_KEYWORD_SCORES:
            if keyword in url_path:
                score += pts

        parent = a.getparent()
        if parent is not None:
            surrounding = (parent.text_content() or "").lower().replace(anchor_text, "")
            if "pdf" in surrounding or "xml" in surrounding:
                score += 1

        if score < _THRESHOLD:
            continue

        if url_path.endswith(".pdf") or "pdf" in anchor_text:
            inferred_type = "pdf"
        elif url_path.endswith(".xml") or "xml" in anchor_text:
            inferred_type = "xml"
        else:
            inferred_type = "unknown"

        candidates.append({"url": href, "inferred_type": inferred_type, "score": score})

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:_MAX_LINKS]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/infrastructure/test_link_extractor.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/parsers/link_extractor.py tests/infrastructure/test_link_extractor.py
git commit -m "feat: add HTML link extractor with heuristic scoring"
```

---

### Task 2: Invoice link downloader

**Files:**
- Create: `app/infrastructure/email/invoice_link_downloader.py`
- Test: `tests/infrastructure/test_invoice_link_downloader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/infrastructure/test_invoice_link_downloader.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.infrastructure.email.invoice_link_downloader import download_links


def _make_response(content_type: str, body: bytes, content_disposition: str = "", status_code: int = 200, url: str = "https://example.com/file"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = body
    resp.headers = {}
    if content_type:
        resp.headers["content-type"] = content_type
    if content_disposition:
        resp.headers["content-disposition"] = content_disposition
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_pdf_content_type_returns_attachment():
    resp = _make_response("application/pdf", b"%PDF-1.4 content", url="https://example.com/inv")
    links = [{"url": "https://example.com/inv", "inferred_type": "pdf", "score": 5}]

    with patch("app.infrastructure.email.invoice_link_downloader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        result = await download_links(links)

    assert len(result) == 1
    assert result[0]["data"] == b"%PDF-1.4 content"
    assert result[0]["filename"].endswith(".pdf")


@pytest.mark.asyncio
async def test_xml_content_type_returns_attachment():
    resp = _make_response("application/xml", b"<invoice/>", url="https://example.com/inv")
    links = [{"url": "https://example.com/inv", "inferred_type": "xml", "score": 5}]

    with patch("app.infrastructure.email.invoice_link_downloader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        result = await download_links(links)

    assert len(result) == 1
    assert result[0]["filename"].endswith(".xml")


@pytest.mark.asyncio
async def test_unsupported_content_type_skipped():
    resp = _make_response("text/html", b"<html/>", url="https://example.com/page")
    links = [{"url": "https://example.com/page", "inferred_type": "unknown", "score": 3}]

    with patch("app.infrastructure.email.invoice_link_downloader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        result = await download_links(links)

    assert result == []


@pytest.mark.asyncio
async def test_content_disposition_filename_used():
    resp = _make_response(
        "application/pdf", b"pdf",
        content_disposition='attachment; filename="invoice_237.pdf"',
        url="https://example.com/dl"
    )
    links = [{"url": "https://example.com/dl", "inferred_type": "pdf", "score": 5}]

    with patch("app.infrastructure.email.invoice_link_downloader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        result = await download_links(links)

    assert result[0]["filename"] == "invoice_237.pdf"


@pytest.mark.asyncio
async def test_url_basename_used_when_no_content_disposition():
    resp = _make_response("application/pdf", b"pdf", url="https://example.com/files/00000237.pdf")
    links = [{"url": "https://example.com/files/00000237.pdf", "inferred_type": "pdf", "score": 5}]

    with patch("app.infrastructure.email.invoice_link_downloader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        result = await download_links(links)

    assert result[0]["filename"] == "00000237.pdf"


@pytest.mark.asyncio
async def test_failed_link_skipped_others_returned():
    good_resp = _make_response("application/pdf", b"pdf", url="https://example.com/good.pdf")
    links = [
        {"url": "https://example.com/bad", "inferred_type": "pdf", "score": 6},
        {"url": "https://example.com/good.pdf", "inferred_type": "pdf", "score": 5},
    ]

    async def fake_get(url, **kwargs):
        if "bad" in url:
            raise Exception("Connection error")
        return good_resp

    with patch("app.infrastructure.email.invoice_link_downloader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = fake_get

        result = await download_links(links)

    assert len(result) == 1
    assert result[0]["filename"] == "good.pdf"


@pytest.mark.asyncio
async def test_url_extension_fallback_when_content_type_generic():
    resp = _make_response("application/octet-stream", b"pdf-data", url="https://example.com/inv.pdf")
    links = [{"url": "https://example.com/inv.pdf", "inferred_type": "pdf", "score": 5}]

    with patch("app.infrastructure.email.invoice_link_downloader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=resp)

        result = await download_links(links)

    assert len(result) == 1
    assert result[0]["filename"].endswith(".pdf")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/infrastructure/test_invoice_link_downloader.py -v 2>&1 | head -20
```

Expected: `ImportError` — `invoice_link_downloader` does not exist yet.

- [ ] **Step 3: Implement invoice_link_downloader.py**

Create `app/infrastructure/email/invoice_link_downloader.py`:

```python
import logging
import re
from datetime import datetime
from urllib.parse import urlparse
import httpx

logger = logging.getLogger(__name__)

_CONTENT_TYPE_TO_EXT = {
    "application/pdf": "pdf",
    "application/xml": "xml",
    "text/xml": "xml",
}


async def download_links(links: list[dict]) -> list[dict]:
    results = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for link in links:
            try:
                result = await _download_one(client, link["url"])
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"[InvoiceLinkDownloader] Failed {link['url']}: {e}")
    return results


async def _download_one(client: httpx.AsyncClient, url: str) -> dict | None:
    response = await client.get(url)
    response.raise_for_status()

    raw_ct = response.headers.get("content-type", "")
    content_type = raw_ct.split(";")[0].strip().lower()
    ext = _detect_ext(content_type, url)

    if ext is None:
        logger.debug(f"[InvoiceLinkDownloader] Skip {url} — type '{content_type}' not pdf/xml")
        return None

    filename = _infer_filename(response.headers, url, ext)
    logger.info(f"[InvoiceLinkDownloader] Downloaded {filename} ({len(response.content)} bytes)")
    return {"filename": filename, "data": response.content}


def _detect_ext(content_type: str, url: str) -> str | None:
    if content_type in _CONTENT_TYPE_TO_EXT:
        return _CONTENT_TYPE_TO_EXT[content_type]
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith(".xml"):
        return "xml"
    return None


def _infer_filename(headers: httpx.Headers, url: str, ext: str) -> str:
    cd = headers.get("content-disposition", "")
    match = re.search(r'filename=["\']?([^"\';\r\n]+)["\']?', cd, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    basename = urlparse(url).path.rstrip("/").split("/")[-1]
    if basename and "." in basename:
        return basename

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"invoice_{ts}.{ext}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/infrastructure/test_invoice_link_downloader.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/email/invoice_link_downloader.py tests/infrastructure/test_invoice_link_downloader.py
git commit -m "feat: add async invoice link downloader"
```

---

### Task 3: EmailListener integration

**Files:**
- Modify: `app/infrastructure/email/email_listener.py:1-8,65-67`

- [ ] **Step 1: Add import and helper method**

In `app/infrastructure/email/email_listener.py`, add import at top (line 6, after existing imports):

```python
from app.infrastructure.parsers.link_extractor import extract_scored_links
from app.infrastructure.email.invoice_link_downloader import download_links
```

Then add this method inside the `EmailListener` class, after `_extract_attachments_from_raw` (after line 38):

```python
    async def _download_links_from_email(self, raw: bytes) -> list[dict]:
        try:
            msg = message_from_bytes(raw)
            html_body = None
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    html_body = payload.decode("utf-8", errors="replace")
                    break

            if not html_body:
                logger.debug("[EmailListener] No HTML body for link extraction")
                return []

            scored_links = extract_scored_links(html_body)
            if not scored_links:
                logger.debug("[EmailListener] No candidate download links found")
                return []

            logger.info(f"[EmailListener] Found {len(scored_links)} candidate download links")
            attachments = await download_links(scored_links)
            logger.info(f"[EmailListener] Downloaded {len(attachments)} files from links")
            return attachments
        except Exception as e:
            logger.error(f"[EmailListener] Link extraction error: {e}")
            return []
```

- [ ] **Step 2: Replace lines 65-67 (skip on no attachments)**

Replace:
```python
                if not attachments:
                    logger.warning(f"[EmailListener] No attachments found in email {email['id']}")
                    continue
```

With:
```python
                if not attachments:
                    logger.info(f"[EmailListener] No attachments in email {email['id']}, trying link download")
                    attachments = await self._download_links_from_email(raw)
                if not attachments:
                    logger.warning(f"[EmailListener] No attachments or downloadable links in email {email['id']}")
                    continue
```

- [ ] **Step 3: Run full test suite to verify no regressions**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all previously passing tests still PASS, plus all new tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/infrastructure/email/email_listener.py
git commit -m "feat: fall back to link download when email has no attachments"
```

---

### Task 4: Full integration smoke test

- [ ] **Step 1: Verify imports work cleanly**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -c "from app.infrastructure.email.email_listener import EmailListener; print('OK')"
```

Expected: `OK`

- [ ] **Step 2: Run complete test suite**

```bash
cd /Users/quangdung/Documents/collect_invoice
python -m pytest tests/ -v
```

Expected: all tests pass, no import errors.

- [ ] **Step 3: Final commit**

```bash
git add -A
git status
```

If clean (nothing unstaged), no commit needed. If any stragglers, commit them:

```bash
git commit -m "chore: finalize link invoice downloader feature"
```
