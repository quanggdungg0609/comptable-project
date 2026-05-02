import logging
import httpx
import re
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)


async def download_invoices_from_links(links: list[dict]) -> list[tuple[str, bytes]]:
    """Download invoices from the provided list of scored links.
    
    Returns a list of tuples (filename, content).
    """
    if not links:
        return []

    results: list[tuple[str, bytes]] = []
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for link in links:
            url = link["url"]
            try:
                logger.info(f"[LinkDownloader] Downloading {url}")
                response = await client.get(url)
                if response.status_code != 200:
                    logger.warning(f"[LinkDownloader] Failed to download {url}: {response.status_code}")
                    continue

                filename = _get_filename_from_response(response, url)
                results.append((filename, response.content))
                
            except Exception as e:
                logger.error(f"[LinkDownloader] Error downloading {url}: {e}")
                continue

    return results


def _get_filename_from_response(response: httpx.Response, url: str) -> str:
    # 1. Try Content-Disposition
    cd = response.headers.get("Content-Disposition", "")
    if cd:
        # attachment; filename="invoice.pdf"
        match = re.search(r'filename="?([^";]+)"?', cd)
        if match:
            return unquote(match.group(1))

    # 2. Try URL path
    path = urlparse(url).path
    if path and "/" in path:
        filename = path.split("/")[-1]
        if filename and "." in filename:
            return unquote(filename)

    # 3. Default based on content type
    ct = response.headers.get("Content-Type", "").lower()
    if "pdf" in ct:
        return "invoice.pdf"
    if "xml" in ct:
        return "invoice.xml"

    return "downloaded_file"
