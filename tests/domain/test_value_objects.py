import pytest
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus


def test_file_type_from_pdf():
    assert FileType.from_filename("invoice.pdf") == FileType.PDF


def test_file_type_from_xml():
    assert FileType.from_filename("invoice.xml") == FileType.XML


def test_file_type_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        FileType.from_filename("invoice.docx")


def test_invoice_status_has_required_states():
    for name in ("PENDING", "PROCESSING", "AWAITING_REVIEW", "CONFIRMED", "REJECTED", "FAILED"):
        assert InvoiceStatus[name].value == name




        
    