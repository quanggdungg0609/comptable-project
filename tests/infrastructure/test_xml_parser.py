from app.infrastructure.parsers.xml_parser import extract_text_from_xml

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HDon>
  <DLHDon Id="VLFNC_W9EKDE">
    <TTChung>
      <PBan>2.1.0</PBan>
      <THDon>Hóa đơn giá trị gia tăng</THDon>
      <KHMSHDon>1</KHMSHDon>
      <KHHDon>C26TAA</KHHDon>
      <SHDon>00000064</SHDon>
      <NLap>2026-03-18</NLap>
      <DVTTe>VND</DVTTe>
      <HTTToan>Chuyển khoản</HTTToan>
      <MSTTCGP>0101243150</MSTTCGP>
    </TTChung>
    <NDHDon>
      <NBan>
        <Ten>CÔNG TY TNHH ĐẦU TƯ VÀ VẬN TẢI AN PHÚ</Ten>
        <MST>0201582012</MST>
        <DChi>Tổ dân phố 5 Do Nha, Phường An Dương, Hải Phòng</DChi>
        <SDThoai>0912736086</SDThoai>
        <STKNHang>19029498818888</STKNHang>
      </NBan>
      <NMua>
        <Ten>CÔNG TY TNHH MỘT THÀNH VIÊN CẢNG HOÀNG DIỆU CHÙA VẼ</Ten>
        <MST>0201712790</MST>
        <DChi>Số 5 đường Chùa Vẽ, Phường Đông Hải, Hải Phòng</DChi>
        <MKHang>KH00056</MKHang>
      </NMua>
      <DSHHDVu>
        <HHDVu>
          <STT>1</STT>
          <THHDVu>Cước vận chuyển hàng - 272 kiện = 929,621 tấn</THHDVu>
          <SLuong>0.000000</SLuong>
          <DGia>0.000000</DGia>
          <ThTien>0.000000</ThTien>
        </HHDVu>
        <HHDVu>
          <STT>2</STT>
          <THHDVu>Cước vận chuyển - Chùa Vẽ đến Nam Đình Vũ</THHDVu>
          <DVTinh>Chuyến</DVTinh>
          <SLuong>12.000000</SLuong>
          <DGia>5900000.000000</DGia>
          <ThTien>70800000.000000</ThTien>
          <TSuat>8%</TSuat>
          <TTKhac>
            <TTin>
              <TTruong>VATAmount</TTruong>
              <DLieu>5664000.0</DLieu>
            </TTin>
          </TTKhac>
        </HHDVu>
        <HHDVu>
          <STT>3</STT>
          <THHDVu>Cước vận chuyển - Chùa Vẽ đến Nam Đình Vũ</THHDVu>
          <DVTinh>Chuyến</DVTinh>
          <SLuong>11.000000</SLuong>
          <DGia>5900000.000000</DGia>
          <ThTien>64900000.000000</ThTien>
          <TSuat>8%</TSuat>
          <TTKhac>
            <TTin>
              <TTruong>VATAmount</TTruong>
              <DLieu>5192000.0</DLieu>
            </TTin>
          </TTKhac>
        </HHDVu>
      </DSHHDVu>
      <TToan>
        <THTTLTSuat>
          <LTSuat>
            <TSuat>8%</TSuat>
            <ThTien>445000000.000000</ThTien>
            <TThue>35600000.000000</TThue>
          </LTSuat>
        </THTTLTSuat>
        <TgTCThue>445000000.000000</TgTCThue>
        <TgTThue>35600000.000000</TgTThue>
        <TgTTTBSo>480600000.000000</TgTTTBSo>
      </TToan>
    </NDHDon>
  </DLHDon>
</HDon>""".encode("utf-8")

def test_xml_extract_returns_string():
    result = extract_text_from_xml(SAMPLE_XML)
    assert isinstance(result, str)
    assert len(result) > 100

def test_xml_extract_contains_invoice_metadata():
    result = extract_text_from_xml(SAMPLE_XML)
    # Invoice series, number, date, party details
    assert "C26TAA" in result
    assert "00000064" in result
    assert "2026-03-18" in result
    assert "0201582012" in result  # Seller MST
    assert "0201712790" in result  # Buyer MST

def test_xml_extract_contains_invoice_items():
    result = extract_text_from_xml(SAMPLE_XML)
    # Line items: quantity, price, VAT rate, totals
    assert "12.000000" in result or "12" in result  # Qty from item 2
    assert "5900000" in result  # Unit price
    assert "8%" in result  # VAT rate
    assert "70800000" in result  # Amount for item 2

def test_xml_extract_contains_totals():
    result = extract_text_from_xml(SAMPLE_XML)
    # Invoice totals
    assert "445000000" in result  # Total before VAT
    assert "35600000" in result  # Total VAT
    assert "480600000" in result  # Grand total