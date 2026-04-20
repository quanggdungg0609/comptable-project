from lxml import etree

def extract_text_from_xml(data: bytes) -> str:
    """
    Parse Vietnamese e-invoice XML and flatten to readable text for LLM.
    
    Preserves structure:
    - Invoice metadata (TTChung)
    - Seller/Buyer info (NBan, NMua)
    - Line items (DSHHDVu/HHDVu) with qty, price, VAT, amounts
    - Totals (TToan)
    
    Returns single string suitable for LLM extraction of invoice fields.
    """
    root = etree.fromstring(data)
    parts = []
    
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        text = (elem.text or "").strip()
        
        if text:
            # Preserve key financial fields with labels
            if tag in ("SHDon", "KHHDon", "NLap", "SLuong", "DGia", "ThTien", 
                      "TSuat", "TThue", "TgTCThue", "TgTThue", "TgTTTBSo",
                      "MST", "Ten", "STT", "THHDVu"):
                parts.append(f"{tag}: {text}")
            else:
                # Include other content as-is
                if len(text) > 2:  # Skip short junk
                    parts.append(f"{tag}: {text}")
    
    return "\n".join(parts)