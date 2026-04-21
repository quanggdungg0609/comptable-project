from decimal import Decimal
from datetime import date
from app.domain.entities.invoice_line_item import InvoiceLineItem

def test_invoice_line_item_defaults():
    item = InvoiceLineItem(
        invoice_symbol="1C26TAA",
        invoice_number="49",
        invoice_date=date(2026, 3, 12),
        seller_name="Cty XYZ",
        seller_tax_code="0901212659",
        ten_hang_hoa="Thép tấm 10mm",
        don_vi_tinh="Kg",
        so_luong=Decimal("298"),
        don_gia=Decimal("28000"),
        thanh_tien=Decimal("8344000"),
        tax_rate=Decimal("0.10"),
        tax_amount=Decimal("834400"),
    )
    assert item.ten_hang_hoa == "Thép tấm 10mm"
    assert item.so_luong == Decimal("298")
    assert isinstance(item.id, str) and len(item.id) == 36  # UUID
