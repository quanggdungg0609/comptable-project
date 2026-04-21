from lxml import etree
from decimal import Decimal
from datetime import date
from app.domain.entities.invoice_line_item import InvoiceLineItem


def _local(elem) -> str:
    tag = elem.tag
    return tag.split("}")[-1] if "}" in tag else tag


def _first_text(parent, tag: str) -> str:
    for el in parent.iter():
        if _local(el) == tag:
            return (el.text or "").strip()
    return ""


def _find_elem(parent, tag: str):
    for el in parent.iter():
        if _local(el) == tag:
            return el
    return None


def extract_text_from_xml(data: bytes) -> str:
    """Extract only the fields needed for LLM invoice parsing — keeps prompt small."""
    root = etree.fromstring(data)
    lines = []

    # Header
    lines.append(f"KHHDon: {_first_text(root, 'KHHDon')}")
    lines.append(f"SHDon: {_first_text(root, 'SHDon')}")
    lines.append(f"NLap: {_first_text(root, 'NLap')}")

    # Seller
    nban = _find_elem(root, "NBan")
    if nban is not None:
        lines.append(f"NBan.Ten: {_first_text(nban, 'Ten')}")
        lines.append(f"NBan.MST: {_first_text(nban, 'MST')}")

    # Line items — only fields the prompt uses
    for el in root.iter():
        if _local(el) != "HHDVu":
            continue
        sluong = _first_text(el, "SLuong")
        if sluong == "0":
            continue
        stt = _first_text(el, "STT")
        mota = _first_text(el, "THHDVu")
        thtien = _first_text(el, "ThTien")
        tsuat = _first_text(el, "TSuat")
        tthue = _first_text(el, "TThue")
        lines.append(f"HH{stt}: {mota} | SL={sluong} ThTien={thtien} TSuat={tsuat} TThue={tthue}")

    return "\n".join(lines)


def _parse_tsuat(tsuat_str: str) -> Decimal:
    """Convert '10%' or '0.10' to Decimal 0.10."""
    s = tsuat_str.strip()
    if s.endswith("%"):
        return Decimal(s[:-1]) / Decimal("100")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _parse_date(date_str: str) -> date:
    try:
        return date.fromisoformat(date_str)
    except Exception:
        return date.today()


def extract_line_items_from_xml(data: bytes) -> list[InvoiceLineItem]:
    root = etree.fromstring(data)

    invoice_symbol = _first_text(root, "KHHDon")
    invoice_number = _first_text(root, "SHDon")
    invoice_date = _parse_date(_first_text(root, "NLap"))

    nban = _find_elem(root, "NBan")
    seller_name = _first_text(nban, "Ten") if nban is not None else ""
    seller_tax_code = _first_text(nban, "MST") if nban is not None else ""

    items = []
    for el in root.iter():
        if _local(el) != "HHDVu":
            continue
        sluong_str = _first_text(el, "SLuong")
        try:
            sluong = Decimal(sluong_str)
        except Exception:
            sluong = Decimal("0")
        if sluong == 0:
            continue

        don_gia_str = _first_text(el, "DGia") or "0"
        thanh_tien_str = _first_text(el, "ThTien") or "0"
        tsuat_str = _first_text(el, "TSuat") or "0"

        try:
            don_gia = Decimal(don_gia_str)
        except Exception:
            don_gia = Decimal("0")
        try:
            thanh_tien = Decimal(thanh_tien_str)
        except Exception:
            thanh_tien = Decimal("0")

        tax_rate = _parse_tsuat(tsuat_str)
        tax_amount = (thanh_tien * tax_rate).quantize(Decimal("0.1"))

        items.append(InvoiceLineItem(
            invoice_symbol=invoice_symbol,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            seller_name=seller_name,
            seller_tax_code=seller_tax_code,
            ten_hang_hoa=_first_text(el, "THHDVu"),
            don_vi_tinh=_first_text(el, "DVTinh"),
            so_luong=sluong,
            don_gia=don_gia,
            thanh_tien=thanh_tien,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
        ))
    return items