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
    """Extract and score links from HTML body.
    
    Returns a list of dicts: {"url": str, "inferred_type": str, "score": int}
    """
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

        # Score based on anchor text
        for keyword, pts in _ANCHOR_SCORES:
            if keyword in anchor_text:
                score += pts

        # Score based on URL path
        if url_path.endswith(".pdf"):
            score += 3
        elif url_path.endswith(".xml"):
            score += 3
        
        for keyword, pts in _URL_KEYWORD_SCORES:
            if keyword in url_path:
                score += pts

        # Score based on surrounding text (parent container)
        parent = a.getparent()
        if parent is not None:
            surrounding = (parent.text_content() or "").lower().replace(anchor_text, "")
            if "pdf" in surrounding or "xml" in surrounding:
                score += 1

        if score < _THRESHOLD:
            continue

        # Infer type
        if url_path.endswith(".pdf") or "pdf" in anchor_text:
            inferred_type = "pdf"
        elif url_path.endswith(".xml") or "xml" in anchor_text:
            inferred_type = "xml"
        else:
            inferred_type = "unknown"

        candidates.append({
            "url": href,
            "inferred_type": inferred_type,
            "score": score
        })

    # Sort by score descending and cap results
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:_MAX_LINKS]
