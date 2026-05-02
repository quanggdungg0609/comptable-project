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
        <a href="https://example.com/a">pdf invoice</a>
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
