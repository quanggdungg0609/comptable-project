from decimal import Decimal
from datetime import date
from app.infrastructure.parsers.xml_parser import extract_line_items_from_xml

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
  <DLHDon>
    <TTChung>
      <KHHDon>1C26TAA</KHHDon>
      <SHDon>49</SHDon>
      <NLap>2026-03-12</NLap>
    </TTChung>
    <NDHDon>
      <NBan>
        <Ten>Cty TNHH ĐT và TM Linh Chi Nguyễn</Ten>
        <MST>0901212659</MST>
      </NBan>
      <DSHHDVu>
        <HHDVu>
          <STT>1</STT>
          <THHDVu>Thép tấm 10mm</THHDVu>
          <DVTinh>Kg</DVTinh>
          <SLuong>298</SLuong>
          <DGia>28000</DGia>
          <ThTien>8344000</ThTien>
          <TSuat>10%</TSuat>
        </HHDVu>
        <HHDVu>
          <STT>2</STT>
          <THHDVu>Thép tấm 4mm</THHDVu>
          <DVTinh>Kg</DVTinh>
          <SLuong>42</SLuong>
          <DGia>28000</DGia>
          <ThTien>1176000</ThTien>
          <TSuat>10%</TSuat>
        </HHDVu>
        <HHDVu>
          <STT>3</STT>
          <THHDVu>Dịch vụ bỏ qua</THHDVu>
          <SLuong>0</SLuong>
          <DGia>0</DGia>
          <ThTien>0</ThTien>
        </HHDVu>
      </DSHHDVu>
    </NDHDon>
  </DLHDon>
</HDon>""".encode("utf-8")

def test_extract_returns_correct_count():
    items = extract_line_items_from_xml(SAMPLE_XML)
    assert len(items) == 2  # row with SLuong=0 is skipped

def test_extract_fields_correct():
    items = extract_line_items_from_xml(SAMPLE_XML)
    first = items[0]
    assert first.ten_hang_hoa == "Thép tấm 10mm"
    assert first.don_vi_tinh == "Kg"
    assert first.so_luong == Decimal("298")
    assert first.don_gia == Decimal("28000")
    assert first.thanh_tien == Decimal("8344000")
    assert first.tax_rate == Decimal("0.10")
    assert first.invoice_symbol == "1C26TAA"
    assert first.invoice_number == "49"
    assert first.invoice_date == date(2026, 3, 12)
    assert first.seller_name == "Cty TNHH ĐT và TM Linh Chi Nguyễn"
    assert first.seller_tax_code == "0901212659"

def test_tax_amount_computed():
    items = extract_line_items_from_xml(SAMPLE_XML)
    first = items[0]
    # tax_amount = thanh_tien * tax_rate = 8344000 * 0.10 = 834400
    assert first.tax_amount == Decimal("834400.0")
