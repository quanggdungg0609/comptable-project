import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from datetime import date
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.value_objects.invoice_status import InvoiceStatus

def make_item():
    return InvoiceItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", description="Mua vật tư",
        price_before_tax=Decimal("8344000"), tax_rate=Decimal("0.10"),
        price_after_tax=Decimal("834400"),
    )

def make_line_item():
    return InvoiceLineItem(
        invoice_symbol="1C26TAA", invoice_number="49",
        invoice_date=date(2026, 3, 12), seller_name="Cty XYZ",
        seller_tax_code="0901212659", ten_hang_hoa="Thép tấm 10mm",
        don_vi_tinh="Kg", so_luong=Decimal("298"), don_gia=Decimal("28000"),
        thanh_tien=Decimal("8344000"), tax_rate=Decimal("0.10"),
        tax_amount=Decimal("834400"),
    )

@pytest.fixture
def use_case():
    repo = AsyncMock()
    llm = AsyncMock()
    llm.extract_invoice.return_value = ([make_item()], [make_line_item()])
    return ProcessInvoiceUseCase(repo=repo, llm=llm), repo, llm

async def test_xml_saves_line_items_from_xml_parser(use_case):
    uc, repo, llm = use_case
    fake_line_items = [make_line_item()]
    with patch(
        "app.application.use_cases.process_invoice.extract_line_items_from_xml",
        return_value=fake_line_items,
    ):
        job = await uc.execute(
            filename="hd049.xml",
            file_data=b"<HDon><SHDon>49</SHDon></HDon>",
        )
    assert job.status == InvoiceStatus.AWAITING_REVIEW
    repo.save_line_items.assert_called_once_with(job.id, fake_line_items)

async def test_pdf_saves_line_items_from_llm(use_case):
    uc, repo, llm = use_case
    job = await uc.execute(
        filename="hd049.pdf",
        file_data=b"%PDF-1.4",
    )
    assert job.status == InvoiceStatus.AWAITING_REVIEW
    repo.save_line_items.assert_called_once()
    saved_items = repo.save_line_items.call_args[0][1]
    assert len(saved_items) == 1
    assert saved_items[0].ten_hang_hoa == "Thép tấm 10mm"
