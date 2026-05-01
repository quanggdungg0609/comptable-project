# app/infrastructure/llm/excel_cr_classifier.py
import json
import logging
from dataclasses import dataclass
from typing import Any
import httpx

logger = logging.getLogger(__name__)

_AUTO_APPLY_THRESHOLD = 0.85

_SYSTEM_PROMPT = """Bạn là chuyên gia phân loại chi phí kế toán Việt Nam.
Phân loại các khoản chi phí vào đúng Chỉ tiêu báo cáo.
Chỉ dựa vào Khoản mục và Diễn giải — KHÔNG có thông tin về số tiền hay tên công ty.
Trả lời JSON theo schema được yêu cầu."""

_USER_TEMPLATE = """Khoản mục: {khoan_muc}

Danh sách Diễn giải cần phân loại:
{dien_giai_json}

Danh sách Chỉ tiêu hợp lệ:
{chi_tieu_json}

Trả về JSON:
{{
  "suggestions": [
    {{
      "dien_giai": "<Diễn giải gốc>",
      "suggested": "<Chỉ tiêu phù hợp nhất>",
      "confidence": <0.0-1.0>,
      "reason": "<lý do ngắn gọn>",
      "alternates": ["<Chỉ tiêu thay thế nếu có>"]
    }}
  ]
}}"""

_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass
class ClassificationResult:
    dien_giai: str
    suggested: str
    confidence: float
    reason: str
    alternates: list[str]
    auto_apply: bool


class ExcelCrClassifier:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model

    async def classify(
        self,
        khoan_muc: str,
        dien_giai_list: list[str],
        chi_tieu_list: list[str],
    ) -> list[ClassificationResult]:
        if not dien_giai_list:
            return []

        prompt = _USER_TEMPLATE.format(
            khoan_muc=khoan_muc,
            dien_giai_json=json.dumps(dien_giai_list, ensure_ascii=False),
            chi_tieu_json=json.dumps(chi_tieu_list, ensure_ascii=False),
        )

        data = await self._call_llm(prompt)
        results = []
        for s in data.get("suggestions", []):
            confidence = float(s.get("confidence", 0.0))
            results.append(ClassificationResult(
                dien_giai=s.get("dien_giai", ""),
                suggested=s.get("suggested", ""),
                confidence=confidence,
                reason=s.get("reason", ""),
                alternates=s.get("alternates", []),
                auto_apply=confidence >= _AUTO_APPLY_THRESHOLD,
            ))
        return results

    async def _call_llm(self, prompt: str) -> dict[str, Any]:
        url = _GEMINI_API_URL.format(model=self._model)
        payload = {
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 4096,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url, headers={"x-goog-api-key": self._api_key}, json=payload
            )
            resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(raw)
