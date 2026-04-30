import io
import pytest
import pandas as pd
from app.infrastructure.parsers.excel_cr_source_parser import parse_source_file

def _make_csv_bytes(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue()

SAMPLE_ROWS = [
    {"Tháng": 1, "Ngày": "2025-01-02", "Diễn giải": "Thưởng sáng kiến", "TK": 111,
     "Số tiền": 58_900_000, "Khoản mục": "cpk", "TK cp": ""},
    {"Tháng": 1, "Ngày": "2025-01-15", "Diễn giải": "Trợ cấp TNLĐ", "TK": 111,
     "Số tiền": 9_336_600, "Khoản mục": "cpk", "TK cp": ""},
    {"Tháng": 2, "Ngày": "2025-02-05", "Diễn giải": "Thưởng sáng kiến", "TK": 111,
     "Số tiền": 12_000_000, "Khoản mục": "cpk", "TK cp": ""},
]

def test_parse_csv_returns_dataframe():
    data = _make_csv_bytes(SAMPLE_ROWS)
    df = parse_source_file(data, "chi_phi.csv")
    assert list(df.columns) == ["thang", "dien_giai", "so_tien", "khoan_muc"]

def test_parse_csv_row_count():
    data = _make_csv_bytes(SAMPLE_ROWS)
    df = parse_source_file(data, "chi_phi.csv")
    assert len(df) == 3

def test_parse_csv_so_tien_numeric():
    data = _make_csv_bytes(SAMPLE_ROWS)
    df = parse_source_file(data, "chi_phi.csv")
    assert df["so_tien"].dtype.kind in ("f", "i")

def test_parse_csv_strips_numeric_khoan_muc():
    rows = SAMPLE_ROWS + [
        {"Tháng": 1, "Ngày": "2025-01-03", "Diễn giải": "Header row",
         "TK": 111, "Số tiền": 0, "Khoản mục": "123", "TK cp": ""}
    ]
    data = _make_csv_bytes(rows)
    df = parse_source_file(data, "chi_phi.csv")
    # row with numeric Khoản mục is dropped
    assert len(df) == 3

def test_parse_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        parse_source_file(b"data", "file.txt")