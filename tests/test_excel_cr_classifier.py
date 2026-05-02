import pytest
from unittest.mock import AsyncMock, patch
from app.infrastructure.llm.excel_cr_classifier import ExcelCrClassifier, ClassificationResult

@pytest.mark.asyncio
async def test_classify_returns_result_above_threshold():
    classifier = ExcelCrClassifier.__new__(ExcelCrClassifier)

    mock_response = {
        "suggestions": [
            {
                "dien_giai": "Thù lao HĐTV quý I",
                "suggested": "Chi khác",
                "confidence": 0.92,
                "reason": "Thù lao HĐTV là chi phí quản lý",
                "alternates": ["Chi phí QL"],
            }
        ]
    }

    with patch.object(classifier, "_call_llm", new=AsyncMock(return_value=mock_response)):
        results = await classifier.classify(
            khoan_muc="cpk",
            dien_giai_list=["Thù lao HĐTV quý I"],
            chi_tieu_list=["Chi khác", "Chi phí QL"],
        )

    assert len(results) == 1
    assert results[0].suggested == "Chi khác"
    assert results[0].confidence == pytest.approx(0.92)
    assert results[0].auto_apply is True

@pytest.mark.asyncio
async def test_classify_below_threshold_not_auto_applied():
    classifier = ExcelCrClassifier.__new__(ExcelCrClassifier)

    mock_response = {
        "suggestions": [
            {
                "dien_giai": "Phí thuê xe",
                "suggested": "Chi phí SXKD",
                "confidence": 0.70,
                "reason": "Không chắc",
                "alternates": [],
            }
        ]
    }

    with patch.object(classifier, "_call_llm", new=AsyncMock(return_value=mock_response)):
        results = await classifier.classify(
            khoan_muc="cpk",
            dien_giai_list=["Phí thuê xe"],
            chi_tieu_list=["Chi phí SXKD", "Chi khác"],
        )

    assert results[0].auto_apply is False
