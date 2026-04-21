from lxml import etree


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