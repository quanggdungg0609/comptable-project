import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from datetime import date
from app.infrastructure.llm.ollama_client import OllamaLLMClient

MOCK_LLM_RESPONSE = """{
  "items": [
    {
      "invoice_symbol": "C26TAA",
      "invoice_number": "00000064",
      "invoice_date": "2026-03-18",
      "seller_name": "CÔNG TY TNHH ĐẦU TƯ VÀ VẬN TẢI AN PHÚ",
      "seller_tax_code": "0201582012",
      "description": "Hàng hóa/Dịch vụ",
      "price_before_tax": 445000000,
      "tax_rate": 0.08,
      "price_after_tax": 35600000
    }
  ]
}"""

@pytest.fixture
def client():
    return OllamaLLMClient(base_url="http://localhost:11434", model="gemma4:e2b")

async def test_extract_invoice_returns_items(client):
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": MOCK_LLM_RESPONSE}
    }
    # raise_for_status is a sync method in httpx
    mock_response.raise_for_status.return_value = None
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        items = await client.extract_invoice("KHHDon: C26TAA\nSHDon: 00000064\n...")
    assert len(items) == 1
    assert items[0].invoice_number == "00000064"
    assert items[0].price_before_tax == Decimal("445000000")
    assert items[0].tax_rate == Decimal("0.08")
    assert items[0].price_after_tax == Decimal("35600000")
    assert items[0].invoice_date == date(2026, 3, 18)