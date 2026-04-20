import pytest
from pathlib import Path
from app.infrastructure.parsers.pdf_parser import extract_text_from_pdf

# Use actual test sample: tests/samples/invoice_test.pdf
SAMPLE_PDF_PATH = Path(__file__).parent.parent / "samples" / "invoice_test.pdf"

def test_extract_text_from_pdf_returns_string():
    # Test with real Vietnamese e-invoice PDF
    assert SAMPLE_PDF_PATH.exists(), f"Sample PDF not found at {SAMPLE_PDF_PATH}"
    with open(SAMPLE_PDF_PATH, "rb") as f:
        text = extract_text_from_pdf(f.read())
    
    # Verify extraction returns string
    assert isinstance(text, str)
    assert len(text) > 0
    # Should contain invoice-related keywords (Vietnamese)
    assert any(kw in text.lower() for kw in ["hóa đơn", "invoice", "gtgt", "khhdon"])

def test_extract_text_raises_on_invalid_data():
    with pytest.raises(Exception):
        extract_text_from_pdf(b"not a pdf")