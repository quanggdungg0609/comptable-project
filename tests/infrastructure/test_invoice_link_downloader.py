import pytest
from unittest.mock import AsyncMock, patch
from app.infrastructure.email.invoice_link_downloader import download_invoices_from_links


@pytest.mark.asyncio
async def test_download_invoices_from_links_empty_returns_empty():
    results = await download_invoices_from_links([])
    assert results == []


@pytest.mark.asyncio
async def test_download_invoices_from_links_success():
    links = [
        {"url": "https://example.com/invoice.pdf", "inferred_type": "pdf", "score": 5},
        {"url": "https://example.com/data", "inferred_type": "xml", "score": 4}
    ]
    
    mock_response_pdf = AsyncMock()
    mock_response_pdf.status_code = 200
    mock_response_pdf.content = b"%PDF-1.4"
    mock_response_pdf.headers = {"Content-Type": "application/pdf"}
    
    mock_response_xml = AsyncMock()
    mock_response_xml.status_code = 200
    mock_response_xml.content = b"<xml>invoice</xml>"
    mock_response_xml.headers = {
        "Content-Type": "text/xml",
        "Content-Disposition": 'attachment; filename="hóa_đơn.xml"'
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [mock_response_pdf, mock_response_xml]
        
        results = await download_invoices_from_links(links)
        
        assert len(results) == 2
        assert results[0][0] == "invoice.pdf"
        assert results[0][1] == b"%PDF-1.4"
        assert results[1][0] == "hóa_đơn.xml"
        assert results[1][1] == b"<xml>invoice</xml>"


@pytest.mark.asyncio
async def test_download_invoices_from_links_handles_errors():
    links = [{"url": "https://example.com/fail", "inferred_type": "pdf", "score": 5}]
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = Exception("Connection error")
        
        results = await download_invoices_from_links(links)
        assert results == []


@pytest.mark.asyncio
async def test_download_invoices_from_links_skips_non_200():
    links = [{"url": "https://example.com/404", "inferred_type": "pdf", "score": 5}]
    
    mock_response = AsyncMock()
    mock_response.status_code = 404
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = mock_response
        
        results = await download_invoices_from_links(links)
        assert results == []
