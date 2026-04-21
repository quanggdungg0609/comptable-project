import asyncio
import json
import logging
import httpx
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.ports.llm_port import ILLMPort
from app.infrastructure.llm.ollama_client import EXTRACTION_PROMPT, _parse_item

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 60  # fallback if no Retry-After header
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GeminiLLMClient(ILLMPort):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model

    async def extract_invoice(self, content: str) -> list[InvoiceItem]:
        prompt = EXTRACTION_PROMPT.format(content=content)
        url = GEMINI_API_URL.format(model=self._model)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 512,
            },
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = None
            for attempt in range(_MAX_RETRIES + 1):
                resp = await client.post(
                    url,
                    headers={"x-goog-api-key": self._api_key},
                    json=payload,
                )
                if resp.status_code not in _RETRYABLE_STATUS:
                    break
                if attempt == _MAX_RETRIES:
                    break
                # honour Retry-After if Gemini sends it, else use exponential back-off
                retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    wait = min(30 * (2 ** attempt), 120)  # 30s, 60s, 120s
                logger.warning(
                    "Gemini %d — attempt %d/%d, waiting %ds. Body: %s",
                    resp.status_code, attempt + 1, _MAX_RETRIES, wait,
                    resp.text[:200],
                )
                await asyncio.sleep(wait)

            resp.raise_for_status()

        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("items", [])
        return [_parse_item(i) for i in items]
