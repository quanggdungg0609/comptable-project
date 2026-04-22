import asyncio
import json
import logging
import httpx
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.ports.llm_port import ILLMPort
from app.infrastructure.llm.ollama_client import EXTRACTION_PROMPT, _parse_item, _parse_line_item

logger = logging.getLogger(__name__)


def _clean_json(raw: str) -> str:
    """Strip markdown code fences Gemini sometimes wraps around JSON."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]  # drop first line (```json or ```)
        s = s.rsplit("```", 1)[0]  # drop closing ```
    return s.strip()


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 60
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GeminiLLMClient(ILLMPort):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model

    async def extract_invoice(self, content: str) -> tuple[list[InvoiceItem], list[InvoiceLineItem]]:
        prompt = EXTRACTION_PROMPT.format(content=content)
        url = GEMINI_API_URL.format(model=self._model)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 8192,
            },
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            data = None
            for attempt in range(_MAX_RETRIES + 1):
                resp = await client.post(
                    url,
                    headers={"x-goog-api-key": self._api_key},
                    json=payload,
                )

                # HTTP-level retry for transient server errors
                if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                    retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                    wait = int(retry_after) if (retry_after and retry_after.isdigit()) else min(30 * (2 ** attempt), 120)
                    logger.warning("Gemini %d — attempt %d/%d, waiting %ds.", resp.status_code, attempt + 1, _MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

                # JSON parse retry — Gemini occasionally returns malformed JSON
                try:
                    data = json.loads(_clean_json(raw))
                    break
                except json.JSONDecodeError:
                    if attempt == _MAX_RETRIES:
                        raise
                    logger.warning("Gemini returned invalid JSON on attempt %d, retrying...", attempt + 1)
                    await asyncio.sleep(2)

        items = [_parse_item(i) for i in data.get("items", [])]
        line_items = [_parse_line_item(li, items) for li in data.get("line_items", [])]
        return items, line_items
